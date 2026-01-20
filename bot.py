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
from telethon.tl.types import UserStatusOnline, UserStatusRecently, ChannelParticipantsAdmins
from telethon.tl.functions.messages import ImportChatInviteRequest, GetHistoryRequest
from telethon.tl.functions.channels import JoinChannelRequest, LeaveChannelRequest, GetParticipantRequest
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
logger = logging.getLogger("SaudiMerchantBot")

# جلب المتغيرات الحساسة
API_ID_RAW = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
SAMBANOVA_API_KEY = os.getenv("SAMBANOVA_API_KEY", "b1818ac7-46d5-4d95-bf75-8ad864b0b8de")

# التحقق الصارم من المتغيرات
if not API_ID_RAW or not API_HASH or not BOT_TOKEN or not MONGO_URI:
    logger.critical("❌ خطأ قاتل: أحد المتغيرات الأساسية مفقود (API_ID, HASH, TOKEN, MONGO).")
    sys.exit(1)

API_ID = int(API_ID_RAW)

# إعداد عميل الذكاء الاصطناعي (SambaNova Llama 405B)
try:
    ai_client = AsyncOpenAI(
        base_url="https://api.sambanova.ai/v1",
        api_key=SAMBANOVA_API_KEY
    )
    AI_MODEL = "Meta-Llama-3.1-405B-Instruct"
    logger.info(f"✅ تم تفعيل محرك الذكاء الاصطناعي: {AI_MODEL}")
except Exception as e:
    logger.error(f"⚠️ فشل إعداد الذكاء الاصطناعي: {e}")
    ai_client = None

# تعليمات الشخصية (System Prompt)
STRICT_RULE = """
أنت تاجر سعودي محترف، خبير في السوق والتعاملات.
1. تحدث بلهجة سعودية عامية محترمة ("يا هلا"، "أبشر"، "سم").
2. هدفك هو البيع، الإقناع، وخدمة العميل بسرعة.
3. لا تذكر أبداً أنك روبوت أو ذكاء اصطناعي.
4. إذا سئلت عن السعر ولا تعرفه، اطلب من العميل التواصل خاص مع المالك.
"""

# ==============================================================================
#                               2. متغيرات الذاكرة المؤقتة
# ==============================================================================
# تخزين الجلسات النشطة لليوزربوت
active_clients = {}

# تخزين حالة المستخدم الحالية (لإدخال النصوص)
USER_STATE = {}

# تخزين بيانات المهام المؤقتة قبل الحفظ
TASK_DATA = {}

# تخزين إعدادات النشر المؤقتة
AUTO_POST_CONFIG = {}

# تخزين معرفات آخر رسائل تم نشرها (للحذف عند الخطر)
# الصيغة: {'owner_id_chat_id': msg_id}
LAST_MSG_IDS = {}

# تخزين توقيت الردود لمنع التكرار (Cooldown)
# الصيغة: {(chat_id, user_id, keyword): timestamp}
REPLY_COOLDOWN = {}

# ==============================================================================
#                               3. الاتصال بقاعدة البيانات
# ==============================================================================
try:
    mongo_client = AsyncIOMotorClient(MONGO_URI)
    db = mongo_client['MyTelegramBotDB']
    
    # تعريف الجداول (Collections) بشكل منفصل وواضح
    sessions_col = db['sessions']           # تخزين جلسات الدخول
    replies_col = db['replies']             # تخزين الردود التلقائية
    reactions_col = db['reactions']         # تخزين التفاعلات
    ai_settings_col = db['ai_prompts']      # إعدادات الذكاء الاصطناعي
    config_col = db['autopost_config']      # إعدادات النشر التلقائي
    paused_groups_col = db['paused_groups'] # الجروبات المجمدة بسبب رد المشرف
    admins_watch_col = db['admins_watch']   # قائمة المشرفين المراقبين (الرادار)
    subs_col = db['subscriptions']          # الاشتراكات المؤقتة (للمغادرة لاحقاً)
    general_settings_col = db['general_settings'] # الإعدادات العامة (مثل زر الاشتراك التلقائي)
    
    logger.info("✅ تم الاتصال بقاعدة البيانات MongoDB بنجاح.")
except Exception as e:
    logger.critical(f"❌ فشل الاتصال بقاعدة البيانات: {e}")
    sys.exit(1)

# ==============================================================================
#                               4. خادم الويب (للبقاء نشطاً)
# ==============================================================================
bot = TelegramClient('bot_session', API_ID, API_HASH)

async def web_handler(request):
    """ صفحة ويب بسيطة تعرض حالة البوت """
    return web.Response(text=f"Bot Status: Online\nActive Users: {len(active_clients)}")

