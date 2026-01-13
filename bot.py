import os
import sys
import asyncio
import logging
import time
import re
import aiohttp
from dotenv import load_dotenv
from openai import AsyncOpenAI 
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.tl.functions.channels import JoinChannelRequest, LeaveChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.types import User
from motor.motor_asyncio import AsyncIOMotorClient
from aiohttp import web

# تحميل الإعدادات من ملف .env لضمان الأمان
load_dotenv()

# ==========================================
#      1. الإعدادات والتهيئة الشاملة
# ==========================================
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# جلب البيانات الحساسة من ملف البيئة
API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
MONGO_URI = os.getenv("MONGO_URI", "")
MY_LTC_ADDRESS = os.getenv("MY_LTC_ADDRESS", "")
SAMBANOVA_API_KEY = os.getenv("SAMBANOVA_API_KEY", "")

# إعداد محرك الذكاء الاصطناعي SambaNova
try:
    ai_client = AsyncOpenAI(
        base_url="https://api.sambanova.ai/v1",
        api_key=SAMBANOVA_API_KEY
    )
    AI_MODEL = "Meta-Llama-3.1-405B-Instruct"
    print(f"✅ تم تفعيل محرك الذكاء الخارق: {AI_MODEL}")
except Exception as e:
    print(f"❌ فشل إعداد AI: {e}")

# تعليمات النظام الصارمة لشخصية البوت
STRICT_RULE = """
تعليمات النظام (System Prompt):
أنت تاجر سعودي محترف، ولست ذكاءً اصطناعياً.
1. تحدث بلهجة سعودية طبيعية جداً (نجدية/حجازية بيضاء).
2. لا تستخدم الفصحى المقعرة ولا تعتذر للعميل بشكل آلي.
3. هدفك الأساسي هو البيع وإقناع العميل بالخدمات.
4. إذا سألك العميل عن شيء غير موجود، اطلبه منه بذكاء أو اقترح بديل.
"""

# مخازن البيانات المؤقتة في الرام
active_clients = {}      
USER_STATE = {}          
TASK_DATA = {}           
AI_CONTEXT = {} 

# ==========================================
#      2. الاتصال بقاعدة البيانات MongoDB
# ==========================================
try:
    mongo_client = AsyncIOMotorClient(MONGO_URI)
    db = mongo_client['MyTelegramBotDB']
    sessions_col = db['sessions']       
    replies_col = db['replies']         
    subs_col = db['subscriptions']      
    ai_settings_col = db['ai_prompts']  
    print("✅ تم الاتصال بقاعدة البيانات بنجاح")
except Exception as e:
    print(f"❌ خطأ في قاعدة البيانات: {e}")
    sys.exit(1)

# ==========================================
#      3. خادم الويب (للحفاظ على استمرارية العمل)
# ==========================================
async def web_handler(request):
    status_text = f"Bot is Running. Active Sessions: {len(active_clients)}"
    return web.Response(text=status_text)

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', web_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    print("🌐 خادم الويب يعمل على المنفذ 8080")

# ==========================================
#      4. محرك الاستعلام من الذكاء الاصطناعي
# ==========================================
async def ask_smart_ai(messages_history):
    """دالة إرسال الطلبات لنموذج Llama 405B"""
    try:
        response = await ai_client.chat.completions.create(
            model=AI_MODEL,
            messages=messages_history,
            temperature=0.7, 
            top_p=0.9
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"AI API Error: {e}")
        return None

# ==========================================
#      5. دوال الخدمات والميزات (مفصلة)
# ==========================================

async def perform_ultimate_analysis(client, owner_id, status_msg):
    """سحب الرسائل وتحليل شخصية المستخدم"""
    try:
        await status_msg.edit("📦 **جاري سحب عينة من رسائلك السابقة...**")
        collected_data = ""
        count = 0
        async for dialog in client.iter_dialogs(limit=25):
            if count > 10000: break 
            if dialog.is_user and not dialog.entity.bot:
                async for msg in client.iter_messages(dialog.id, limit=10):
                    if msg.out and msg.text:
                        collected_data += f"- {msg.text}\n"
                        count += len(msg.text)
        
        await status_msg.edit("🧠 **المارد (405B) يقوم بتحليل أسلوبك التجاري...**")
        analysis_msgs = [
            {"role": "system", "content": "أنت خبير تحليل بيانات استخلص أسلوب التاجر بدقة واكتب له ملف تعريف."},
            {"role": "user", "content": f"حلل هذه الرسائل لتاجر واستخرج المنتجات والأسعار والأسلوب:\n{collected_data[:6000]}"}
        ]
        final_res = await ask_smart_ai(analysis_msgs)
        if final_res:
            await ai_settings_col.update_one({"owner_id": owner_id}, {"$set": {"prompt": final_res}}, upsert=True)
            await client.send_message("me", f"📝 **تقرير التحليل الكامل:**\n\n{final_res}")
            return "✅ **تم الاستنساخ بنجاح! البوت الآن يتحدث مثلك.**"
        return "❌ فشل التحليل، حاول لاحقاً."
    except Exception as e:
        return f"خطأ أثناء التحليل: {e}"

