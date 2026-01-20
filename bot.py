import os
import sys
import asyncio
import logging
import time
import re
import traceback
from datetime import datetime

# استيراد مكاتب التعامل مع معرفات قاعدة البيانات
from bson.objectid import ObjectId

# استيراد مكاتب التيليجرام الأساسية
from telethon import TelegramClient, events, Button, functions, types
from telethon.sessions import StringSession
from telethon.tl.types import UserStatusOnline, UserStatusRecently
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.functions.channels import JoinChannelRequest, LeaveChannelRequest
from telethon.errors import FloodWaitError, UserNotParticipantError

# استيراد محرك قاعدة البيانات
from motor.motor_asyncio import AsyncIOMotorClient

# استيراد خادم الويب
from aiohttp import web

# استيراد الذكاء الاصطناعي
from openai import AsyncOpenAI

# استيراد ملفات البيئة
from dotenv import load_dotenv

# ==============================================================================
#                               1. إعدادات النظام والبيئة
# ==============================================================================

# تحميل المتغيرات من ملف .env
load_dotenv()

# تهيئة نظام السجلات (Logs) بتفصيل عالي
logging.basicConfig(
    format='[%(asctime)s] %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("SaudiMerchantBot_Full")

# جلب المتغيرات الحساسة
API_ID_RAW = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
SAMBANOVA_API_KEY = os.getenv("SAMBANOVA_API_KEY", "b1818ac7-46d5-4d95-bf75-8ad864b0b8de")

# التحقق الصارم من المتغيرات
if not all([API_ID_RAW, API_HASH, BOT_TOKEN, MONGO_URI]):
    logger.critical("❌ خطأ قاتل: أحد المتغيرات الأساسية مفقود.")
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
#                               2. متغيرات الذاكرة
# ==============================================================================
active_clients = {}
USER_STATE = {}
TASK_DATA = {}
AUTO_POST_CONFIG = {}
LAST_MSG_IDS = {}
REPLY_COOLDOWN = {}

# ==============================================================================
#                               3. الاتصال بقاعدة البيانات
# ==============================================================================
try:
    mongo_client = AsyncIOMotorClient(MONGO_URI)
    db = mongo_client['MyTelegramBotDB']
    
    sessions_col = db['sessions']
    replies_col = db['replies']
    reactions_col = db['reactions']
    ai_settings_col = db['ai_prompts']
    config_col = db['autopost_config']
    paused_groups_col = db['paused_groups']
    admins_watch_col = db['admins_watch']
    subs_col = db['subscriptions']
    
    logger.info("✅ تم الاتصال بقاعدة البيانات MongoDB بنجاح.")
except Exception as e:
    logger.critical(f"❌ فشل الاتصال بقاعدة البيانات: {e}")
    sys.exit(1)

# ==============================================================================
#                               4. خادم الويب
# ==============================================================================
bot = TelegramClient('bot_session', API_ID, API_HASH)

async def web_handler(request):
    return web.Response(text=f"Bot Status: Online\nActive: {len(active_clients)}")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', web_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()

# ==============================================================================
#                               5. دوال المساعدة
# ==============================================================================
async def ask_smart_ai(messages_history):
    if not ai_client: return None
    try:
        response = await ai_client.chat.completions.create(
            model=AI_MODEL,
            messages=messages_history,
            temperature=0.7,
            top_p=0.9
        )
        return response.choices[0].message.content
    except: return None

# ==============================================================================
#                               6. إدارة اليوزربوت
# ==============================================================================
async def start_userbot(owner_id, session_str):
    try:
        if owner_id in active_clients:
            await active_clients[owner_id].disconnect()
        
        client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
        await client.connect()
        
        if not await client.is_user_authorized():
            await sessions_col.delete_one({"_id": owner_id})
            return False
        
        client.owner_id = owner_id
        client.cooldowns = {} 

        # ---------------- تسجيل المعالجات (Handlers) ----------------
        
        # 1. الرد التلقائي
        client.add_event_handler(
            lambda e: process_auto_reply(client, e),
            events.NewMessage(incoming=True)
        )
        
        # 2. الذكاء الاصطناعي
        client.add_event_handler(
            lambda e: process_ai_chat(client, e),
            events.NewMessage(incoming=True)
        )
        
        # 3. الاشتراك الإجباري الآمن (فقط عند الضرورة)
        client.add_event_handler(
            lambda e: process_safe_forced_join(client, e),
            events.NewMessage(incoming=True)
        )
        
        # 4. تجميد النشر (رد الأدمن)
        client.add_event_handler(
            lambda e: process_admin_freeze(client, e),
            events.NewMessage(incoming=True)
        )
        
        # 5. فك التجميد (رد المالك)
        client.add_event_handler(
            lambda e: process_owner_resume(client, e),
            events.NewMessage(outgoing=True)
        )
        
        active_clients[owner_id] = client
        
        # تشغيل المحركات الخلفية
        asyncio.create_task(engine_autopost(client, owner_id))
        asyncio.create_task(engine_autoleave(client, owner_id))
        
        return True
    except Exception as e:
        logger.error(f"Error starting userbot: {e}")
        return False

async def load_all_sessions():
    async for doc in sessions_col.find({}):
        asyncio.create_task(start_userbot(doc['_id'], doc['session_string']))

# ==============================================================================
#                               7. تفاصيل المعالجات
# ==============================================================================

# --- 1. الرد التلقائي ---
async def process_auto_reply(client, event):
    if not event.is_private and not event.is_group: return
    try:
        text = event.raw_text or ""
        cursor = replies_col.find({"owner_id": client.owner_id})
        async for rule in cursor:
            if rule['keyword'] in text:
                key = (event.chat_id, event.sender_id, rule['keyword'])
                if time.time() - REPLY_COOLDOWN.get(key, 0) < 600: return
                REPLY_COOLDOWN[key] = time.time()
                await event.reply(rule['reply'])
                return
    except: pass

# --- 2. الذكاء الاصطناعي ---
async def process_ai_chat(client, event):
    if not event.is_private: return
    try:
        settings = await ai_settings_col.find_one({"owner_id": client.owner_id})
        if not settings or not settings.get('active', False): return
        
        if time.time() - client.cooldowns.get(event.chat_id, 0) > 5:
            async with client.action(event.chat_id, 'typing'):
                await asyncio.sleep(2)
            
            msgs = [
                {"role": "system", "content": f"{STRICT_RULE}\n{settings.get('prompt', '')}"},
                {"role": "user", "content": event.raw_text or "."}
            ]
            ai_reply = await ask_smart_ai(msgs)
            if ai_reply: await event.reply(ai_reply)
            client.cooldowns[event.chat_id] = time.time()
    except: pass

# --- 3. الاشتراك الإجباري الآمن (Safe Forced Join) ---
async def process_safe_forced_join(client, event):
    """
    هذا الكود لا يشترك إلا إذا كان هناك رد مباشر عليك
    يخبرك بأنك محظور أو يجب عليك الاشتراك.
    """
    try:
        # الشرط الأول: هل الرسالة رد علي أو منشن لي؟
        if not (event.is_reply or event.mentioned):
            return 
        
        # الشرط الثاني: التحقق من أن الرد موجه لرسالتي
        reply_message = await event.get_reply_message()
        me = await client.get_me()
        if reply_message and reply_message.sender_id != me.id:
            return # الرد ليس علي، تجاهل فوراً

        text = event.raw_text.lower()
        
        # الشرط الثالث: كلمات الاشتراك الإجباري فقط
        forced_triggers = [
            "لايمكنك", "لا يمكنك", "عليك الاشتراك", "must join", "subscribe to", 
            "join channel", "غير مشترك", "اشترك في", "not a participant", 
            "subscription", "bot channel", "قناة البوت", "عذراً"
        ]
        
        if not any(k in text for k in forced_triggers):
            return # ليس طلب اشتراك
        
        # استخراج الأهداف (الروابط)
        targets_to_join = []
        
        # أ. من النص
        links = re.findall(r'(https?://t\.me/[^\s]+|@[a-zA-Z0-9_]{4,})', event.raw_text)
        targets_to_join.extend(links)
        
        # ب. من الأزرار (مهم جداً للبوتات)
        if event.message.buttons:
            for row in event.message.buttons:
                for btn in row:
                    if hasattr(btn, 'url') and btn.url and "t.me" in btn.url:
                        targets_to_join.append(btn.url)
        
        # تنفيذ الاشتراك
        for target in targets_to_join:
            try:
                final_target = target.replace("https://t.me/", "").replace("@", "").strip()
                
                if "+" in final_target:
                    await client(ImportChatInviteRequest(final_target.split("+")[-1]))
                else:
                    await client(JoinChannelRequest(final_target))
                
                # حفظ للمغادرة
                try: 
                    entity = await client.get_entity(final_target)
                    chat_id_save = entity.id
                except: chat_id_save = final_target

                await subs_col.update_one(
                    {"owner_id": client.owner_id, "chat_id": chat_id_save},
                    {"$set": {"join_time": time.time()}},
                    upsert=True
                )
                logger.info(f"✅ تم حل مشكلة الاشتراك الإجباري: {final_target}")
            except: pass
            
    except: pass

# --- 4. تجميد النشر (Admin Freeze) ---
async def process_admin_freeze(client, event):
    if not event.is_group or not event.is_reply: return
    try:
        me = await client.get_me()
        reply_msg = await event.get_reply_message()
        if reply_msg.sender_id != me.id: return
        
        sender = await event.get_sender()
        perms = await client.get_permissions(event.chat_id, sender)
        
        if perms.is_admin or perms.is_creator:
            await paused_groups_col.update_one(
                {"owner_id": client.owner_id, "chat_id": event.chat_id},
                {"$set": {"admin_id": sender.id, "ts": time.time()}},
                upsert=True
            )
            await client.send_message("me", f"⛔ **توقف النشر في:** {event.chat.title}\nالسبب: رد عليك المشرف.")
    except: pass

# --- 5. فك التجميد (Owner Resume) ---
async def process_owner_resume(client, event):
    if not event.is_group or not event.is_reply: return
    try:
        paused_data = await paused_groups_col.find_one({"owner_id": client.owner_id, "chat_id": event.chat_id})
        if not paused_data: return
        
        reply_msg = await event.get_reply_message()
        if reply_msg.sender_id == paused_data.get('admin_id'):
            await paused_groups_col.delete_one({"owner_id": client.owner_id, "chat_id": event.chat_id})
            await client.send_message("me", f"✅ **تم استئناف النشر في:** {event.chat.title}")
    except: pass

# ==============================================================================
#                               8. المحركات الخلفية
# ==============================================================================

async def engine_autopost(client, owner_id):
    logger.info(f"بدء محرك النشر للمستخدم {owner_id}")
    while True:
        try:
            config = await config_col.find_one({"owner_id": owner_id})
            if not config or not config.get('active', False):
                await asyncio.sleep(60)
                continue
            
            for group_id in config['groups']:
                # فحص التجميد
                if await paused_groups_col.find_one({"owner_id": owner_id, "chat_id": group_id}):
                    continue
                
                # فحص الرادار
                danger = False
                async for admin in admins_watch_col.find({"owner_id": owner_id}):
                    try:
                        user = await client.get_entity(admin['username'])
                        if isinstance(user.status, (UserStatusOnline, UserStatusRecently)):
                            danger = True; break
                    except: pass
                
                if danger:
                    last = LAST_MSG_IDS.get(f"{owner_id}_{group_id}")
                    if last:
                        try: await client.delete_messages(group_id, [last])
                        except: pass
                    await asyncio.sleep(300)
                    continue

                try:
                    sent = await client.send_message(int(group_id), config['message'])
                    LAST_MSG_IDS[f"{owner_id}_{group_id}"] = sent.id
                    await asyncio.sleep(5)
                except FloodWaitError as e: await asyncio.sleep(e.seconds)
                except: pass
            
            await asyncio.sleep(config['interval'] * 60)
        except: await asyncio.sleep(60)

async def engine_autoleave(client, owner_id):
    while True:
        try:
            now = time.time()
            async for sub in subs_col.find({"owner_id": owner_id}):
                if now - sub['join_time'] > 86400:
                    try:
                        tid = sub['chat_id']
                        try: tid = int(tid)
                        except: pass
                        await client(LeaveChannelRequest(tid))
                        await subs_col.delete_one({"_id": sub['_id']})
                    except: pass
        except: pass
        await asyncio.sleep(3600)

async def engine_task_runner(client, status_msg, hours, keyword, reply_msg, delay):
    count = 0
    start_time = time.time() - (hours * 3600)
    replied_cache = set()
    
    try:
        me = await client.get_me()
        async for dialog in client.iter_dialogs():
            if dialog.is_group:
                async for message in client.iter_messages(dialog.id, limit=30, search=keyword):
                    if message.date.timestamp() > start_time and message.sender_id != me.id:
                        if message.sender_id in replied_cache: continue
                        try:
                            await client.send_message(dialog.id, reply_msg, reply_to=message.id)
                            replied_cache.add(message.sender_id)
                            count += 1
                            await asyncio.sleep(delay)
                        except: pass
    except: pass
    await status_msg.reply(f"✅ انتهت المهمة. تم الرد على: {count}")

# ==============================================================================
#                               9. واجهة المستخدم
# ==============================================================================

@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    await show_dashboard(event)

async def show_dashboard(event):
    cid = event.chat_id
    if cid in active_clients and await active_clients[cid].is_user_authorized():
        conf = await config_col.find_one({"owner_id": cid})
        st_post = "🟢 يعمل" if conf and conf.get('active') else "🔴 متوقف"
        
        btns = [
            [Button.inline(f"📢 النشر التلقائي: {st_post}", b"menu_autopost")],
            [Button.inline("📋 الردود المحفوظة", b"list_replies"), Button.inline("➕ إضافة رد", b"add_reply")],
            [Button.inline("👮 رادار المشرفين", b"menu_radar"), Button.inline("⛔ الجروبات المجمدة", b"menu_paused")],
            [Button.inline("🚀 مهام البحث", b"menu_task"), Button.inline("🤖 الذكاء", b"toggle_ai")],
            [Button.inline("🗑️ تنظيف القنوات المؤقتة", b"force_clean")]
        ]
        await event.respond("✅ **لوحة التحكم الآمنة**", buttons=btns)
    else:
        await event.respond("🔒 يرجى تسجيل الدخول.", buttons=[[Button.inline("تسجيل الدخول", b"login")]])

@bot.on(events.CallbackQuery)
async def callback_handler(event):
    cid = event.chat_id
    data = event.data
    client = active_clients.get(cid)

    if data == b"login":
        USER_STATE[cid] = "SESS"
        await event.respond("🔐 **أرسل كود الجلسة (Session String):**")

    elif data == b"force_clean":
        await event.respond("🧹 **جاري مغادرة القنوات التي دخلها البوت سابقاً...**")
        asyncio.create_task(engine_autoleave(client, cid))

    elif data == b"list_replies":
        btns = []
        async for r in replies_col.find({"owner_id": cid}):
            btns.append([Button.inline(f"🗑️ حذف: {r['keyword']}", f"del_rep_{r['_id']}")])
        btns.append([Button.inline("🔙 رجوع", b"back")])
        await event.respond("📋 **قائمة الردود:**", buttons=btns)

    elif data.decode().startswith("del_rep_"):
        rid = data.decode().split("_")[2]
        await replies_col.delete_one({"_id": ObjectId(rid)})
        await event.answer("تم الحذف")
        await event.respond("✅ تم الحذف.")

    elif data == b"back": await show_dashboard(event)

    elif data == b"menu_autopost":
        await event.respond("📢 **النشر التلقائي:**", buttons=[
            [Button.inline("إعداد رسالة جديدة", b"setup_post")],
            [Button.inline("تشغيل / إيقاف", b"toggle_post")]
        ])
    elif data == b"setup_post":
        USER_STATE[cid] = "SET_MSG"
        await event.respond("📝 **أرسل الرسالة:**")
    elif data == b"toggle_post":
        c = await config_col.find_one({"owner_id": cid})
        n = not c.get('active', False) if c else False
        await config_col.update_one({"owner_id": cid}, {"$set": {"active": n}}, upsert=True)
        if n: asyncio.create_task(engine_autopost(client, cid))
        await event.respond(f"✅ الحالة: {n}")

    elif data == b"menu_radar":
        s = "👮 **المراقبين:**\n"
        async for d in admins_watch_col.find({"owner_id": cid}): s += f"- {d['username']}\n"
        await event.respond(s, buttons=[[Button.inline("➕ إضافة", b"add_w"), Button.inline("🗑️ حذف", b"del_w")]])
    elif data == b"add_w": USER_STATE[cid] = "ADD_W"; await event.respond("👤 **اليوزر:**")
    elif data == b"del_w": USER_STATE[cid] = "DEL_W"; await event.respond("👤 **اليوزر:**")

    elif data == b"add_reply": USER_STATE[cid] = "ADD_K"; await event.respond("📝 **الكلمة المفتاحية:**")
    
    elif data == b"menu_task": USER_STATE[cid] = "TASK_H"; TASK_DATA[cid]={}; await event.respond("1️⃣ **عدد الساعات:**")
    
    elif data == b"toggle_ai":
        cur = await ai_settings_col.find_one({"owner_id": cid})
        nw = not cur.get('active') if cur else True
        await ai_settings_col.update_one({"owner_id": cid}, {"$set": {"active": nw}}, upsert=True)
        await event.respond(f"🤖 الذكاء: {nw}")

    elif data == b"menu_paused":
        await paused_groups_col.delete_many({"owner_id": cid})
        await event.respond("✅ **تم فك الحظر عن جميع الجروبات.**")

@bot.on(events.NewMessage)
async def input_handler(event):
    cid = event.chat_id
    txt = event.text.strip()
    st = USER_STATE.get(cid)
    if not st or txt.startswith('/'): return

    if st == "SESS":
        if await start_userbot(cid, txt):
            await sessions_col.update_one({"_id": cid}, {"$set": {"session_string": txt}}, upsert=True)
            await event.respond("✅ **تم الدخول!**")
            await show_dashboard(event)
        else: await event.respond("❌ كود خطأ.")
        USER_STATE[cid] = None

    elif st == "ADD_K":
        TASK_DATA[cid] = {"k": txt}
        USER_STATE[cid] = "ADD_V"
        await event.respond("📝 **الرد:**")
    elif st == "ADD_V":
        await replies_col.update_one({"owner_id": cid, "keyword": TASK_DATA[cid]['k']}, {"$set": {"reply": txt}}, upsert=True)
        await event.respond("✅ **تم الحفظ.**")
        USER_STATE[cid] = None

    elif st == "ADD_W":
        await admins_watch_col.update_one({"owner_id": cid, "username": txt.replace("@","")}, {"$set": {"ts": time.time()}}, upsert=True)
        await event.respond("✅"); USER_STATE[cid] = None
    elif st == "DEL_W":
        await admins_watch_col.delete_one({"owner_id": cid, "username": txt.replace("@","")})
        await event.respond("🗑️"); USER_STATE[cid] = None

    elif st == "SET_MSG":
        AUTO_POST_CONFIG[cid] = {'msg': txt}
        USER_STATE[cid] = "SET_TM"
        await event.respond("⏱️ **الدقائق:**")
    elif st == "SET_TM":
        try:
            AUTO_POST_CONFIG[cid]['time'] = int(txt)
            USER_STATE[cid] = "SET_GP"
            btns = []
            cli = active_clients[cid]
            async for d in cli.iter_dialogs(limit=30):
                if d.is_group: btns.append([Button.inline(d.name[:20], f"g_{d.id}")])
            btns.append([Button.inline("✅ حفظ", "save_post")])
            AUTO_POST_CONFIG[cid]['groups'] = []
            await event.respond("📂 **اختر الجروبات:**", buttons=btns)
        except: pass

    elif st == "TASK_H":
        try:
            TASK_DATA[cid] = {'h': int(txt)}
            USER_STATE[cid] = "TASK_K"
            await event.respond("🔎 **كلمة البحث:**")
        except: pass
    elif st == "TASK_K":
        TASK_DATA[cid]['k'] = txt
        USER_STATE[cid] = "TASK_R"
        await event.respond("📝 **الرد:**")
    elif st == "TASK_R":
        TASK_DATA[cid]['r'] = event.message
        USER_STATE[cid] = "TASK_D"
        await event.respond("⏱️ **ثواني الانتظار:**")
    elif st == "TASK_D":
        try:
            delay = int(txt)
            msg = await event.respond("🚀 **جاري التنفيذ...**")
            asyncio.create_task(engine_task_runner(active_clients[cid], msg, TASK_DATA[cid]['h'], TASK_DATA[cid]['k'], TASK_DATA[cid]['r'], delay))
            USER_STATE[cid] = None
        except: pass

@bot.on(events.CallbackQuery(pattern=r'g_'))
async def gp_sel(event):
    cid = event.chat_id
    gid = int(event.data.decode().split('_')[1])
    l = AUTO_POST_CONFIG.get(cid, {}).get('groups', [])
    if gid not in l: l.append(gid); await event.answer("✅")
    else: l.remove(gid); await event.answer("❌")
    AUTO_POST_CONFIG[cid]['groups'] = l

@bot.on(events.CallbackQuery(pattern=b'save_post'))
async def save_post(event):
    cid = event.chat_id
    d = AUTO_POST_CONFIG.get(cid)
    if not d or not d.get('groups'): return await event.respond("❌")
    await config_col.update_one({"owner_id": cid}, {"$set": {"message": d['msg'], "interval": d['time'], "groups": d['groups'], "active": True}}, upsert=True)
    asyncio.create_task(engine_autopost(active_clients[cid], cid))
    await event.respond("✅ **تم تشغيل النشر!**")
    USER_STATE[cid] = None

# ==============================================================================
#                               10. التشغيل
# ==============================================================================
async def main():
    await start_web_server()
    await load_all_sessions()
    print("✅ Bot Started (Final Clean Version)")
    await bot.start(bot_token=BOT_TOKEN)
    await bot.run_until_disconnected()

if __name__ == '__main__':
    try: loop = asyncio.get_event_loop(); loop.run_until_complete(main())
    except: pass
