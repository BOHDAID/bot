import os
import sys
import asyncio
import logging
import time
import re
import traceback
from datetime import datetime

# ==============================================================================
#                               استيراد المكتبات (كاملة)
# ==============================================================================

# للتعامل مع معرفات قاعدة البيانات
from bson.objectid import ObjectId

# محرك قاعدة البيانات
from motor.motor_asyncio import AsyncIOMotorClient

# مكتبة تيليجرام (Telethon)
from telethon import TelegramClient, events, Button, functions, types
from telethon.sessions import StringSession
from telethon.tl.types import UserStatusOnline, UserStatusRecently
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.functions.channels import JoinChannelRequest, LeaveChannelRequest
from telethon.errors import FloodWaitError

# خادم الويب (لإبقاء البوت نشطاً)
from aiohttp import web

# الذكاء الاصطناعي
from openai import AsyncOpenAI

# تحميل متغيرات البيئة
from dotenv import load_dotenv

# ==============================================================================
#                               1. إعدادات النظام
# ==============================================================================

# تحميل ملف .env
load_dotenv()

# إعداد السجلات (Logging)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("SaudiMerchantBot_Full_NoShortcuts")

# جلب المتغيرات
API_ID_RAW = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
SAMBANOVA_API_KEY = os.getenv("SAMBANOVA_API_KEY", "key")

# التحقق من المتغيرات
if not all([API_ID_RAW, API_HASH, BOT_TOKEN, MONGO_URI]):
    logger.critical("❌ خطأ: البيانات ناقصة في ملف .env")
    sys.exit(1)

API_ID = int(API_ID_RAW)

# إعداد عميل الذكاء الاصطناعي
try:
    ai_client = AsyncOpenAI(
        base_url="https://api.sambanova.ai/v1",
        api_key=SAMBANOVA_API_KEY
    )
    AI_MODEL = "Meta-Llama-3.1-405B-Instruct"
except Exception as e:
    ai_client = None

STRICT_RULE = "أنت تاجر سعودي محترف."

# ==============================================================================
#                               2. متغيرات الذاكرة (بدون اختصارات)
# ==============================================================================

# قائمة العملاء النشطين (Userbots)
active_userbot_clients = {}

# حالة المستخدم الحالية (لإدخال البيانات)
user_current_state = {}

# بيانات المهام المؤقتة
temporary_task_data = {}

# إعدادات النشر المؤقتة
temporary_autopost_config = {}

# آيدي آخر رسالة تم نشرها (للحذف عند الخطر)
last_published_message_ids = {}

# توقيت الردود (لمنع التكرار)
reply_cooldown_timestamps = {}

# 🔥 قائمة المهام النشطة (لمنع التكرار) 🔥
running_autopost_tasks = {} # {owner_id: asyncio.Task}

# ==============================================================================
#                               3. قاعدة البيانات
# ==============================================================================
try:
    mongo_client = AsyncIOMotorClient(MONGO_URI)
    database = mongo_client['MyTelegramBotDB']
    
    sessions_collection = database['sessions']
    replies_collection = database['replies']
    ai_settings_collection = database['ai_prompts']
    autopost_config_collection = database['autopost_config']
    paused_groups_collection = database['paused_groups']
    admins_watch_collection = database['admins_watch']
    subscriptions_collection = database['subscriptions']
    general_settings_collection = database['general_settings']
    
    print("✅ تم الاتصال بقاعدة البيانات بنجاح")
except Exception as e:
    logger.critical(f"DB Error: {e}")
    sys.exit(1)

# ==============================================================================
#                               4. الخادم والبوت
# ==============================================================================
bot_client = TelegramClient('bot_session', API_ID, API_HASH)

async def web_request_handler(request):
    return web.Response(text="Bot Running OK")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', web_request_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()

