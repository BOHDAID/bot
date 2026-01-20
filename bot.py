import os
import sys
import asyncio
import logging
import time
import re
from datetime import datetime
import aiohttp

# استيراد مكتبات التيليجرام الضرورية
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.tl.types import UserStatusOnline, UserStatusRecently, ChannelParticipantsAdmins, User
from telethon.tl.functions.messages import ImportChatInviteRequest, GetHistoryRequest
from telethon.tl.functions.channels import JoinChannelRequest, LeaveChannelRequest

# استيراد مكتبة قاعدة البيانات
from motor.motor_asyncio import AsyncIOMotorClient

# استيراد خادم الويب (لإبقاء البوت نشطاً في Render)
from aiohttp import web

# استيراد مكتبة الذكاء الاصطناعي
from openai import AsyncOpenAI

# استيراد تحميل المتغيرات
from dotenv import load_dotenv

# ==================================================================
#                       1. التجهيز والإعدادات
# ==================================================================

# تحميل ملف .env
load_dotenv()

# إعداد السجلات (Logs) لرؤية الأخطاء بوضوح
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- جلب المتغيرات من النظام ---
API_ID_RAW = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")

# التحقق من أن المتغيرات موجودة
if not all([API_ID_RAW, API_HASH, BOT_TOKEN, MONGO_URI]):
    logger.error("❌ خطأ جسيم: أحد المتغيرات الأساسية (API_ID, HASH, TOKEN, MONGO) مفقود!")
    sys.exit(1)

API_ID = int(API_ID_RAW)

# متغيرات إضافية
SAMBANOVA_API_KEY = os.getenv("SAMBANOVA_API_KEY", "b1818ac7-46d5-4d95-bf75-8ad864b0b8de")
MY_LTC_ADDRESS = os.getenv("MY_LTC_ADDRESS", "Your_LTC_Address")

# تهيئة عميل الذكاء الاصطناعي
try:
    ai_client = AsyncOpenAI(
        base_url="https://api.sambanova.ai/v1",
        api_key=SAMBANOVA_API_KEY
    )
    AI_MODEL = "Meta-Llama-3.1-405B-Instruct"
    print(f"✅ تم تفعيل محرك الذكاء: {AI_MODEL}")
except Exception as e:
    print(f"⚠️ تحذير: فشل إعداد الذكاء الاصطناعي: {e}")

# تعليمات النظام للشخصية
STRICT_RULE = """
تعليمات النظام:
أنت تاجر سعودي محترف وذكي.
1. تحدث بلهجة سعودية عامية ومباشرة.
2. هدفك هو إقناع العميل وبيع الخدمة.
3. لا تذكر أنك بوت أو ذكاء اصطناعي أبداً.
"""

# ==================================================================
#                       2. المتغيرات العامة (الذاكرة)
# ==================================================================
active_clients = {}      # لتخزين جلسات اليوزربوت النشطة
USER_STATE = {}          # لتتبع حالة المستخدم (ماذا يفعل الآن)
TASK_DATA = {}           # لتخزين بيانات المهام المؤقتة
AUTO_POST_CONFIG = {}    # لتخزين إعدادات النشر المؤقتة
LAST_MSG_IDS = {}        # لتخزين معرف آخر رسالة نشرت (للحذف عند الخطر)
REPLY_COOLDOWN = {}      # لتخزين توقيت الردود (منع التكرار)

# ==================================================================
#                       3. الاتصال بقاعدة البيانات
# ==================================================================
try:
    mongo_client = AsyncIOMotorClient(MONGO_URI)
    db = mongo_client['MyTelegramBotDB']
    
    # تعريف الجداول (Collections)
    sessions_col = db['sessions']           # جلسات الدخول
    replies_col = db['replies']             # الردود التلقائية
    reactions_col = db['reactions']         # التفاعلات (الإيموجي)
    ai_settings_col = db['ai_prompts']      # إعدادات الذكاء
    config_col = db['autopost_config']      # إعدادات النشر التلقائي
    paused_groups_col = db['paused_groups'] # الجروبات المجمدة (بسبب المشرف)
    admins_watch_col = db['admins_watch']   # قائمة المشرفين للمراقبة
    subs_col = db['subscriptions']          # جدول الاشتراكات المؤقتة (للمغادرة لاحقاً)
    
    print("✅ تم الاتصال بقاعدة البيانات بنجاح")
except Exception as e:
    print(f"❌ فشل الاتصال بقاعدة البيانات: {e}")
    sys.exit(1)