async def verify_ltc(tx_hash):
    """التحقق من معاملات لايتكوين"""
    try:
        tx_hash = re.sub(r'[^a-fA-F0-9]', '', tx_hash)
        if len(tx_hash) < 10: return False, "هاش غير صحيح"
        url = f"https://api.blockcypher.com/v1/ltc/main/txs/{tx_hash}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=12) as response:
                if response.status != 200: return False, "المعاملة غير موجودة في البلوكشين"
                data = await response.json()
        
        for out in data.get("outputs", []):
            if MY_LTC_ADDRESS in out.get("addresses", []):
                val = out.get("value", 0) / 100000000.0
                return True, f"{val} LTC"
        return False, "المبلغ لم يرسل لهذا العنوان"
    except Exception:
        return False, "خطأ في الشبكة الخارجية"

async def run_broadcast(client, msg, obj, target_type):
    """دالة النشر التلقائي"""
    success_count = 0
    try:
        async for dialog in client.iter_dialogs():
            is_target = False
            if target_type == "groups" and dialog.is_group: is_target = True
            elif target_type == "private" and dialog.is_user and not dialog.entity.bot: is_target = True
            
            if is_target:
                try:
                    await client.send_message(dialog.id, obj)
                    success_count += 1
                    await asyncio.sleep(0.5) # تجنب الحظر
                except: pass
        await msg.reply(f"✅ اكتملت عملية النشر لـ {success_count} محادثة.")
    except Exception as e:
        await msg.reply(f"❌ حدث خطأ أثناء النشر: {e}")

async def run_search_task(client, msg, hours, keyword, reply_msg, delay):
    """مهمة البحث والرد التلقائي في المجموعات"""
    replied_count = 0
    time_limit = time.time() - (hours * 3600)
    try:
        me = await client.get_me()
        async for dialog in client.iter_dialogs():
            if dialog.is_group:
                async for message in client.iter_messages(dialog.id, limit=30, search=keyword):
                    if message.date.timestamp() > time_limit and message.sender_id != me.id:
                        try:
                            await client.send_message(dialog.id, reply_msg, reply_to=message.id)
                            replied_count += 1
                            await asyncio.sleep(delay)
                        except: pass
        await msg.reply(f"✅ انتهت مهمة البحث. تم الرد على {replied_count} رسالة.")
    except Exception as e:
        await msg.reply(f"❌ خطأ في المهمة: {e}")

async def clean_account_dialogs(client, msg):
    """تنظيف الحساب من الحسابات المحذوفة"""
    deleted_count = 0
    await msg.edit("🧹 جاري فحص الحسابات المحذوفة...")
    async for dialog in client.iter_dialogs():
        if isinstance(dialog.entity, User) and dialog.entity.deleted:
            try:
                await client.delete_dialog(dialog.id)
                deleted_count += 1
            except: pass
    await msg.edit(f"✅ تم تنظيف الحساب وحذف {deleted_count} محادثة مع حسابات محذوفة.")

# ==========================================
#      6. تشغيل وإدارة جلسات المستخدمين
# ==========================================
async def start_userbot_session(owner_id, session_str):
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
        
        # إضافة معالجات الأحداث لليوزربوت
        client.add_event_handler(lambda e: userbot_incoming_message_logic(client, e), events.NewMessage(incoming=True))
        client.add_event_handler(lambda e: auto_join_handler(client, e), events.NewMessage(incoming=True))
        
        active_clients[owner_id] = client
        return True
    except:
        return False