async def get_ai_response(messages_list):
    if not ai_client: return None
    try:
        response = await ai_client.chat.completions.create(
            model=AI_MODEL,
            messages=messages_list,
            temperature=0.7
        )
        return response.choices[0].message.content
    except: return None

# ==============================================================================
#                               5. إدارة اليوزربوت (Core Logic)
# ==============================================================================

async def start_userbot_session(owner_id, session_string):
    try:
        # إغلاق الجلسة السابقة
        if owner_id in active_userbot_clients:
            await active_userbot_clients[owner_id].disconnect()
        
        userbot = TelegramClient(StringSession(session_string), API_ID, API_HASH)
        await userbot.connect()
        
        if not await userbot.is_user_authorized():
            return False
        
        userbot.owner_id = owner_id
        userbot.cooldowns = {} 

        # --- تسجيل جميع المعالجات (Handlers) ---
        userbot.add_event_handler(lambda e: handle_auto_reply(userbot, e), events.NewMessage(incoming=True))
        userbot.add_event_handler(lambda e: handle_ai_chat(userbot, e), events.NewMessage(incoming=True))
        userbot.add_event_handler(lambda e: handle_safe_forced_join(userbot, e), events.NewMessage(incoming=True))
        userbot.add_event_handler(lambda e: handle_admin_freeze_trigger(userbot, e), events.NewMessage(incoming=True))
        userbot.add_event_handler(lambda e: handle_owner_resume_trigger(userbot, e), events.NewMessage(outgoing=True))
        
        active_userbot_clients[owner_id] = userbot
        
        # استعادة المهام (مع الحماية)
        await restart_autopost_task_safe(userbot, owner_id)
        
        # تشغيل المغادرة التلقائية
        asyncio.create_task(engine_auto_leave_channels(userbot, owner_id))
            
        return True
    except: return False

async def load_all_sessions_from_db():
    async for document in sessions_collection.find({}):
        asyncio.create_task(start_userbot_session(document['_id'], document['session_string']))

# 🔥 دالة منع التكرار (Task Killer) 🔥
async def restart_autopost_task_safe(client, owner_id):
    # 1. إيقاف المهمة القديمة
    if owner_id in running_autopost_tasks:
        old_task = running_autopost_tasks[owner_id]
        old_task.cancel()
        try:
            await old_task
        except asyncio.CancelledError:
            pass
        del running_autopost_tasks[owner_id]
        logger.info(f"تم إيقاف محرك النشر القديم للمستخدم {owner_id}")

    # 2. تشغيل المهمة الجديدة
    config = await autopost_config_collection.find_one({"owner_id": owner_id})
    if config and config.get('active', False):
        new_task = asyncio.create_task(engine_autopost_loop(client, owner_id))
        running_autopost_tasks[owner_id] = new_task
        logger.info(f"تم تشغيل محرك نشر جديد للمستخدم {owner_id}")

# ==============================================================================
#                               6. المعالجات (Handlers)
# ==============================================================================

async def handle_auto_reply(client, event):
    if not (event.is_private or event.is_group): return
    try:
        user_text = event.raw_text or ""
        cursor = replies_collection.find({"owner_id": client.owner_id})
        async for reply_doc in cursor:
            if reply_doc['keyword'] in user_text:
                # التحقق من الوقت (Cooldown)
                cooldown_key = (event.chat_id, event.sender_id, reply_doc['keyword'])
                last_time = reply_cooldown_timestamps.get(cooldown_key, 0)
                if time.time() - last_time < 600: return
                
                reply_cooldown_timestamps[cooldown_key] = time.time()
                await event.reply(reply_doc['reply'])
                return
    except: pass

async def handle_ai_chat(client, event):
    if not event.is_private: return
    try:
        settings = await ai_settings_collection.find_one({"owner_id": client.owner_id})
        if settings and settings.get('active'):
            if time.time() - client.cooldowns.get(event.chat_id, 0) > 5:
                async with client.action(event.chat_id, 'typing'): await asyncio.sleep(2)
                msgs = [{"role": "system", "content": STRICT_RULE}, {"role": "user", "content": event.raw_text}]
                ai_reply = await get_ai_response(msgs)
                if ai_reply: await event.reply(ai_reply)
                client.cooldowns[event.chat_id] = time.time()
    except: pass