# ==================================================================
#                       4. البوت الرئيسي وخادم الويب
# ==================================================================
bot = TelegramClient('bot_session', API_ID, API_HASH)

async def web_handler(request):
    """ صفحة ويب بسيطة لإبقاء البوت حياً """
    return web.Response(text=f"Bot is Running. Active Userbots: {len(active_clients)}")

async def start_web_server():
    """ تشغيل خادم الويب في الخلفية """
    app = web.Application()
    app.router.add_get('/', web_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    print("✅ خادم الويب يعمل على المنفذ 8080")

# ==================================================================
#                       5. وظائف المساعدة والذكاء
# ==================================================================
async def ask_smart_ai(messages_history):
    """ دالة التحدث مع الذكاء الاصطناعي """
    try:
        response = await ai_client.chat.completions.create(
            model=AI_MODEL,
            messages=messages_history,
            temperature=0.7,
            top_p=0.9
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"AI Error: {e}")
        return None

# ==================================================================
#                       6. إدارة اليوزربوت (Userbot)
# ==================================================================
async def start_userbot(owner_id, session_str):
    """ تشغيل حساب المستخدم كـ يوزربوت """
    try:
        # فصل الجلسة القديمة إذا وجدت
        if owner_id in active_clients:
            await active_clients[owner_id].disconnect()
        
        # إنشاء عميل جديد
        client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
        await client.connect()
        
        # التحقق من الصلاحية
        if not await client.is_user_authorized():
            print(f"❌ الجلسة منتهية للمستخدم {owner_id}")
            await sessions_col.delete_one({"_id": owner_id})
            return False
        
        client.owner_id = owner_id
        client.cooldowns = {} 

        # ---------------- تسجيل المعالجات (Handlers) ----------------
        # 1. معالج الردود التلقائية
        client.add_event_handler(lambda e: handler_auto_reply(client, e), events.NewMessage(incoming=True))
        
        # 2. معالج التفاعلات (الإيموجي)
        client.add_event_handler(lambda e: handler_auto_react(client, e), events.NewMessage(incoming=True))
        
        # 3. معالج الذكاء الاصطناعي (للخاص)
        client.add_event_handler(lambda e: handler_ai_chat(client, e), events.NewMessage(incoming=True))
        
        # 4. معالج الانضمام الآمن (Safe Join) - نسخة شرسة جداً
        client.add_event_handler(lambda e: handler_safe_join(client, e), events.NewMessage(incoming=True))
        
        # 5. معالج تجميد النشر (عند رد الأدمن)
        client.add_event_handler(lambda e: handler_admin_freeze(client, e), events.NewMessage(incoming=True))
        
        # 6. معالج فك التجميد (عند رد المالك)
        client.add_event_handler(lambda e: handler_owner_resume(client, e), events.NewMessage(outgoing=True))
        # ------------------------------------------------------------
        
        active_clients[owner_id] = client
        print(f"✅ تم تفعيل اليوزربوت للمستخدم: {owner_id}")
        
        # استعادة النشر التلقائي إذا كان مفعلاً
        saved_config = await config_col.find_one({"owner_id": owner_id})
        if saved_config and saved_config.get('active', False):
            asyncio.create_task(autopost_engine(client, owner_id))
            
        # تشغيل محرك المغادرة التلقائية (الخروج بعد 24 ساعة)
        asyncio.create_task(auto_leave_engine(client, owner_id))

        return True
    except Exception as e:
        print(f"❌ خطأ في تشغيل اليوزربوت: {e}")
        return False

async def load_all_sessions():
    """ تحميل جميع الجلسات المحفوظة عند التشغيل """
    print("⏳ جاري تحميل الجلسات المحفوظة...")
    async for doc in sessions_col.find({}):
        asyncio.create_task(start_userbot(doc['_id'], doc['session_string']))

# ==================================================================
#                       7. تفاصيل المعالجات (Handlers)
# ==================================================================

# --- 1. معالج الردود التلقائية ---
async def handler_auto_reply(client, event):
    if not event.is_private and not event.is_group: return
    try:
        owner_id = client.owner_id
        text = event.raw_text or ""
        sender_id = event.sender_id
        
        # البحث في قاعدة البيانات عن رد مناسب
        cursor = replies_col.find({"owner_id": owner_id})
        async for d in cursor:
            if d['keyword'] in text:
                # التحقق من المؤقت (10 دقائق)
                cool_key = (event.chat_id, sender_id, d['keyword'])
                last_reply_time = REPLY_COOLDOWN.get(cool_key, 0)
                
                if time.time() - last_reply_time < 600: 
                    return # لم تمر 10 دقائق، تجاهل
                
                # تحديث الوقت وإرسال الرد
                REPLY_COOLDOWN[cool_key] = time.time()
                await event.reply(d['reply'])
                return # توقف هنا، لا تكمل للمعالجات الأخرى
    except: pass

# --- 2. معالج التفاعلات (React) ---
async def handler_auto_react(client, event):
    if not event.is_private and not event.is_group: return
    try:
        owner_id = client.owner_id
        text = event.raw_text or ""
        
        cursor = reactions_col.find({"owner_id": owner_id})
        async for d in cursor:
            if d['keyword'] in text:
                try: 
                    await event.message.react(d['emoji'])
                    break # تفاعل واحد يكفي
                except: pass
    except: pass

# --- 3. معالج الذكاء الاصطناعي ---
async def handler_ai_chat(client, event):
    # الذكاء يعمل في الخاص فقط (Private)
    if not event.is_private: return
    try:
        owner_id = client.owner_id
        
        # هل الذكاء مفعل؟
        settings = await ai_settings_col.find_one({"owner_id": owner_id})
        if not settings or not settings.get('active', False):
            return

        # تأخير بسيط ليظهر كأنه بشري
        if time.time() - client.cooldowns.get(event.chat_id, 0) > 5:
            async with client.action(event.chat_id, 'typing'):
                await asyncio.sleep(2) # انتظار ثانيتين
            
            # تجهيز الرسالة
            user_msg = event.raw_text or "صورة/ملف"
            prompt = settings.get('prompt', "أنت تاجر.")
            
            messages = [
                {"role": "system", "content": f"{STRICT_RULE}\nمعلوماتك:\n{prompt}"},
                {"role": "user", "content": user_msg}
            ]
            
            ai_reply = await ask_smart_ai(messages)
            if ai_reply:
                await event.reply(ai_reply)
            
            client.cooldowns[event.chat_id] = time.time()
    except: pass

# --- 4. معالج الانضمام الآمن (Safe Join) - نسخة محدثة وموسعة ---
async def handler_safe_join(client, event):
    try:
        # الشرط: يجب أن تكون الرسالة رداً (Reply) أو منشتاً (Mention)
        if not (event.is_reply or event.mentioned): return
        
        reply_msg = await event.get_reply_message()
        me = await client.get_me()
        
        # الشرط الأهم: الرد يجب أن يكون على رسالتي أنا
        if reply_msg.sender_id != me.id: return 

        text = event.raw_text.lower()
        
        # الكلمات المفتاحية الموسعة (بناءً على الصورة التي أرسلتها)
        triggers = [
            "join", "اشترك", "subscribe", "subscription", "قناة", "channel",
            "لايمكنك", "غير مشترك", "عليك الاشتراك", "must join", "المجموعة",
            "group", "بوت", "bot"
        ]
        
        if any(x in text for x in triggers):
            print(f"⚠️ كشف رسالة اشتراك إجباري: {text[:50]}...")
            
            # 1. استخراج الروابط العادية (https://t.me/...)
            links = re.findall(r'(https?://t\.me/[^\s]+)', event.raw_text)
            # 2. استخراج اليوزرات (@username) مثل اللي في الصورة
            usernames = re.findall(r'(@[a-zA-Z0-9_]{4,})', event.raw_text)
            
            all_targets = links + usernames
            
            # البحث عن الروابط في الأزرار أيضاً (مهم جداً للبوتات مثل Red bull)
            if event.message.buttons:
                for row in event.message.buttons:
                    for btn in row:
                        if btn.url:
                            if "t.me" in btn.url:
                                all_targets.append(btn.url)
            
            # تنفيذ الاشتراك
            for target in all_targets:
                try:
                    # تنظيف الهدف
                    final_target = target.replace("https://t.me/", "").replace("@", "").strip()
                    
                    if "+" in final_target: # رابط دعوة خاص
                         await client(ImportChatInviteRequest(final_target.split("+")[-1]))
                    else: # يوزرنيم أو رابط عام
                        await client(JoinChannelRequest(final_target))
                    
                    # حفظ الاشتراك في قاعدة البيانات للمغادرة بعد 24 ساعة
                    # نحاول نجيب الآيدي للحفظ
                    try:
                        chat_entity = await client.get_entity(final_target)
                        chat_id_to_save = chat_entity.id
                    except:
                        chat_id_to_save = final_target # نحفظ اليوزر اذا فشل جلب الآيدي

                    await subs_col.update_one(
                        {"owner_id": client.owner_id, "chat_id": chat_id_to_save},
                        {"$set": {"join_time": time.time()}},
                        upsert=True
                    )
                    
                    print(f"✅ تم الاشتراك الإجباري في: {final_target}")
                    
                except Exception as e:
                    print(f"❌ فشل الاشتراك في {target}: {e}")
    except: pass

# --- 5. معالج تجميد النشر (Admin Freeze) ---
async def handler_admin_freeze(client, event):
    """ يراقب إذا قام مشرف بالرد عليك """
    try:
        if not event.is_group or not event.is_reply: return
        
        me = await client.get_me()
        reply_msg = await event.get_reply_message()
        
        # إذا كان الرد ليس علي، تجاهل
        if reply_msg.sender_id != me.id: return
        
        sender = await event.get_sender()
        perms = await client.get_permissions(event.chat_id, sender)
        
        # إذا كان المرسل مشرفاً أو مالك الجروب
        if perms.is_admin or perms.is_creator:
            owner_id = client.owner_id
            
            # تسجيل الجروب في قائمة التوقف
            await paused_groups_col.update_one(
                {"owner_id": owner_id, "chat_id": event.chat_id},
                {"$set": {
                    "admin_id": sender.id, # نحفظ من هو المشرف الذي جمدنا
                    "ts": time.time()
                }},
                upsert=True
            )
            
            # إبلاغ المالك
            await client.send_message("me", f"⛔ **تم إيقاف النشر في:** {event.chat.title}\n👮 السبب: رد عليك المشرف (ID: {sender.id}).\n✅ **الحل:** قم بالرد عليه ليعود النشر.")
    except: pass

# --- 6. معالج فك التجميد (Owner Resume) ---
async def handler_owner_resume(client, event):
    """ يراقب ردود المالك لفك الحظر """
    try:
        if not event.is_group or not event.is_reply: return
        
        owner_id = client.owner_id
        chat_id = event.chat_id
        
        # هل الجروب متوقف أصلاً؟
        paused_data = await paused_groups_col.find_one({"owner_id": owner_id, "chat_id": chat_id})
        if not paused_data: return
        
        reply_msg = await event.get_reply_message()
        
        # هل رددت على نفس المشرف؟
        if reply_msg.sender_id == paused_data.get('admin_id'):
            await paused_groups_col.delete_one({"owner_id": owner_id, "chat_id": chat_id})
            await client.send_message("me", f"✅ **تم استئناف النشر في:** {event.chat.title}\nأحسنت التصرف!")
    except: pass

# ==================================================================
#                       8. محركات الخلفية (Engines)
# ==================================================================

# --- محرك النشر الحربي (Autopost Engine) ---
async def check_admin_online_radar(client, owner_id):
    """ فحص هل أحد المشرفين المراقبين متصل الآن؟ """
    is_danger = False
    try:
        cursor = admins_watch_col.find({"owner_id": owner_id})
        async for doc in cursor:
            try:
                entity = await client.get_entity(doc['username'])
                # الفحص: هل هو متصل (Online) أو كان متصلاً قريباً (Recently)
                if isinstance(entity.status, (UserStatusOnline, UserStatusRecently)):
                    is_danger = True
                    break 
            except: pass
    except: pass
    return is_danger

async def autopost_engine(client, owner_id):
    """ الحلقة اللانهائية للنشر التلقائي """
    print(f"🚀 تشغيل محرك النشر للمستخدم: {owner_id}")
    
    while True:
        try:
            # 1. جلب الإعدادات
            config = await config_col.find_one({"owner_id": owner_id})
            if not config or not config.get('active', False):
                print(f"🛑 توقف النشر للمستخدم {owner_id}")
                break 

            target_groups = config['groups']
            msg_content = config['message']
            interval_minutes = config['interval']
            
            # 2. الدوران على الجروبات
            for chat_id in target_groups:
                
                # أ. التحقق من التجميد (هل رد أدمن؟)
                is_paused = await paused_groups_col.find_one({"owner_id": owner_id, "chat_id": chat_id})
                if is_paused:
                    continue # تخطي هذا الجروب
                
                # ب. التحقق من الرادار (هل مشرف متصل؟)
                radar_danger = await check_admin_online_radar(client, owner_id)
                if radar_danger:
                    # خطر! احذف آخر رسالة واهرب
                    last_msg = LAST_MSG_IDS.get(f"{owner_id}_{chat_id}")
                    if last_msg:
                        try: await client.delete_messages(chat_id, [last_msg])
                        except: pass
                    
                    await asyncio.sleep(300) # توقف 5 دقائق
                    continue 
                
                # ج. النشر الآمن
                try:
                    sent_msg = await client.send_message(int(chat_id), msg_content)
                    # حفظ الرسالة للحذف عند الطوارئ
                    LAST_MSG_IDS[f"{owner_id}_{chat_id}"] = sent_msg.id
                    await asyncio.sleep(3)
                except Exception as e:
                    print(f"خطأ في النشر {chat_id}: {e}")
            
            # 3. الانتظار للدورة القادمة
            await asyncio.sleep(interval_minutes * 60)
            
        except Exception as e:
            print(f"خطأ في محرك النشر: {e}")
            await asyncio.sleep(60)

# --- محرك المغادرة التلقائية (Auto Leave) ---
async def auto_leave_engine(client, owner_id):
    """ فحص القنوات المشترك بها مؤقتاً ومغادرتها بعد 24 ساعة """
    while True:
        try:
            now = time.time()
            # البحث عن الاشتراكات التي مر عليها 24 ساعة (86400 ثانية)
            async for doc in subs_col.find({"owner_id": owner_id}):
                join_time = doc.get('join_time', 0)
                if now - join_time > 86400:
                    try:
                        chat_id_to_leave = doc['chat_id']
                        # محاولة التعامل مع الآيدي سواء كان رقم أو نص
                        try: chat_id_to_leave = int(chat_id_to_leave)
                        except: pass
                        
                        await client(LeaveChannelRequest(chat_id_to_leave))
                        print(f"🚪 مغادرة تلقائية من: {chat_id_to_leave}")
                        # حذف من القاعدة
                        await subs_col.delete_one({"_id": doc['_id']})
                    except Exception as e:
                        print(f"فشل المغادرة: {e}")
        except: pass
        await asyncio.sleep(3600) # فحص كل ساعة

# --- محرك مهام البحث (Tasks) ---
async def run_task_engine(client, status_msg, hours, keyword, reply_msg, delay):
    """ البحث عن رسائل والرد عليها """
    count = 0
    limit_time = time.time() - (hours * 3600)
    replied_users_cache = set() # لضمان عدم الرد على نفس الشخص مرتين
    
    try:
        me = await client.get_me()
        
        # البحث في كل المحادثات
        async for dialog in client.iter_dialogs(limit=None):
            if dialog.is_group:
                # البحث عن الكلمة
                async for message in client.iter_messages(dialog.id, limit=20, search=keyword):
                    # الشروط: الوقت + ليس أنا + لم أرد عليه سابقاً
                    if message.date.timestamp() > limit_time and message.sender_id != me.id:
                        if message.sender_id in replied_users_cache:
                            continue 
                        
                        try:
                            await client.send_message(dialog.id, reply_msg, reply_to=message.id)
                            replied_users_cache.add(message.sender_id)
                            count += 1
                            await asyncio.sleep(delay)
                        except: pass
                        
    except Exception as e:
        print(f"خطأ في المهمة: {e}")
        
    await status_msg.reply(f"✅ انتهت مهمة البحث.\nتم الرد على: {count} رسالة.")

# ==================================================================
#                       10. قوائم البوت (القوائم والأزرار)
# ==================================================================
@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    await show_main_menu(event)

async def show_main_menu(event):
    cid = event.chat_id
    # التأكد من أن المستخدم مسجل الدخول
    if cid in active_clients and await active_clients[cid].is_user_authorized():
        # جلب حالة النشر
        conf = await config_col.find_one({"owner_id": cid})
        status_autopost = "🟢" if conf and conf.get('active') else "🔴"
        
        # جلب حالة الذكاء
        ai_set = await ai_settings_col.find_one({"owner_id": cid})
        status_ai = "🟢" if ai_set and ai_set.get('active') else "🔴"

        buttons = [
            [Button.inline(f"📢 النشر التلقائي {status_autopost}", b"menu_autopost")],
            [Button.inline("👮 رادار المشرفين", b"menu_radar"), Button.inline("⛔ الجروبات المتوقفة", b"menu_paused")],
            [Button.inline("🚀 مهام البحث", b"menu_task"), Button.inline(f"🤖 الذكاء {status_ai}", b"toggle_ai")],
            [Button.inline("➕ إضافة رد", b"add_rep"), Button.inline("🎭 إضافة تفاعل", b"add_react")],
            [Button.inline("🗑️ حذف (رد/تفاعل)", b"menu_del"), Button.inline("📊 الإحصائيات", b"stats")],
            [Button.inline("🚨 اشتراك يدوي (للطوارئ)", b"manual_join")] # 🆕 زر الطوارئ
        ]
        await event.respond("✅ **لوحة التحكم الشاملة (النسخة الكاملة)**\nاختر من القائمة:", buttons=buttons)
    else:
        await event.respond("👋 أهلاً بك.\nيرجى تسجيل الدخول أولاً.", buttons=[[Button.inline("🔐 تسجيل الدخول", b"login")]])

# ==================================================================
#                       11. معالج الأزرار (Callbacks)
# ==================================================================
@bot.on(events.CallbackQuery)
async def callback_handler(event):
    cid = event.chat_id
    data = event.data
    client = active_clients.get(cid)
    
    # --- تسجيل الدخول ---
    if data == b"login":
        USER_STATE[cid] = "SESS"
        await event.respond("🔐 **أرسل كود الجلسة (Session String) الآن:**")

    # --- اشتراك يدوي (طوارئ) ---
    elif data == b"manual_join":
        USER_STATE[cid] = "MANUAL_JOIN"
        await event.respond("🆘 **أرسل رابط القناة أو اليوزر (مثلاً @channel) للاشتراك فوراً:**")

    # --- قائمة النشر التلقائي ---
    elif data == b"menu_autopost":
        btns = [
            [Button.inline("⚙️ إعداد جديد", b"setup_post")],
            [Button.inline("تشغيل / إيقاف", b"toggle_post")]
        ]
        await event.respond("📢 **تحكم النشر التلقائي:**", buttons=btns)
        
    elif data == b"setup_post":
        AUTO_POST_CONFIG[cid] = {}
        USER_STATE[cid] = "SET_MSG"
        await event.respond("📝 **أرسل نص الرسالة التي تريد نشرها:**")
        
    elif data == b"toggle_post":
        conf = await config_col.find_one({"owner_id": cid})
        if not conf:
            return await event.respond("❌ لا توجد إعدادات! قم بإنشاء إعداد جديد أولاً.")
        
        new_status = not conf.get('active', False)
        await config_col.update_one({"owner_id": cid}, {"$set": {"active": new_status}}, upsert=True)
        
        if new_status:
            asyncio.create_task(autopost_engine(client, cid))
        
        await event.respond(f"✅ تم تغيير الحالة إلى: {'🟢' if new_status else '🔴'}")

    # --- قائمة الرادار (المشرفين) ---
    elif data == b"menu_radar":
        s = "**👮 المشرفين المراقبين (توقف النشر إذا اتصلوا):**\n"
        async for doc in admins_watch_col.find({"owner_id": cid}):
            s += f"- @{doc['username']}\n"
        btns = [[Button.inline("➕ إضافة يوزر", b"add_watch"), Button.inline("🗑️ حذف يوزر", b"del_watch")]]
        await event.respond(s, buttons=btns)
        
    elif data == b"add_watch":
        USER_STATE[cid] = "ADD_ADMIN"
        await event.respond("👤 **أرسل يوزر المشرف (بدون @):**")
        
    elif data == b"del_watch":
        USER_STATE[cid] = "DEL_ADMIN"
        await event.respond("👤 **أرسل اليوزر لحذفه:**")

    # --- قائمة الجروبات المتوقفة ---
    elif data == b"menu_paused":
        s = "**⛔ الجروبات المتوقفة (بانتظار ردك على المشرف):**\n"
        count = 0
        async for doc in paused_groups_col.find({"owner_id": cid}):
            s += f"- Chat ID: `{doc['chat_id']}` (Admin: {doc.get('admin_id')})\n"
            count += 1
        
        btns = []
        if count > 0:
            btns.append([Button.inline("♻️ فك الحظر يدوياً عن الكل", b"clear_paused")])
        
        await event.respond(s if count > 0 else "✅ لا يوجد جروبات متوقفة حالياً.", buttons=btns)
        
    elif data == b"clear_paused":
        await paused_groups_col.delete_many({"owner_id": cid})
        await event.respond("✅ تم فك الحظر عن جميع الجروبات يدوياً.")

    # --- قائمة المهام والذكاء ---
    elif data == b"menu_task":
        USER_STATE[cid] = "TASK_H"
        TASK_DATA[cid] = {}
        await event.respond("1️⃣ **ابحث في رسائل آخر كم ساعة؟** (أرسل رقم)")
        
    elif data == b"toggle_ai":
        s = await ai_settings_col.find_one({"owner_id": cid})
        new_s = not (s.get('active', False) if s else False)
        await ai_settings_col.update_one({"owner_id": cid}, {"$set": {"active": new_s}}, upsert=True)
        await event.respond(f"🤖 الذكاء: {'🟢' if new_s else '🔴'}")

    # --- الردود والتفاعلات ---
    elif data == b"add_rep":
        USER_STATE[cid] = "ADD_KEY"
        await event.respond("📝 **أرسل الكلمة المفتاحية للرد:**")
        
    elif data == b"add_react":
        USER_STATE[cid] = "ADD_REACT_KEY"
        await event.respond("📝 **أرسل الكلمة المفتاحية للتفاعل:**")
        
    elif data == b"menu_del":
        btns = [[Button.inline("حذف رد", b"del_rep"), Button.inline("حذف تفاعل", b"del_react")]]
        await event.respond("ماذا تريد أن تحذف؟", buttons=btns)
        
    elif data == b"del_rep":
        USER_STATE[cid] = "DEL_KEY"
        await event.respond("🗑️ **أرسل الكلمة لحذف ردها:**")
        
    elif data == b"del_react":
        USER_STATE[cid] = "DEL_REACT"
        await event.respond("🗑️ **أرسل الكلمة لحذف تفاعلها:**")
        
    elif data == b"stats":
        if client:
            d = await client.get_dialogs()
            await event.respond(f"📊 **الإحصائيات:**\nعدد المحادثات والجروبات النشطة: {len(d)}")

# ==================================================================
#                       12. معالج الإدخال النصي (Inputs)
# ==================================================================
@bot.on(events.NewMessage)
async def input_handler(event):
    cid = event.chat_id
    text = event.text.strip()
    state = USER_STATE.get(cid)
    
    # تجاهل الأوامر أو إذا لم يكن هناك حالة
    if not state or text.startswith('/'): return
    
    # --- تسجيل الدخول ---
    if state == "SESS":
        msg = await event.respond("⏳ جاري التحقق من الجلسة...")
        if await start_userbot(cid, text):
            await sessions_col.update_one({"_id": cid}, {"$set": {"session_string": text}}, upsert=True)
            await msg.edit("✅ **تم تسجيل الدخول بنجاح!**")
            await show_main_menu(event)
        else:
            await msg.edit("❌ كود الجلسة غير صالح أو منتهي.")
        USER_STATE[cid] = None

    # --- اشتراك يدوي (طوارئ) ---
    elif state == "MANUAL_JOIN":
        client = active_clients.get(cid)
        if client:
            try:
                target = text.replace("https://t.me/", "").replace("@", "").strip()
                await client(JoinChannelRequest(target))
                await event.respond(f"✅ تم الاشتراك في {target} بنجاح!")
            except Exception as e:
                await event.respond(f"❌ فشل الاشتراك: {e}")
        USER_STATE[cid] = None

    # --- إعداد النشر ---
    elif state == "SET_MSG":
        AUTO_POST_CONFIG[cid]['msg'] = text
        USER_STATE[cid] = "SET_TIME"
        await event.respond("⏱️ **كم دقيقة الانتظار بين كل عملية نشر؟** (رقم)")
        
    elif state == "SET_TIME":
        try:
            val = int(text)
            AUTO_POST_CONFIG[cid]['time'] = val
            USER_STATE[cid] = "SEL_GROUPS"
            
            # عرض الجروبات
            client = active_clients.get(cid)
            buttons = []
            async for d in client.iter_dialogs(limit=30):
                if d.is_group:
                    buttons.append([Button.inline(d.name[:25], f"gp_{d.id}")])
            
            buttons.append([Button.inline("✅ حفظ وبدء النشر", "save_post")])
            AUTO_POST_CONFIG[cid]['groups'] = []
            
            await event.respond("📂 **اختر الجروبات التي تريد النشر فيها:**", buttons=buttons)
        except:
            await event.respond("❌ الرجاء إرسال رقم صحيح.")

    # --- إدخالات الرادار ---
    elif state == "ADD_ADMIN":
        u = text.replace("@", "")
        await admins_watch_col.update_one({"owner_id": cid, "username": u}, {"$set": {"ts": time.time()}}, upsert=True)
        await event.respond(f"✅ تم إضافة {u} للمراقبة.")
        USER_STATE[cid] = None
        
    elif state == "DEL_ADMIN":
        u = text.replace("@", "")
        await admins_watch_col.delete_one({"owner_id": cid, "username": u})
        await event.respond(f"🗑️ تم حذف {u}.")
        USER_STATE[cid] = None

    # --- إدخالات الردود ---
    elif state == "ADD_KEY":
        TASK_DATA[cid] = {"k": text}
        USER_STATE[cid] = "VAL"
        await event.respond("📝 **الآن أرسل الرد الذي تريده:**")
        
    elif state == "VAL":
        await replies_col.update_one({"owner_id": cid, "keyword": TASK_DATA[cid]["k"]}, {"$set": {"reply": text}}, upsert=True)
        await event.respond("✅ تم حفظ الرد."); USER_STATE[cid] = None
        
    elif state == "DEL_KEY":
        await replies_col.delete_one({"owner_id": cid, "keyword": text})
        await event.respond("🗑️ تم الحذف."); USER_STATE[cid] = None

    # --- إدخالات التفاعل ---
    elif state == "ADD_REACT_KEY":
        TASK_DATA[cid] = {"k": text}
        USER_STATE[cid] = "ADD_REACT_EMOJI"
        await event.respond("😀 **أرسل الإيموجي:**")
        
    elif state == "ADD_REACT_EMOJI":
        await reactions_col.update_one({"owner_id": cid, "keyword": TASK_DATA[cid]["k"]}, {"$set": {"emoji": text}}, upsert=True)
        await event.respond("✅ تم حفظ التفاعل."); USER_STATE[cid] = None
        
    elif state == "DEL_REACT":
        await reactions_col.delete_one({"owner_id": cid, "keyword": text})
        await event.respond("🗑️ تم الحذف."); USER_STATE[cid] = None

    # --- إدخالات المهام ---
    elif state == "TASK_H":
        try:
            TASK_DATA[cid] = {"h": int(text)}
            USER_STATE[cid] = "TK"
            await event.respond("🔎 **ما هي الكلمة التي تبحث عنها؟**")
        except: pass
        
    elif state == "TK":
        TASK_DATA[cid]["k"] = text
        USER_STATE[cid] = "TR"
        await event.respond("📝 **ما هو الرد الذي تريد إرساله؟**")
        
    elif state == "TR":
        TASK_DATA[cid]["r"] = event.message # نحفظ كائن الرسالة كاملاً
        USER_STATE[cid] = "TD"
        await event.respond("⏱️ **كم ثانية انتظار بين كل رد؟**")
        
    elif state == "TD":
        try:
            delay = int(text)
            msg = await event.respond("🚀 جاري بدء المهمة في الخلفية...")
            asyncio.create_task(run_task_engine(
                active_clients[cid], msg, TASK_DATA[cid]["h"], TASK_DATA[cid]["k"], TASK_DATA[cid]["r"], delay
            ))
            USER_STATE[cid] = None
        except: pass

# --- أزرار اختيار الجروبات ---
@bot.on(events.CallbackQuery(pattern=r'gp_'))
async def group_selection_handler(event):
    cid = event.chat_id
    gid = int(event.data.decode().split('_')[1])
    
    if 'groups' not in AUTO_POST_CONFIG.get(cid, {}):
        AUTO_POST_CONFIG[cid]['groups'] = []
        
    if gid not in AUTO_POST_CONFIG[cid]['groups']:
        AUTO_POST_CONFIG[cid]['groups'].append(gid)
        await event.answer("✅ تم الاختيار")
    else:
        AUTO_POST_CONFIG[cid]['groups'].remove(gid)
        await event.answer("❌ تم الإلغاء")

@bot.on(events.CallbackQuery(pattern=b'save_post'))
async def save_post_handler(event):
    cid = event.chat_id
    data = AUTO_POST_CONFIG.get(cid)
    
    if not data or not data.get('groups'):
        return await event.respond("❌ يجب اختيار جروب واحد على الأقل.")
    
    await config_col.update_one(
        {"owner_id": cid},
        {"$set": {
            "message": data['msg'],
            "interval": data['time'],
            "groups": data['groups'],
            "active": True
        }},
        upsert=True
    )
    
    # تشغيل المحرك
    cli = active_clients.get(cid)
    asyncio.create_task(autopost_engine(cli, cid))
    
    await event.respond("✅ **تم تفعيل النشر التلقائي بنجاح!**"); USER_STATE[cid] = None

# ==================================================================
#                       13. التشغيل الرئيسي
# ==================================================================
async def main():
    await start_web_server()
    await load_all_sessions()
    print("✅ تم تشغيل البوت بنجاح (النسخة الكاملة المفصلة)")
    await bot.start(bot_token=BOT_TOKEN)
    await bot.run_until_disconnected()

if __name__ == '__main__':
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("تم إيقاف البوت.")
    except Exception as e:
        print(f"خطأ غير متوقع: {e}")