async def userbot_incoming_message_logic(client, event):
    """المنطق البرمجي للرد التلقائي داخل حساب المستخدم"""
    if not event.is_private: return 
    try:
        owner_id = client.owner_id
        settings = await ai_settings_col.find_one({"owner_id": owner_id})
        is_ai_active = settings.get('active', False) if settings else False
        
        raw_text = event.raw_text or ""
        
        # 1. فحص الردود التلقائية المخزنة (الكلمات المفتاحية)
        keywords_cursor = replies_col.find({"owner_id": owner_id})
        async for data in keywords_cursor:
            if data['keyword'] in raw_text:
                await event.reply(data['reply'])
                return 

        # 2. فحص الذكاء الاصطناعي إذا كان مفعلاً
        if not is_ai_active: return 

        current_ts = time.time()
        # منع الرد المتكرر بسرعة (Cooldown)
        if current_ts - client.cooldowns.get(event.chat_id, 0) > 5: 
            async with client.action(event.chat_id, 'typing'):
                await asyncio.sleep(1.5)
                
                pay_status = ""
                # التحقق من وجود هاش لايتكوين في الرسالة
                hash_match = re.search(r'\b[a-fA-F0-9]{64}\b', raw_text)
                if hash_match:
                    v, i = await verify_ltc(hash_match.group(0))
                    pay_status = f"\n[تنبيه للنظام: العميل أرسل إشعار دفع، النتيجة: {'ناجح' if v else 'فاشل'}، القيمة: {i}]"
                
                persona = settings.get('prompt', "أنت تاجر سعودي.") if settings else "أنت تاجر سعودي."
                
                messages = [
                    {"role": "system", "content": f"{STRICT_RULE}\n\nشخصيتك ومعلوماتك:\n{persona}\n{pay_status}"},
                    {"role": "user", "content": raw_text if raw_text else "[أرسل العميل وسائط]"}
                ]
                
                ai_response = await ask_smart_ai(messages)
                if ai_response:
                    await event.reply(ai_response)
                    client.cooldowns[event.chat_id] = current_ts
    except Exception as e:
        logger.error(f"Error in userbot handler: {e}")

async def auto_join_handler(client, event):
    """الانضمام التلقائي عند استقبال رابط قناة"""
    try:
        if any(word in event.raw_text.lower() for word in ["انضم", "اشترك", "join"]):
            links = re.findall(r'(https?://t\.me/[^\s]+)', event.raw_text)
            for link in links:
                await perform_temporary_join(client, link)
    except: pass

async def perform_temporary_join(client, link):
    try:
        chat_id = 0
        if "+" in link or "joinchat" in link:
            invite_hash = link.split("+")[-1].replace("https://t.me/joinchat/", "")
            result = await client(ImportChatInviteRequest(invite_hash))
            if result.chats: chat_id = result.chats[0].id
        else:
            clean_link = link.replace('@', '').replace('https://t.me/', '')
            await client(JoinChannelRequest(clean_link))
            entity = await client.get_entity(clean_link)
            chat_id = entity.id
        
        if chat_id:
            await subs_col.update_one(
                {"owner_id": client.owner_id, "chat_id": chat_id}, 
                {"$set": {"join_time": time.time()}}, 
                upsert=True
            )
    except: pass

# ==========================================
#      7. المهام الخلفية المجدولة
# ==========================================
async def auto_leave_manager():
    """مهمة خلفية لمغادرة القنوات بعد 24 ساعة"""
    while True:
        try:
            current_now = time.time()
            cursor = subs_col.find({})
            async for entry in cursor:
                # 86400 ثانية = 24 ساعة
                if current_now - entry['join_time'] > 86400:
                    try:
                        client = active_clients.get(entry['owner_id'])
                        if client:
                            await client(LeaveChannelRequest(entry['chat_id']))
                    except: pass
                    await subs_col.delete_one({"_id": entry['_id']})
        except: pass
        await asyncio.sleep(3600)

# ==========================================
#      8. واجهة التحكم (البوت الرسمي)
# ==========================================
@bot.on(events.NewMessage(pattern='/start'))
async def bot_start_handler(event):
    await show_main_menu(event)

async def show_main_menu(event):
    cid = event.chat_id
    if cid in active_clients and await active_clients[cid].is_user_authorized():
        settings = await ai_settings_col.find_one({"owner_id": cid})
        is_active = settings.get('active', False) if settings else False
        
        status_btn = Button.inline("🟢 الذكاء يعمل" if is_active else "🔴 الذكاء متوقف", b"toggle_ai_status")
        
        buttons_layout = [
            [status_btn],
            [Button.inline("🕵️‍♂️ استنساخ الشخصية (405B)", b"run_deep_scan")],
            [Button.inline("🗣️ تدريب البوت (نقاش)", b"start_consult"), Button.inline("💰 فحص دفع LTC", b"check_ltc_ui")],
            [Button.inline("🛠️ أدوات الإدارة والمهام", b"open_admin_tools")],
            [Button.inline("ℹ️ معلومات النظام", b"sys_info")]
        ]
        await event.respond("🛡️ **لوحة التحكم المركزية (SambaNova Engine)**\nمرحباً بك! اختر من القائمة التالية لإدارة حسابك:", buttons=buttons_layout)
    else:
        await event.respond("👋 أهلاً بك في بوت التاجر الذكي.\nيرجى تسجيل الدخول لربط حسابك بالجهاز.", buttons=[[Button.inline("🔐 تسجيل الدخول", b"init_login")]])