# اشتراك آمن فقط (عند الرد عليك بكلمات حظر)
async def handle_safe_forced_join(client, event):
    try:
        if not (event.is_reply or event.mentioned): return
        reply_message = await event.get_reply_message()
        my_info = await client.get_me()
        if reply_message and reply_message.sender_id != my_info.id: return 

        text_content = event.raw_text.lower()
        forced_keywords = ["لايمكنك", "عليك الاشتراك", "must join", "غير مشترك", "join channel", "القناة"]
        
        if any(keyword in text_content for keyword in forced_keywords):
            targets_to_join = re.findall(r'(https?://t\.me/[^\s]+|@[a-zA-Z0-9_]{4,})', event.raw_text)
            if event.message.buttons:
                for row in event.message.buttons:
                    for btn in row:
                        if hasattr(btn, 'url') and btn.url and "t.me" in btn.url:
                            targets_to_join.append(btn.url)
            
            for target_link in targets_to_join:
                try:
                    clean_link = target_link.replace("https://t.me/", "").replace("@", "").strip()
                    if "+" in clean_link: await client(ImportChatInviteRequest(clean_link.split("+")[-1]))
                    else: await client(JoinChannelRequest(clean_link))
                    
                    try: 
                        entity = await client.get_entity(clean_link)
                        chat_id_to_save = entity.id
                    except: chat_id_to_save = clean_link
                        
                    await subscriptions_collection.update_one({"owner_id": client.owner_id, "chat_id": chat_id_to_save}, 
                        {"$set": {"join_time": time.time()}}, upsert=True)
                except: pass
    except: pass

# 🔥 تجميد النشر عند رد المشرف 🔥
async def handle_admin_freeze_trigger(client, event):
    if not (event.is_group and event.is_reply): return
    try:
        my_info = await client.get_me()
        reply_msg = await event.get_reply_message()
        
        # إذا الرد مو علي، اطلع
        if reply_msg.sender_id != my_info.id: return
        
        sender = await event.get_sender()
        perms = await client.get_permissions(event.chat_id, sender)
        
        # إذا كان أدمن
        if perms.is_admin or perms.is_creator:
            await paused_groups_collection.update_one(
                {"owner_id": client.owner_id, "chat_id": event.chat_id},
                {"$set": {"admin_id": sender.id}},
                upsert=True
            )
            await client.send_message("me", f"⛔ **تم إيقاف النشر في الجروب:** {event.chat.title}\nالسبب: رد عليك المشرف.")
    except: pass

# 🔥 فك التجميد عند رد المالك 🔥
async def handle_owner_resume_trigger(client, event):
    if not (event.is_group and event.is_reply): return
    try:
        paused_data = await paused_groups_collection.find_one({"owner_id": client.owner_id, "chat_id": event.chat_id})
        if not paused_data: return
        
        replied_to_msg = await event.get_reply_message()
        # إذا رديت على نفس الأدمن
        if replied_to_msg.sender_id == paused_data['admin_id']:
            await paused_groups_collection.delete_one({"_id": paused_data['_id']})
            await client.send_message("me", f"✅ **تم استئناف النشر في:** {event.chat.title}")
    except: pass

# ==============================================================================
#                               7. المحركات الخلفية (Engines)
# ==============================================================================