async def start_web_server():
    """ تشغيل خادم الويب في الخلفية """
    app = web.Application()
    app.router.add_get('/', web_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    logger.info("✅ خادم الويب يعمل على المنفذ 8080.")

# ==============================================================================
#                               5. دوال المساعدة (Helpers)
# ==============================================================================

async def ask_smart_ai(messages_history):
    """ إرسال الطلب للذكاء الاصطناعي والحصول على الرد """
    if not ai_client: return None
    try:
        response = await ai_client.chat.completions.create(
            model=AI_MODEL,
            messages=messages_history,
            temperature=0.7,
            top_p=0.9
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"خطأ في الذكاء الاصطناعي: {e}")
        return None

# ==============================================================================
#                               6. إدارة اليوزربوت (Core Userbot Logic)
# ==============================================================================

async def start_userbot(owner_id, session_str):
    """
    وظيفة ضخمة لتهيئة وتشغيل حساب المستخدم كبوت
    وتسجيل جميع المعالجات (Handlers) والمحركات (Engines).
    """
    try:
        # إغلاق الجلسة السابقة إن وجدت
        if owner_id in active_clients:
            await active_clients[owner_id].disconnect()
        
        # إنشاء العميل
        client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
        await client.connect()
        
        # التحقق من صلاحية الجلسة
        if not await client.is_user_authorized():
            logger.warning(f"جلسة المستخدم {owner_id} منتهية الصلاحية.")
            await sessions_col.delete_one({"_id": owner_id})
            return False
        
        client.owner_id = owner_id
        client.cooldowns = {} 

        # ----------------------------------------------------------------------
        #                       تسجيل المعالجات (Handlers)
        # ----------------------------------------------------------------------
        
        # 1. معالج الردود التلقائية (Auto Reply)
        client.add_event_handler(
            lambda e: process_auto_reply(client, e),
            events.NewMessage(incoming=True)
        )
        
        # 2. معالج التفاعل التلقائي (Auto React)
        client.add_event_handler(
            lambda e: process_auto_react(client, e),
            events.NewMessage(incoming=True)
        )
        
        # 3. معالج الذكاء الاصطناعي (Smart AI Chat)
        client.add_event_handler(
            lambda e: process_ai_chat(client, e),
            events.NewMessage(incoming=True)
        )
        
        # 4. معالج الاشتراك الإجباري الذكي (Smart Auto Join)
        client.add_event_handler(
            lambda e: process_aggressive_join(client, e),
            events.NewMessage(incoming=True)
        )
        
        # 5. معالج تجميد النشر عند رد المشرف (Admin Freeze)
        client.add_event_handler(
            lambda e: process_admin_freeze_trigger(client, e),
            events.NewMessage(incoming=True)
        )
        
        # 6. معالج فك التجميد عند رد المالك (Owner Resume)
        client.add_event_handler(
            lambda e: process_owner_resume_trigger(client, e),
            events.NewMessage(outgoing=True)
        )
        
        # حفظ العميل في الذاكرة
        active_clients[owner_id] = client
        logger.info(f"✅ تم تشغيل اليوزربوت بنجاح للمستخدم: {owner_id}")
        
        # ----------------------------------------------------------------------
        #                       تسجيل المهام الخلفية (Background Tasks)
        # ----------------------------------------------------------------------
        
        # أ. مهمة النشر التلقائي (War Mode)
        asyncio.create_task(engine_autopost(client, owner_id))
        
        # ب. مهمة المغادرة التلقائية (Auto Leave after 24h)
        asyncio.create_task(engine_autoleave(client, owner_id))
        
        return True
        
    except Exception as e:
        logger.error(f"❌ خطأ أثناء تشغيل اليوزربوت للمستخدم {owner_id}: {e}")
        return False

async def load_all_sessions():
    """ تحميل وتشغيل كافة الجلسات المخزنة عند بدء التشغيل """
    logger.info("⏳ جاري تحميل كافة الجلسات المحفوظة...")
    count = 0
    async for doc in sessions_col.find({}):
        success = await start_userbot(doc['_id'], doc['session_string'])
        if success: count += 1
    logger.info(f"✅ تم تحميل {count} جلسة بنجاح.")

# ==============================================================================
#                               7. تفاصيل المعالجات (Processors)
# ==============================================================================

# ----------------- 1. منطق الرد التلقائي -----------------
async def process_auto_reply(client, event):
    # يعمل في الخاص والجروبات
    if not event.is_private and not event.is_group: return
    try:
        text = event.raw_text or ""
        sender_id = event.sender_id
        chat_id = event.chat_id
        
        # جلب الردود الخاصة بهذا المستخدم
        cursor = replies_col.find({"owner_id": client.owner_id})
        async for rule in cursor:
            keyword = rule['keyword']
            reply_msg = rule['reply']
            
            if keyword in text:
                # التحقق من الكولدون (10 دقائق = 600 ثانية)
                unique_key = (chat_id, sender_id, keyword)
                last_time = REPLY_COOLDOWN.get(unique_key, 0)
                current_time = time.time()
                
                if current_time - last_time < 600:
                    continue # لم ينته الوقت، تجاهل
                
                # تحديث الوقت وإرسال الرد
                REPLY_COOLDOWN[unique_key] = current_time
                await event.reply(reply_msg)
                return # رد واحد يكفي
    except Exception as e:
        pass

# ----------------- 2. منطق التفاعل التلقائي -----------------
async def process_auto_react(client, event):
    if not event.is_private and not event.is_group: return
    try:
        text = event.raw_text or ""
        cursor = reactions_col.find({"owner_id": client.owner_id})
        async for rule in cursor:
            if rule['keyword'] in text:
                try:
                    await event.message.react(rule['emoji'])
                    return # تفاعل واحد يكفي
                except: pass
    except: pass

# ----------------- 3. منطق الذكاء الاصطناعي -----------------
async def process_ai_chat(client, event):
    # يعمل فقط في الخاص
    if not event.is_private: return
    try:
        # التحقق مما إذا كان الذكاء مفعلاً
        settings = await ai_settings_col.find_one({"owner_id": client.owner_id})
        if not settings or not settings.get('active', False):
            return # مطفأ
        
        # التحقق من كولدون الكتابة (لعدم الإزعاج)
        if time.time() - client.cooldowns.get(event.chat_id, 0) > 5:
            # إظهار "جاري الكتابة..."
            async with client.action(event.chat_id, 'typing'):
                await asyncio.sleep(2) # محاكاة تفكير بشري
            
            # إعداد الرسائل
            system_prompt = settings.get('prompt', "أنت تاجر.")
            msgs = [
                {"role": "system", "content": f"{STRICT_RULE}\n\nبياناتك:\n{system_prompt}"},
                {"role": "user", "content": event.raw_text or "[ملف/صورة]"}
            ]
            
            # طلب الرد
            ai_reply = await ask_smart_ai(msgs)
            if ai_reply:
                await event.reply(ai_reply)
            
            client.cooldowns[event.chat_id] = time.time()
    except Exception as e:
        logger.error(f"خطأ في معالج الذكاء: {e}")

# ----------------- 4. منطق الاشتراك الإجباري الذكي -----------------
async def process_aggressive_join(client, event):
    """
    هذا هو الوحش الذي يبحث عن أي رابط أو زر ويشترك فيه.
    يعمل فقط إذا فعلت الزر الخاص به.
    """
    try:
        # 1. التحقق من إعدادات المستخدم (هل الميزة مفعلة؟)
        settings = await general_settings_col.find_one({"owner_id": client.owner_id})
        if not settings or not settings.get('auto_join', False):
            return # الميزة معطلة
        
        targets_to_join = []
        
        # أ. البحث في النص عن روابط أو يوزرات
        text = event.raw_text or ""
        # البحث عن روابط t.me
        links = re.findall(r'(https?://t\.me/[^\s]+)', text)
        targets_to_join.extend(links)
        # البحث عن يوزرات (@channel)
        usernames = re.findall(r'(@[a-zA-Z0-9_]{4,})', text)
        targets_to_join.extend(usernames)
        
        # ب. البحث في الأزرار (Buttons) - هذه أهم نقطة للبوتات
        if event.message.buttons:
            for row in event.message.buttons:
                for btn in row:
                    if isinstance(btn, types.KeyboardButtonUrl):
                        if "t.me" in btn.url:
                            targets_to_join.append(btn.url)
        
        # 2. تنفيذ الاشتراك
        for target in targets_to_join:
            try:
                # تنظيف الرابط
                clean_target = target.replace("https://t.me/", "").replace("@", "").strip()
                
                # المحاولة
                if "+" in clean_target:
                    # رابط دعوة خاص (Private Invite Link)
                    hash_val = clean_target.split("+")[-1]
                    await client(ImportChatInviteRequest(hash_val))
                else:
                    # رابط عام أو يوزر (Public Channel/Group)
                    await client(JoinChannelRequest(clean_target))
                
                logger.info(f"✅ تم الاشتراك التلقائي في: {clean_target}")
                
                # 3. حفظ الاشتراك في قاعدة البيانات للمغادرة بعد 24 ساعة
                # نحاول نجيب الآيدي الرقمي للحفظ الأدق
                try:
                    entity = await client.get_entity(clean_target)
                    chat_id_save = entity.id
                except:
                    chat_id_save = clean_target # نحفظ النص إذا فشل جلب الآيدي

                await subs_col.update_one(
                    {"owner_id": client.owner_id, "chat_id": chat_id_save},
                    {"$set": {"join_time": time.time()}},
                    upsert=True
                )
                
            except FloodWaitError as fwe:
                logger.warning(f"⚠️ FloodWait أثناء الاشتراك: {fwe.seconds} ثانية.")
                await asyncio.sleep(fwe.seconds)
            except UserNotParticipantError:
                pass
            except Exception as e:
                # أخطاء متوقعة (مشترك مسبقاً، رابط خطأ.. إلخ)
                pass

    except Exception as e:
        pass

# ----------------- 5. منطق تجميد النشر (الحماية) -----------------
async def process_admin_freeze_trigger(client, event):
    # يجب أن يكون في جروب ويكون رداً
    if not event.is_group or not event.is_reply: return
    try:
        # هل الرد موجه لي؟
        me = await client.get_me()
        reply_message = await event.get_reply_message()
        if reply_message.sender_id != me.id:
            return # الرد ليس علي، لا يهمني
        
        # فحص صلاحيات من رد علي
        sender = await event.get_sender()
        permissions = await client.get_permissions(event.chat_id, sender)
        
        # إذا كان مشرفاً أو المالك
        if permissions.is_admin or permissions.is_creator:
            # تجميد الجروب
            await paused_groups_col.update_one(
                {"owner_id": client.owner_id, "chat_id": event.chat_id},
                {"$set": {
                    "admin_id": sender.id, # نحفظ من جمدنا
                    "ts": time.time()
                }},
                upsert=True
            )
            
            # إرسال تنبيه للمالك في المحفوظات
            await client.send_message("me", f"⛔ **تنبيه أمني:**\nتم إيقاف النشر في الجروب: **{event.chat.title}**\n👮 السبب: رد عليك المشرف (ID: `{sender.id}`).\n💡 **للاستئناف:** قم بالرد على رسالة هذا المشرف في الجروب.")
            
    except Exception as e:
        pass

# ----------------- 6. منطق فك التجميد (الاستئناف) -----------------
async def process_owner_resume_trigger(client, event):
    if not event.is_group or not event.is_reply: return
    try:
        owner_id = client.owner_id
        chat_id = event.chat_id
        
        # هل الجروب مجمد أصلاً؟
        paused_record = await paused_groups_col.find_one({"owner_id": owner_id, "chat_id": chat_id})
        if not paused_record:
            return # الجروب سليم، لا داعي لشيء
        
        # هل رددت على نفس المشرف؟
        reply_message = await event.get_reply_message()
        target_admin_id = paused_record.get('admin_id')
        
        if reply_message.sender_id == target_admin_id:
            # نعم، قمت بالاشتباك الصحيح
            await paused_groups_col.delete_one({"owner_id": owner_id, "chat_id": chat_id})
            await client.send_message("me", f"✅ **تم استئناف النشر!**\nلقد قمت بالرد على المشرف في **{event.chat.title}**.")
            
    except Exception as e:
        pass

# ==============================================================================
#                               8. المحركات الخلفية (Engines)
# ==============================================================================

# --- أ. محرك فحص الأونلاين (الرادار) ---
async def check_admin_online_radar(client, owner_id):
    """ يعيد True إذا كان أحد المشرفين في قائمة المراقبة متصلاً """
    is_danger = False
    try:
        # جلب قائمة المشرفين المراقبين لهذا المستخدم
        async for doc in admins_watch_col.find({"owner_id": owner_id}):
            target_username = doc['username']
            try:
                entity = await client.get_entity(target_username)
                # فحص الحالة: هل هو Online أو Recently
                if isinstance(entity.status, (UserStatusOnline, UserStatusRecently)):
                    is_danger = True
                    break # وجدنا واحداً، يكفي للتوقف
            except:
                pass # اليوزر غير موجود أو خطأ
    except:
        pass
    return is_danger

# --- ب. محرك النشر التلقائي (War Engine) ---
async def engine_autopost(client, owner_id):
    """
    حلقة لا نهائية تقوم بالنشر في الجروبات المحددة
    مع مراعاة الرادار والتجميد.
    """
    logger.info(f"🚀 بدء محرك النشر للمستخدم {owner_id}")
    
    while True:
        try:
            # 1. جلب الإعدادات الحالية
            config = await config_col.find_one({"owner_id": owner_id})
            
            # إذا لم يوجد إعدادات أو النشر متوقف
            if not config or not config.get('active', False):
                # ننتظر قليلاً ثم نفحص مرة أخرى (بدلاً من كسر الحلقة)
                await asyncio.sleep(60)
                continue
            
            target_groups = config.get('groups', [])
            message_text = config.get('message', "")
            interval_minutes = config.get('interval', 10)
            
            if not target_groups or not message_text:
                await asyncio.sleep(60)
                continue

            # 2. الدوران على الجروبات
            for group_id in target_groups:
                
                # أ. فحص التجميد (Blacklist)
                is_frozen = await paused_groups_col.find_one({"owner_id": owner_id, "chat_id": group_id})
                if is_frozen:
                    continue # تخطي هذا الجروب
                
                # ب. فحص الرادار (Online Check)
                radar_alert = await check_admin_online_radar(client, owner_id)
                if radar_alert:
                    # خطر! مشرف متصل.
                    # 1. حاول حذف آخر رسالة نشرتها في هذا الجروب
                    last_msg_id = LAST_MSG_IDS.get(f"{owner_id}_{group_id}")
                    if last_msg_id:
                        try:
                            await client.delete_messages(group_id, [last_msg_id])
                        except: pass
                    
                    # 2. توقف تكتيكي (5 دقائق)
                    await asyncio.sleep(300)
                    continue # انتقل للدورة التالية
                
                # ج. النشر
                try:
                    sent_msg = await client.send_message(int(group_id), message_text)
                    
                    # تسجيل آيدي الرسالة
                    LAST_MSG_IDS[f"{owner_id}_{group_id}"] = sent_msg.id
                    
                    # انتظار بسيط لتجنب الطوفان (Flood)
                    await asyncio.sleep(5) 
                    
                except FloodWaitError as fwe:
                    logger.warning(f"FloodWait {fwe.seconds}s for user {owner_id}")
                    await asyncio.sleep(fwe.seconds)
                except Exception as e:
                    logger.error(f"خطأ في النشر للمجموعة {group_id}: {e}")

            # 3. الانتظار للدورة القادمة
            await asyncio.sleep(interval_minutes * 60)
            
        except Exception as e:
            logger.error(f"خطأ غير متوقع في محرك النشر: {e}")
            await asyncio.sleep(60)

# --- ج. محرك المغادرة التلقائية (Auto Leave) ---
async def engine_autoleave(client, owner_id):
    """
    يفحص الاشتراكات المؤقتة ويغادر القنوات التي مر عليها 24 ساعة.
    """
    logger.info(f"🕰️ بدء محرك المغادرة التلقائية للمستخدم {owner_id}")
    while True:
        try:
            current_time = time.time()
            # البحث عن الاشتراكات التي مر عليها 86400 ثانية (24 ساعة)
            cursor = subs_col.find({"owner_id": owner_id})
            
            async for sub in cursor:
                join_time = sub.get('join_time', 0)
                if current_time - join_time > 86400:
                    chat_id = sub['chat_id']
                    try:
                        # محاولة تحويل الآيدي لرقم
                        try: target = int(chat_id)
                        except: target = chat_id
                        
                        await client(LeaveChannelRequest(target))
                        logger.info(f"🚪 مغادرة تلقائية من: {target}")
                        
                        # حذف من القاعدة
                        await subs_col.delete_one({"_id": sub['_id']})
                        
                        # انتظار بسيط
                        await asyncio.sleep(2)
                    except Exception as e:
                        logger.warning(f"فشل المغادرة من {chat_id}: {e}")
            
            # فحص كل ساعة
            await asyncio.sleep(3600)
            
        except Exception as e:
            await asyncio.sleep(3600)

# --- د. محرك تنفيذ مهام البحث (Task Runner) ---
async def engine_task_runner(client, status_msg, hours, keyword, reply_msg, delay):
    """ ينفذ مهمة البحث والرد لمرة واحدة """
    count = 0
    start_time = time.time() - (hours * 3600)
    replied_cache = set()
    
    try:
        me = await client.get_me()
        
        async for dialog in client.iter_dialogs(limit=None):
            if dialog.is_group:
                async for message in client.iter_messages(dialog.id, limit=30, search=keyword):
                    # الشروط
                    if message.date.timestamp() > start_time and message.sender_id != me.id:
                        if message.sender_id in replied_cache:
                            continue
                        
                        try:
                            await client.send_message(dialog.id, reply_msg, reply_to=message.id)
                            replied_cache.add(message.sender_id)
                            count += 1
                            await asyncio.sleep(delay)
                        except FloodWaitError as fwe:
                            await asyncio.sleep(fwe.seconds)
                        except: pass
                        
    except Exception as e:
        logger.error(f"Task Error: {e}")
        
    await status_msg.reply(f"✅ **اكتملت المهمة!**\nتم الرد على: `{count}` رسالة.")

# ==============================================================================
#                               9. واجهة البوت والقوائم (UI)
# ==============================================================================

@bot.on(events.NewMessage(pattern='/start'))
async def bot_start_command(event):
    await show_dashboard(event)

async def show_dashboard(event):
    cid = event.chat_id
    
    # التحقق من تسجيل الدخول
    if cid in active_clients and await active_clients[cid].is_user_authorized():
        
        # جلب الحالات لعرضها في الأزرار
        # 1. حالة النشر
        post_conf = await config_col.find_one({"owner_id": cid})
        icon_post = "🟢 يعمل" if post_conf and post_conf.get('active') else "🔴 متوقف"
        
        # 2. حالة الاشتراك التلقائي
        gen_conf = await general_settings_col.find_one({"owner_id": cid})
        icon_join = "🟢 مفعل" if gen_conf and gen_conf.get('auto_join') else "🔴 معطل"
        
        # 3. حالة الذكاء
        ai_conf = await ai_settings_col.find_one({"owner_id": cid})
        icon_ai = "🟢" if ai_conf and ai_conf.get('active') else "🔴"

        # بناء لوحة التحكم
        buttons = [
            [
                Button.inline(f"📢 النشر التلقائي: {icon_post}", b"menu_autopost")
            ],
            [
                Button.inline(f"🔗 الاشتراك التلقائي: {icon_join}", b"toggle_autojoin")
            ],
            [
                Button.inline("📋 عرض وحذف الردود المحفوظة", b"list_replies"),
                Button.inline("➕ إضافة رد جديد", b"add_reply")
            ],
            [
                Button.inline("👮 رادار المشرفين", b"menu_radar"),
                Button.inline("⛔ الجروبات المجمدة", b"menu_paused")
            ],
            [
                Button.inline("🚀 تشغيل مهمة بحث", b"menu_task"),
                Button.inline(f"🤖 الذكاء: {icon_ai}", b"toggle_ai")
            ],
            [
                Button.inline("🎭 إضافة تفاعل", b"add_react"),
                Button.inline("📊 الإحصائيات", b"view_stats")
            ]
        ]
        
        await event.respond(
            "👋 **أهلاً بك في لوحة تحكم التاجر (النسخة الكاملة)**\n\n"
            "هنا يمكنك التحكم في جميع خصائص الروبوت الخاص بك.",
            buttons=buttons
        )
    else:
        # زر تسجيل الدخول
        await event.respond(
            "🔒 **أنت غير مسجل.**\nيرجى تسجيل الدخول لتفعيل البوت.",
            buttons=[[Button.inline("🔑 تسجيل الدخول (Session String)", b"login")]]
        )

# ==============================================================================
#                               10. معالج الأزرار (Callback Queries)
# ==============================================================================

@bot.on(events.CallbackQuery)
async def bot_callback_handler(event):
    cid = event.chat_id
    data = event.data
    client = active_clients.get(cid)
    
    # ------------------- تسجيل الدخول -------------------
    if data == b"login":
        USER_STATE[cid] = "WAITING_SESSION"
        await event.respond("🔐 **الرجاء إرسال كود الجلسة (Session String) الآن:**")

    # ------------------- التحكم بالاشتراك التلقائي -------------------
    elif data == b"toggle_autojoin":
        current = await general_settings_col.find_one({"owner_id": cid})
        new_state = not (current.get('auto_join', False) if current else False)
        
        await general_settings_col.update_one(
            {"owner_id": cid},
            {"$set": {"auto_join": new_state}},
            upsert=True
        )
        
        status_text = "🟢 **تم تفعيل الاشتراك التلقائي!**\nسيدخل البوت أي قناة أو جروب يواجهه." if new_state else "🔴 **تم إيقاف الاشتراك التلقائي.**"
        await event.respond(status_text)
        await show_dashboard(event) # تحديث الواجهة

    # ------------------- قائمة الردود (عرض وحذف) -------------------
    elif data == b"list_replies":
        replies_cursor = replies_col.find({"owner_id": cid})
        buttons_list = []
        count = 0
        
        async for doc in replies_cursor:
            count += 1
            # إنشاء زر للحذف يحتوي على الآيدي
            btn_text = f"🗑️ حذف: {doc['keyword']}"
            btn_data = f"del_rep_{doc['_id']}"
            buttons_list.append([Button.inline(btn_text, btn_data)])
        
        buttons_list.append([Button.inline("🔙 رجوع", b"back_to_main")])
        
        if count > 0:
            await event.respond(f"📋 **قائمة الردود المحفوظة ({count}):**\nاضغط على الرد لحذفه.", buttons=buttons_list)
        else:
            await event.respond("❌ لا توجد ردود محفوظة حالياً.", buttons=buttons_list)

    # معالجة حذف الرد
    elif data.decode().startswith("del_rep_"):
        try:
            reply_id_str = data.decode().split("_")[2]
            await replies_col.delete_one({"_id": ObjectId(reply_id_str)})
            await event.answer("✅ تم الحذف بنجاح!")
            await event.respond("✅ **تم حذف الرد.**\nاضغط على 'عرض الردود' للتحديث.")
        except Exception as e:
            await event.respond(f"❌ خطأ: {e}")

    # ------------------- النشر التلقائي -------------------
    elif data == b"menu_autopost":
        await event.respond(
            "📢 **قائمة النشر التلقائي:**",
            buttons=[
                [Button.inline("⚙️ إعداد رسالة ووقت جديد", b"setup_post_new")],
                [Button.inline("⏯️ تشغيل / إيقاف النشر", b"toggle_post_active")],
                [Button.inline("🔙 رجوع", b"back_to_main")]
            ]
        )
    
    elif data == b"setup_post_new":
        USER_STATE[cid] = "WAITING_POST_MSG"
        await event.respond("📝 **أرسل نص الرسالة التي تريد نشرها:**")

    elif data == b"toggle_post_active":
        conf = await config_col.find_one({"owner_id": cid})
        if not conf:
            return await event.respond("❌ لا توجد إعدادات محفوظة. قم بالإعداد أولاً.")
        
        new_active = not conf.get('active', False)
        await config_col.update_one({"owner_id": cid}, {"$set": {"active": new_active}}, upsert=True)
        
        # إعادة تشغيل المحرك إذا تم التفعيل
        if new_active:
            asyncio.create_task(autopost_engine(client, cid))
            
        await event.respond(f"✅ حالة النشر الآن: {'🟢 يعمل' if new_active else '🔴 متوقف'}")
        await show_dashboard(event)

    # ------------------- الرادار (المشرفين) -------------------
    elif data == b"menu_radar":
        msg = "👮 **قائمة المشرفين المراقبين:**\n"
        async for d in admins_watch_col.find({"owner_id": cid}):
            msg += f"- `{d['username']}`\n"
        
        await event.respond(msg, buttons=[
            [Button.inline("➕ إضافة يوزر", b"add_radar_user"), Button.inline("🗑️ حذف يوزر", b"del_radar_user")],
            [Button.inline("🔙 رجوع", b"back_to_main")]
        ])

    elif data == b"add_radar_user":
        USER_STATE[cid] = "WAITING_RADAR_ADD"
        await event.respond("👤 **أرسل يوزر المشرف (بدون @):**")
    
    elif data == b"del_radar_user":
        USER_STATE[cid] = "WAITING_RADAR_DEL"
        await event.respond("👤 **أرسل يوزر المشرف لحذفه:**")

    # ------------------- الجروبات المجمدة -------------------
    elif data == b"menu_paused":
        msg = "⛔ **الجروبات المتوقفة حالياً:**\n"
        has_items = False
        async for d in paused_groups_col.find({"owner_id": cid}):
            has_items = True
            msg += f"- Chat ID: `{d['chat_id']}`\n"
        
        btns = [[Button.inline("🔙 رجوع", b"back_to_main")]]
        if has_items:
            btns.insert(0, [Button.inline("♻️ فك الحظر عن الجميع يدوياً", b"unpause_all")])
        
        await event.respond(msg if has_items else "✅ لا يوجد جروبات متوقفة.", buttons=btns)

    elif data == b"unpause_all":
        await paused_groups_col.delete_many({"owner_id": cid})
        await event.respond("✅ **تم تنظيف القائمة وفك الحظر.**")

    # ------------------- الإضافات (ردود، تفاعل، مهام) -------------------
    elif data == b"add_reply":
        USER_STATE[cid] = "WAITING_REP_KEY"
        await event.respond("🔑 **أرسل الكلمة المفتاحية:**")

    elif data == b"add_react":
        USER_STATE[cid] = "WAITING_REACT_KEY"
        await event.respond("🔑 **أرسل الكلمة المفتاحية للتفاعل:**")

    elif data == b"menu_task":
        USER_STATE[cid] = "WAITING_TASK_HOURS"
        TASK_DATA[cid] = {}
        await event.respond("1️⃣ **ابحث في رسائل آخر كم ساعة؟ (أرسل رقم)**")

    elif data == b"toggle_ai":
        curr = await ai_settings_col.find_one({"owner_id": cid})
        n_st = not (curr.get('active', False) if curr else False)
        await ai_settings_col.update_one({"owner_id": cid}, {"$set": {"active": n_st}}, upsert=True)
        await event.respond(f"🤖 الذكاء الاصطناعي: {'🟢' if n_st else '🔴'}")
        await show_dashboard(event)

    elif data == b"view_stats":
        if client:
            try:
                dialogs = await client.get_dialogs()
                groups = [d for d in dialogs if d.is_group]
                channels = [d for d in dialogs if d.is_channel]
                await event.respond(
                    f"📊 **إحصائيات حسابك:**\n\n"
                    f"💬 المجموعات: {len(groups)}\n"
                    f"📢 القنوات: {len(channels)}\n"
                    f"📨 المحادثات الخاصة: {len(dialogs) - len(groups) - len(channels)}"
                )
            except:
                await event.respond("❌ تعذر جلب الإحصائيات (قد يكون الحساب محظوراً مؤقتاً).")

    elif data == b"back_to_main":
        await show_dashboard(event)

# ==============================================================================
#                               11. معالج النصوص (Inputs Handler)
# ==============================================================================

@bot.on(events.NewMessage)
async def bot_input_handler(event):
    cid = event.chat_id
    text = event.text.strip()
    state = USER_STATE.get(cid)
    
    # تجاهل الأوامر أو إذا لم يكن هناك حالة انتظار
    if not state or text.startswith('/'): return
    
    # 1. تسجيل الدخول
    if state == "WAITING_SESSION":
        status_msg = await event.respond("⏳ **جاري التحقق من الجلسة...**")
        success = await start_userbot(cid, text)
        if success:
            await sessions_col.update_one({"_id": cid}, {"$set": {"session_string": text}}, upsert=True)
            await status_msg.edit("✅ **تم تسجيل الدخول وتشغيل البوت بنجاح!**")
            await show_dashboard(event)
        else:
            await status_msg.edit("❌ **كود الجلسة غير صالح أو منتهي.**\nحاول استخراج كود جديد.")
        USER_STATE[cid] = None

    # 2. إضافة رد
    elif state == "WAITING_REP_KEY":
        TASK_DATA[cid] = {"keyword": text}
        USER_STATE[cid] = "WAITING_REP_MSG"
        await event.respond("📝 **الآن أرسل الرد:**")
    
    elif state == "WAITING_REP_MSG":
        keyword = TASK_DATA[cid]['keyword']
        await replies_col.update_one(
            {"owner_id": cid, "keyword": keyword},
            {"$set": {"reply": text}},
            upsert=True
        )
        await event.respond(f"✅ **تم حفظ الرد للكلمة:** `{keyword}`")
        USER_STATE[cid] = None

    # 3. إضافة تفاعل
    elif state == "WAITING_REACT_KEY":
        TASK_DATA[cid] = {"keyword": text}
        USER_STATE[cid] = "WAITING_REACT_EMOJI"
        await event.respond("😀 **أرسل الإيموجي:**")
    
    elif state == "WAITING_REACT_EMOJI":
        keyword = TASK_DATA[cid]['keyword']
        await reactions_col.update_one(
            {"owner_id": cid, "keyword": keyword},
            {"$set": {"emoji": text}},
            upsert=True
        )
        await event.respond(f"✅ **تم حفظ التفاعل للكلمة:** `{keyword}`")
        USER_STATE[cid] = None

    # 4. الرادار
    elif state == "WAITING_RADAR_ADD":
        username = text.replace("@", "").strip()
        await admins_watch_col.update_one(
            {"owner_id": cid, "username": username},
            {"$set": {"ts": time.time()}},
            upsert=True
        )
        await event.respond(f"✅ **تمت إضافة {username} لقائمة المراقبة.**")
        USER_STATE[cid] = None
    
    elif state == "WAITING_RADAR_DEL":
        username = text.replace("@", "").strip()
        result = await admins_watch_col.delete_one({"owner_id": cid, "username": username})
        if result.deleted_count > 0:
            await event.respond(f"🗑️ **تم حذف {username} من القائمة.**")
        else:
            await event.respond("❌ هذا الاسم غير موجود.")
        USER_STATE[cid] = None

    # 5. إعدادات النشر
    elif state == "WAITING_POST_MSG":
        AUTO_POST_CONFIG[cid] = {'msg': text}
        USER_STATE[cid] = "WAITING_POST_TIME"
        await event.respond("⏱️ **كم دقيقة الانتظار بين النشر؟ (أرسل رقماً فقط)**")
    
    elif state == "WAITING_POST_TIME":
        try:
            minutes = int(text)
            AUTO_POST_CONFIG[cid]['time'] = minutes
            USER_STATE[cid] = "WAITING_POST_GROUPS"
            
            # عرض الجروبات للاختيار
            client = active_clients.get(cid)
            if not client: return
            
            buttons = []
            async for dialog in client.iter_dialogs(limit=40):
                if dialog.is_group:
                    btn_text = dialog.name[:20]
                    btn_data = f"sel_gp_{dialog.id}"
                    buttons.append([Button.inline(btn_text, btn_data)])
            
            buttons.append([Button.inline("✅ حفظ وبدء النشر", "save_autopost_final")])
            AUTO_POST_CONFIG[cid]['groups'] = []
            
            await event.respond("📂 **اختر الجروبات للنشر فيها:**", buttons=buttons)
        except ValueError:
            await event.respond("❌ الرجاء إرسال رقم صحيح.")

    # 6. إعداد المهام
    elif state == "WAITING_TASK_HOURS":
        try:
            TASK_DATA[cid] = {'hours': int(text)}
            USER_STATE[cid] = "WAITING_TASK_KEY"
            await event.respond("🔎 **ما هي الكلمة التي تبحث عنها؟**")
        except: pass
    
    elif state == "WAITING_TASK_KEY":
        TASK_DATA[cid]['keyword'] = text
        USER_STATE[cid] = "WAITING_TASK_REP"
        await event.respond("📝 **ما هو الرد؟**")
    
    elif state == "WAITING_TASK_REP":
        TASK_DATA[cid]['reply'] = event.message # حفظ الرسالة كاملة
        USER_STATE[cid] = "WAITING_TASK_DELAY"
        await event.respond("⏱️ **كم ثانية انتظار بين كل رد؟**")
    
    elif state == "WAITING_TASK_DELAY":
        try:
            delay = int(text)
            status_msg = await event.respond("🚀 **جاري بدء المهمة في الخلفية...**")
            
            # تشغيل المهمة
            client = active_clients.get(cid)
            asyncio.create_task(engine_task_runner(
                client,
                status_msg,
                TASK_DATA[cid]['hours'],
                TASK_DATA[cid]['keyword'],
                TASK_DATA[cid]['reply'],
                delay
            ))
            USER_STATE[cid] = None
        except: pass

# --- معالجة اختيار الجروبات للنشر ---
@bot.on(events.CallbackQuery(pattern=r'sel_gp_'))
async def post_group_selection(event):
    cid = event.chat_id
    group_id = int(event.data.decode().split('_')[2])
    
    current_list = AUTO_POST_CONFIG.get(cid, {}).get('groups', [])
    
    if group_id not in current_list:
        current_list.append(group_id)
        await event.answer("✅ تم اختيار الجروب")
    else:
        current_list.remove(group_id)
        await event.answer("❌ تم الإلغاء")
    
    AUTO_POST_CONFIG[cid]['groups'] = current_list

@bot.on(events.CallbackQuery(pattern=b'save_autopost_final'))
async def post_save_final(event):
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
    client = active_clients.get(cid)
    asyncio.create_task(autopost_engine(client, cid))
    
    await event.respond("✅ **تم حفظ الإعدادات وتشغيل النشر التلقائي!**")
    USER_STATE[cid] = None

# ==============================================================================
#                               12. التشغيل النهائي (Main Loop)
# ==============================================================================

async def main():
    logger.info("🚀 بدء تشغيل النظام...")
    
    # تشغيل السيرفر والجلسات
    await start_web_server()
    await load_all_sessions()
    
    logger.info("✅ البوت جاهز ويعمل بكامل طاقته (Full Mode).")
    
    # تشغيل البوت الرئيسي
    await bot.start(bot_token=BOT_TOKEN)
    await bot.run_until_disconnected()

if __name__ == '__main__':
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        logger.info("🛑 تم إيقاف البوت يدوياً.")
    except Exception as e:
        logger.critical(f"❌ حدث خطأ غير متوقع: {e}")
        traceback.print_exc()