@bot.on(events.CallbackQuery)
async def bot_callback_handler(event):
    cid = event.chat_id
    data = event.data
    cli = active_clients.get(cid)

    if data == b"init_login":
        USER_STATE[cid] = "AWAITING_SESS"
        await event.respond("🔐 **يرجى إرسال كود الجلسة (String Session) الآن:**")
    
    elif data == b"toggle_ai_status":
        s = await ai_settings_col.find_one({"owner_id": cid})
        current = s.get('active', False) if s else False
        await ai_settings_col.update_one({"owner_id": cid}, {"$set": {"active": not current}}, upsert=True)
        await show_main_menu(event)

    elif data == b"open_admin_tools":
        admin_btns = [
            [Button.inline("🚀 مهمة بحث ورد جديد", b"ui_new_task"), Button.inline("🧹 تنظيف الحساب", b"ui_clean_acc")],
            [Button.inline("➕ إضافة رد تلقائي", b"ui_add_reply"), Button.inline("🗑️ حذف رد تلقائي", b"ui_del_reply")],
            [Button.inline("📋 قائمة ردودي", b"ui_list_replies"), Button.inline("⏳ انضمام يدوي", b"ui_join_temp")],
            [Button.inline("📢 نشر للمجموعات", b"ui_bc_groups"), Button.inline("📢 نشر للخاص", b"ui_bc_private")],
            [Button.inline("📊 إحصائيات الحساب", b"ui_stats"), Button.inline("🔙 رجوع للقائمة", b"ui_back_main")]
        ]
        await event.edit("🛠️ **أدوات الإدارة المتقدمة:**\nتحكم في مهام النشر، البحث، والردود التلقائية من هنا.", buttons=admin_btns)

    elif data == b"ui_back_main":
        await show_main_menu(event)

    elif data == b"run_deep_scan":
        if not cli: return
        m = await event.respond("🚀 بدأت عملية التحليل العميق لرسائلك...")
        asyncio.create_task(perform_ultimate_analysis(cli, cid, m))

    elif data == b"start_consult":
        USER_STATE[cid] = "CONSULT_MODE"
        AI_CONTEXT[cid] = [{"role": "system", "content": "أنت خبير مبيعات. اسأل التاجر عن منتجاته وأسعاره لتدريب البوت."}]
        first_q = await ask_smart_ai(AI_CONTEXT[cid])
        AI_CONTEXT[cid].append({"role": "assistant", "content": first_q})
        await event.respond(f"🗣️ **بدأت جلسة التدريب:**\n\n{first_q}")

    elif data == b"check_ltc_ui":
        USER_STATE[cid] = "AWAITING_TX"
        await event.respond("💰 **يرجى إرسال هاش المعاملة (TX Hash) للتحقق:**")

    elif data == b"ui_new_task":
        USER_STATE[cid] = "TASK_STEP_1"
        TASK_DATA[cid] = {}
        await event.respond("1️⃣ **كم عدد الساعات التي تريد البحث خلالها؟** (مثلاً: 24)")

    elif data == b"ui_bc_groups":
        USER_STATE[cid] = "BC_GROUP_MSG"
        await event.respond("📢 **أرسل الرسالة التي تريد نشرها في جميع مجموعاتك:**")

    elif data == b"ui_add_reply":
        USER_STATE[cid] = "ADD_KEYWORD_STEP_1"
        await event.respond("📝 **أرسل الكلمة المفتاحية التي سيفحصها البوت:**")

    elif data == b"ui_clean_acc":
        m = await event.respond("🧹 جاري البدء...")
        asyncio.create_task(clean_account_dialogs(cli, m))
    
    elif data == b"ui_list_replies":
        all_replies = "**📋 قائمة الردود المسجلة لديك:**\n\n"
        async for item in replies_col.find({"owner_id": cid}):
            all_replies += f"🔹 `{item['keyword']}` -> {item['reply']}\n"
        await event.respond(all_replies)