async def engine_autopost_loop(client, owner_id):
    logger.info(f"بدء النشر للمستخدم {owner_id}")
    while True:
        try:
            # التحقق من الإلغاء
            try: asyncio.current_task().cancelled()
            except: pass

            config = await autopost_config_collection.find_one({"owner_id": owner_id})
            if not config or not config.get('active', False): break
            
            for group_id in config['groups']:
                # 1. هل الجروب مجمد؟
                if await paused_groups_collection.find_one({"owner_id": owner_id, "chat_id": group_id}): 
                    continue
                
                # 2. هل المشرف متصل؟
                is_danger = False
                async for admin_doc in admins_watch_collection.find({"owner_id": owner_id}):
                    try:
                        admin_entity = await client.get_entity(admin_doc['username'])
                        if isinstance(admin_entity.status, (UserStatusOnline, UserStatusRecently)):
                            is_danger = True; break
                    except: pass
                
                if is_danger:
                    last_msg = last_published_message_ids.get(f"{owner_id}_{group_id}")
                    if last_msg: 
                        try: await client.delete_messages(group_id, [last_msg])
                        except: pass
                    await asyncio.sleep(300); continue

                # 3. النشر
                try:
                    sent_message = await client.send_message(int(group_id), config['message'])
                    last_published_message_ids[f"{owner_id}_{group_id}"] = sent_message.id
                    await asyncio.sleep(5)
                except FloodWaitError as f: await asyncio.sleep(f.seconds)
                except: pass
            
            await asyncio.sleep(config['interval'] * 60)
        except asyncio.CancelledError: break
        except: await asyncio.sleep(60)

async def engine_auto_leave_channels(client, owner_id):
    while True:
        try:
            current_timestamp = time.time()
            async for sub in subscriptions_collection.find({"owner_id": owner_id}):
                if current_timestamp - sub['join_time'] > 86400:
                    try:
                        target_id = sub['chat_id']
                        try: target_id = int(target_id)
                        except: pass
                        await client(LeaveChannelRequest(target_id))
                        await subscriptions_collection.delete_one({"_id": sub['_id']})
                    except: pass
        except: pass
        await asyncio.sleep(3600)

# 🔥 محرك البرودكاست المطور (يدعم الصور) 🔥
async def engine_broadcast_sender(client, status_message, source_message_object):
    count_sent = 0
    try:
        async for dialog in client.iter_dialogs():
            if dialog.is_user and not dialog.entity.bot:
                try:
                    # نرسل كائن الرسالة كاملاً (يدعم الصور والملفات)
                    await client.send_message(dialog.id, source_message_object)
                    count_sent += 1
                    await asyncio.sleep(1)
                except: pass
    except: pass
    await status_message.edit(f"✅ **تم الانتهاء.**\nتم الإرسال لـ: `{count_sent}`")

async def engine_search_task(client, status_msg, hours, keyword, reply_text, delay):
    count = 0; limit_time = time.time() - (hours * 3600); replied_users = set()
    try:
        my_info = await client.get_me()
        async for dialog in client.iter_dialogs():
            if dialog.is_group:
                async for msg in client.iter_messages(dialog.id, search=keyword, limit=20):
                    if msg.date.timestamp() > limit_time and msg.sender_id != my_info.id:
                        if msg.sender_id in replied_users: continue
                        try:
                            await client.send_message(dialog.id, reply_text, reply_to=msg.id)
                            replied_users.add(msg.sender_id)
                            count += 1
                            await asyncio.sleep(delay)
                        except: pass
    except: pass
    await status_msg.reply(f"✅ تم الرد على {count} رسالة.")

# ==============================================================================
#                               8. واجهة المستخدم (القوائم)
# ==============================================================================

@bot_client.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    chat_id = event.chat_id
    
    if chat_id in active_userbot_clients:
        config = await autopost_config_collection.find_one({"owner_id": chat_id})
        status_post = "🟢" if config and config.get('active') else "🔴"
        
        buttons = [
            [Button.inline(f"📢 النشر التلقائي {status_post}", b"menu_autopost")],
            [Button.inline("📨 برودكاست (صور/نص)", b"broadcast_menu")],
            [Button.inline("📋 الردود", b"list_replies"), Button.inline("👮 الرادار", b"menu_radar")],
            [Button.inline("🚀 مهام بحث", b"menu_tasks"), Button.inline("🤖 ذكاء", b"toggle_ai")],
            [Button.inline("📊 إحصائيات", b"view_stats"), Button.inline("🗑️ تنظيف القنوات", b"clean_channels")]
        ]
        await event.respond("✅ **لوحة التحكم الكاملة**", buttons=buttons)
    else:
        await event.respond("🔒", buttons=[[Button.inline("تسجيل الدخول", b"login")]])

@bot_client.on(events.CallbackQuery)
async def callback_handler(event):
    chat_id = event.chat_id
    data = event.data
    client = active_userbot_clients.get(chat_id)

    # 🔥 كاشف الصمت: تنبيه إذا لم يسجل الدخول 🔥
    if not client and data != b"login":
        await event.answer("⚠️ يجب تسجيل الدخول أولاً!", alert=True)
        return

    await event.answer()

    if data == b"login":
        user_current_state[chat_id] = "WAITING_SESSION"
        await event.respond("🔐 **أرسل كود الجلسة (Session String):**")

    elif data == b"clean_channels":
        await event.respond("🧹 **جاري المغادرة...**")
        asyncio.create_task(engine_auto_leave_channels(client, chat_id))

    elif data == b"menu_autopost":
        conf = await autopost_config_collection.find_one({"owner_id": chat_id})
        msg_prev = conf.get('message', 'لا يوجد')[:20] if conf else "لا يوجد"
        btns = [
            [Button.inline("⚙️ إعداد جديد", b"setup_post")],
            [Button.inline("⏯️ تشغيل/إيقاف", b"toggle_post")],
            [Button.inline("🗑️ حذف الإعدادات", b"delete_autopost_settings")],
            [Button.inline("👁️ عرض المنشور", b"view_current_post")],
            [Button.inline("🔙 رجوع", b"back_home")]
        ]
        await event.respond(f"📢 **النشر التلقائي**\nالرسالة: `{msg_prev}`", buttons=btns)

    elif data == b"view_current_post":
        conf = await autopost_config_collection.find_one({"owner_id": chat_id})
        await event.respond(f"📝 **الرسالة:**\n\n{conf['message']}" if conf else "❌ لا توجد رسالة")

    elif data == b"delete_autopost_settings":
        await autopost_config_collection.delete_one({"owner_id": chat_id})
        if chat_id in running_autopost_tasks:
            running_autopost_tasks[chat_id].cancel()
            del running_autopost_tasks[chat_id]
        await event.respond("🗑️ **تم الحذف والإيقاف.**")

    elif data == b"setup_post":
        user_current_state[chat_id] = "WAITING_POST_MSG"
        await event.respond("📝 **أرسل الرسالة التي تريد نشرها:**")
    
    elif data == b"toggle_post":
        conf = await autopost_config_collection.find_one({"owner_id": chat_id})
        if not conf:
            await event.respond("❌ قم بالإعداد أولاً")
            return
        
        new_status = not conf.get('active', False)
        await autopost_config_collection.update_one({"owner_id": chat_id}, {"$set": {"active": new_status}}, upsert=True)
        await restart_autopost_task_safe(client, chat_id)
        await event.respond(f"✅ الحالة الآن: {'🟢 يعمل' if new_status else '🔴 متوقف'}")

    elif data == b"broadcast_menu":
        user_current_state[chat_id] = "WAITING_BROADCAST_MSG"
        await event.respond("📨 **أرسل الرسالة (صورة/فيديو/نص) التي تريد نشرها للخاص:**")

    elif data == b"list_replies":
        btns = []
        async for r in replies_collection.find({"owner_id": chat_id}):
            btns.append([Button.inline(f"🗑️ حذف: {r['keyword']}", f"del_rep_{r['_id']}")])
        btns.append([Button.inline("➕ إضافة رد", b"add_reply")])
        btns.append([Button.inline("🔙 رجوع", b"back_home")])
        await event.respond("📋 **الردود:**", buttons=btns)

    elif data == b"add_reply":
        user_current_state[chat_id] = "WAITING_REPLY_KEY"
        await event.respond("📝 **أرسل الكلمة المفتاحية:**")

    elif data.decode().startswith("del_rep_"):
        await replies_collection.delete_one({"_id": ObjectId(data.decode().split("_")[2])})
        await event.respond("✅ تم الحذف.")

    elif data == b"menu_radar":
        msg = "👮 **المراقبين:**\n"
        async for x in admins_watch_collection.find({"owner_id": chat_id}): msg += f"- {x['username']}\n"
        await event.respond(msg, buttons=[[Button.inline("➕ إضافة", b"add_radar"), Button.inline("🗑️ حذف", b"del_radar")], [Button.inline("🔙", b"back_home")]])
    
    elif data == b"add_radar": user_current_state[chat_id]="WAITING_RADAR_ADD"; await event.respond("👤 **اليوزر:**")
    elif data == b"del_radar": user_current_state[chat_id]="WAITING_RADAR_DEL"; await event.respond("👤 **اليوزر:**")

    elif data == b"menu_tasks": user_current_state[chat_id]="WAITING_TASK_HOURS"; TASK_DATA[chat_id]={}; await event.respond("1️⃣ **عدد الساعات:**")
    
    elif data == b"toggle_ai":
        curr = await ai_settings_collection.find_one({"owner_id": chat_id})
        new_w = not curr.get('active') if curr else True
        await ai_settings_collection.update_one({"owner_id": chat_id}, {"$set": {"active": new_w}}, upsert=True)
        await event.respond(f"🤖 الذكاء: {'🟢' if new_w else '🔴'}")
    
    elif data == b"back_home": await start_handler(event)
    elif data == b"view_stats":
        if client:
            d = await client.get_dialogs()
            await event.respond(f"📊 **عدد المحادثات:** {len(d)}")