# ==========================================
#      9. معالج المدخلات النصية (Input Handler)
# ==========================================
@bot.on(events.NewMessage)
async def global_input_handler(event):
    cid = event.chat_id
    text = event.text.strip()
    state = USER_STATE.get(cid)
    
    if not state or text.startswith('/'): return

    if state == "AWAITING_SESS":
        if await start_userbot_session(cid, text):
            await sessions_col.update_one({"_id": cid}, {"$set": {"session_string": text}}, upsert=True)
            await event.respond("✅ **تم ربط الحساب بنجاح!**")
            await show_main_menu(event)
        else:
            await event.respond("❌ **الكود غير صحيح أو انتهت صلاحيته.**")
        USER_STATE[cid] = None

    elif state == "CONSULT_MODE":
        if text.lower() in ["تم", "انتهى", "حفظ"]:
            await event.respond("⏳ جاري إنشاء شخصية البوت النهائية...")
            AI_CONTEXT[cid].append({"role": "user", "content": "اكتب System Prompt نهائي وشامل بناءً على كلامي."})
            final_prompt = await ask_smart_ai(AI_CONTEXT[cid])
            if final_prompt:
                await ai_settings_col.update_one({"owner_id": cid}, {"$set": {"prompt": final_prompt}}, upsert=True)
                await event.respond("✅ **تم الحفظ بنجاح!**")
            USER_STATE[cid] = None
        else:
            AI_CONTEXT[cid].append({"role": "user", "content": text})
            response = await ask_smart_ai(AI_CONTEXT[cid])
            if response:
                AI_CONTEXT[cid].append({"role": "assistant", "content": response})
                await event.reply(response)

    elif state == "AWAITING_TX":
        v, i = await verify_ltc(text)
        await event.respond(f"{'✅' if v else '❌'} **النتيجة:** {i}")
        USER_STATE[cid] = None

    elif state == "BC_GROUP_MSG":
        m = await event.respond("🚀 جاري بدء النشر في المجموعات...")
        asyncio.create_task(run_broadcast(active_clients[cid], m, event.message, "groups"))
        USER_STATE[cid] = None

    elif state == "ADD_KEYWORD_STEP_1":
        TASK_DATA[cid] = {"k": text}
        USER_STATE[cid] = "ADD_KEYWORD_STEP_2"
        await event.respond("📝 **الآن أرسل الرد الذي سيقوم البوت بإرساله:**")

    elif state == "ADD_KEYWORD_STEP_2":
        await replies_col.update_one(
            {"owner_id": cid, "keyword": TASK_DATA[cid]["k"]}, 
            {"$set": {"reply": text}}, 
            upsert=True
        )
        await event.respond("✅ **تمت إضافة الرد التلقائي بنجاح.**")
        USER_STATE[cid] = None

    elif state == "TASK_STEP_1":
        try:
            TASK_DATA[cid]["h"] = int(text)
            USER_STATE[cid] = "TASK_STEP_2"
            await event.respond("2️⃣ **ما هي الكلمة المفتاحية للبحث عنها؟**")
        except: await event.respond("⚠️ يرجى إدخال رقم صحيح.")

    elif state == "TASK_STEP_2":
        TASK_DATA[cid]["k"] = text
        USER_STATE[cid] = "TASK_STEP_3"
        await event.respond("3️⃣ **أرسل رسالة الرد (يمكن أن تكون نص أو صورة):**")

    elif state == "TASK_STEP_3":
        TASK_DATA[cid]["r"] = event.message
        USER_STATE[cid] = "TASK_STEP_4"
        await event.respond("4️⃣ **أرسل وقت التأخير بين الردود بالثواني:** (مثلاً: 5)")

    elif state == "TASK_STEP_4":
        try:
            m = await event.respond("🚀 جاري تنفيذ مهمة البحث والرد...")
            asyncio.create_task(run_search_task(
                active_clients[cid], m, 
                TASK_DATA[cid]["h"], 
                TASK_DATA[cid]["k"], 
                TASK_DATA[cid]["r"], 
                int(text)
            ))
            USER_STATE[cid] = None
        except: await event.respond("⚠️ يرجى إدخال رقم ثواني صحيح.")

# ==========================================
#      10. الدالة الرئيسية لتشغيل البوت
# ==========================================
async def main_application_start():
    # تشغيل خادم الويب
    await start_web_server()
    
    # تحميل كافة الجلسات المخزنة في القاعدة
    async for entry in sessions_col.find({}):
        asyncio.create_task(start_userbot_session(entry['_id'], entry['session_string']))
    
    # تشغيل مدير مغادرة القنوات في الخلفية
    asyncio.create_task(auto_leave_manager())
    
    print("🚀 تم تشغيل البوت واليوزربوتات بنجاح!")
    
    # بدء تشغيل البوت الرسمي
    await bot.start(bot_token=BOT_TOKEN)
    await bot.run_until_disconnected()

if __name__ == '__main__':
    try:
        asyncio.run(main_application_start())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"FATAL ERROR: {e}")