@bot_client.on(events.NewMessage)
async def input_message_handler(event):
    chat_id = event.chat_id
    user_text = event.text.strip()
    state = user_current_state.get(chat_id)
    
    if not state: return

    # تسجيل الدخول
    if state == "WAITING_SESSION":
        if await start_userbot_session(chat_id, user_text):
            await sessions_collection.update_one({"_id": chat_id}, {"$set": {"session_string": user_text}}, upsert=True)
            await event.respond("✅ **تم الدخول!**")
            await start_handler(event)
        else: await event.respond("❌ كود خطأ.")
        user_current_state[chat_id]=None

    # برودكاست (الآن يدعم الصور)
    elif state == "WAITING_BROADCAST_MSG":
        status_msg = await event.respond("⏳ **جاري النشر...**")
        asyncio.create_task(engine_broadcast_sender(active_userbot_clients[chat_id], status_msg, event.message))
        user_current_state[chat_id] = None

    # إعدادات النشر
    elif state == "WAITING_POST_MSG":
        temporary_autopost_config[chat_id] = {'msg': user_text}
        user_current_state[chat_id] = "WAITING_POST_TIME"
        await event.respond("✅ **تم حفظ النص.**\nأرسل الآن: **كم دقيقة الانتظار؟**")
    
    elif state == "WAITING_POST_TIME":
        try:
            temporary_autopost_config[chat_id]['time'] = int(user_text)
            user_current_state[chat_id] = "WAITING_POST_GROUPS"
            btns = []
            cli = active_userbot_clients[chat_id]
            async for d in cli.iter_dialogs(limit=30): 
                if d.is_group: btns.append([Button.inline(d.name[:20], f"grp_{d.id}")])
            btns.append([Button.inline("✅ حفظ وبدء", "save_autopost_final")])
            temporary_autopost_config[chat_id]['groups'] = []
            await event.respond("✅ **تم حفظ الوقت.**\n📂 **اختر الجروبات:**", buttons=btns)
        except: 
            await event.respond("❌ أرسل رقماً صحيحاً.")

    elif state == "WAITING_REPLY_KEY":
        TASK_DATA[chat_id] = {'k': user_text}
        user_current_state[chat_id] = "WAITING_REPLY_VAL"
        await event.respond("📝 **الرد:**")
    elif state == "WAITING_REPLY_VAL":
        await replies_collection.update_one({"owner_id": chat_id, "keyword": TASK_DATA[chat_id]['k']}, {"$set": {"reply": user_text}}, upsert=True)
        await event.respond("✅ **تم الحفظ**")
        user_current_state[chat_id]=None

    elif state == "WAITING_RADAR_ADD":
        await admins_watch_collection.update_one({"owner_id": chat_id, "username": user_text.replace("@","")}, {"$set": {"ts":time.time()}}, upsert=True)
        await event.respond("✅"); user_current_state[chat_id]=None
    elif state == "WAITING_RADAR_DEL":
        await admins_watch_collection.delete_one({"owner_id": chat_id, "username": user_text.replace("@","")})
        await event.respond("🗑️"); user_current_state[chat_id]=None

    elif state == "WAITING_TASK_HOURS": TASK_DATA[chat_id]={'h':int(user_text)}; user_current_state[chat_id]="WAITING_TASK_KEY"; await event.respond("كلمة البحث:")
    elif state == "WAITING_TASK_KEY": TASK_DATA[chat_id]['k']=user_text; user_current_state[chat_id]="WAITING_TASK_REP"; await event.respond("الرد:")
    elif state == "WAITING_TASK_REP": TASK_DATA[chat_id]['r']=event.message; user_current_state[chat_id]="WAITING_TASK_DELAY"; await event.respond("ثواني الانتظار:")
    elif state == "WAITING_TASK_DELAY":
        msg = await event.respond("🚀")
        asyncio.create_task(engine_search_task(active_userbot_clients[chat_id], msg, TASK_DATA[chat_id]['h'], TASK_DATA[chat_id]['k'], TASK_DATA[chat_id]['r'], int(user_text)))
        user_current_state[chat_id]=None

@bot_client.on(events.CallbackQuery(pattern=r'grp_'))
async def group_select(event):
    chat_id = event.chat_id
    group_id = int(event.data.decode().split('_')[1])
    l = temporary_autopost_config.get(chat_id, {}).get('groups', [])
    if group_id not in l: l.append(group_id); await event.answer("✅")
    else: l.remove(group_id); await event.answer("❌")
    temporary_autopost_config[chat_id]['groups'] = l

@bot_client.on(events.CallbackQuery(pattern=b'save_autopost_final'))
async def save_autopost_final(event):
    chat_id = event.chat_id
    d = temporary_autopost_config.get(chat_id)
    if not d or not d.get('groups'): return await event.respond("❌ اختر جروب")
    
    await autopost_config_collection.update_one({"owner_id": chat_id}, {"$set": {"message": d['msg'], "interval": d['time'], "groups": d['groups'], "active": True}}, upsert=True)
    await restart_autopost_task_safe(active_userbot_clients[chat_id], chat_id)
    await event.respond("✅ **تم الحفظ وبدء النشر!**")
    user_current_state[chat_id] = None

# ==============================================================================
#                               9. التشغيل
# ==============================================================================
async def main():
    await start_web_server()
    await load_all_sessions_from_db()
    print("✅ Bot Started Final Full")
    await bot_client.start(bot_token=BOT_TOKEN)
    await bot_client.run_until_disconnected()

if __name__ == '__main__':
    try: loop = asyncio.get_event_loop(); loop.run_until_complete(main())
    except: pass
