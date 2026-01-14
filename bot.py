import os
import sys
import asyncio
import logging
import time
import re
import aiohttp
from openai import AsyncOpenAI
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.tl.functions.channels import JoinChannelRequest, LeaveChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.types import User
from motor.motor_asyncio import AsyncIOMotorClient
from aiohttp import web
from dotenv import load_dotenv

# تحميل متغيرات البيئة من ملف .env إذا وجد
load_dotenv()

# ==========================================
#      1. الإعدادات والتهيئة
# ==========================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- استدعاء المتغيرات من النظام مع التحقق ---
API_ID_RAW = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")

# التحقق من وجود القيم الأساسية قبل البدء
if not all([API_ID_RAW, API_HASH, BOT_TOKEN, MONGO_URI]):
    missing = [k for k, v in {"API_ID": API_ID_RAW, "API_HASH": API_HASH, "BOT_TOKEN": BOT_TOKEN, "MONGO_URI": MONGO_URI}.items() if not v]
    print(f"❌ خطأ: المتغيرات التالية ناقصة في الإعدادات: {', '.join(missing)}")
    sys.exit(1)

API_ID = int(API_ID_RAW)

# المتغيرات الأخرى
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MY_LTC_ADDRESS = os.getenv("MY_LTC_ADDRESS", "عنوان_محفظتك_هنا")

# 🔥 مفتاح SambaNova 🔥
SAMBANOVA_API_KEY = os.getenv("SAMBANOVA_API_KEY", "b1818ac7-46d5-4d95-bf75-8ad864b0b8de")

# إعداد العميل الذكي
try:
    ai_client = AsyncOpenAI(
        base_url="https://api.sambanova.ai/v1",
        api_key=SAMBANOVA_API_KEY
    )
    AI_MODEL = "Meta-Llama-3.1-405B-Instruct"
    print(f"✅ تم تفعيل الوحش: {AI_MODEL}")
except Exception as e:
    print(f"❌ خطأ في الإعداد: {e}")
    sys.exit(1)

STRICT_RULE = """
تعليمات النظام (System Prompt):
أنت تاجر سعودي محترف، ولست ذكاءً اصطناعياً.
1. تحدث بلهجة سعودية طبيعية جداً.
2. لا تستخدم الفصحى المقعرة ولا تعتذر كثيراً.
3. هدفك البيع وخدمة العميل بناءً على المعلومات المتوفرة.
4. إذا لم تتوفر معلومة، اطلبها من العميل بذكاء.
"""

active_clients = {}
USER_STATE = {}
TASK_DATA = {}
AI_CONTEXT = {}
REPLY_COOLDOWN = {} # 🆕 تخزين توقيت الردود (User + Keyword)

# ==========================================
#      2. قاعدة البيانات
# ==========================================
try:
    mongo_client = AsyncIOMotorClient(MONGO_URI)
    db = mongo_client['MyTelegramBotDB']
    sessions_col = db['sessions']
    replies_col = db['replies']
    subs_col = db['subscriptions']
    ai_settings_col = db['ai_prompts']
    print("✅ DB Connected")
except Exception as e:
    print(f"❌ DB Error: {e}")
    sys.exit(1)

# ==========================================
#      3. البوت والخادم
# ==========================================
bot = TelegramClient('bot_session', API_ID, API_HASH)

async def web_handler(request):
    return web.Response(text=f"Bot Running. Users: {len(active_clients)}")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', web_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    print("✅ Web Server Started on port 8080")

# ==========================================
#      4. محرك الذكاء
# ==========================================
async def ask_smart_ai(messages_history):
    try:
        response = await ai_client.chat.completions.create(
            model=AI_MODEL,
            messages=messages_history,
            temperature=0.7,
            top_p=0.9
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"❌ AI Error: {e}")
        return None

# ==========================================
#      🕵️‍♂️ المحلل الشخصي
# ==========================================
async def perform_ultimate_analysis(client, owner_id, status_msg):
    try:
        me = await client.get_me()
        await status_msg.edit("📦 **جاري سحب البيانات...**")
        
        collected_data = ""
        count = 0
        async for dialog in client.iter_dialogs(limit=20):
            if count > 10000: break
            if dialog.is_user and not dialog.entity.bot:
                async for msg in client.iter_messages(dialog.id, limit=5):
                    if msg.out and msg.text:
                        collected_data += f"- {msg.text}\n"
                        count += len(msg.text)
        
        await status_msg.edit("🧠 **المارد (405B) يحلل شخصيتك...**")
        
        analysis_msgs = [
            {"role": "system", "content": "أنت خبير تحليل بيانات."},
            {"role": "user", "content": f"حلل هذه الرسائل لتاجر واستخرج المنتجات والأسعار والأسلوب، واكتب System Prompt شامل:\n{collected_data[:5000]}"}
        ]
        
        final_res = await ask_smart_ai(analysis_msgs)
        
        if final_res:
            await ai_settings_col.update_one({"owner_id": owner_id}, {"$set": {"prompt": final_res}}, upsert=True)
            try:
                await client.send_message("me", f"📝 **تقرير التحليل:**\n\n{final_res}")
            except:
                with open("report.txt", "w", encoding="utf-8") as f: f.write(final_res)
                await client.send_file("me", "report.txt", caption="📝 **التقرير**")
            return "✅ **تم الاستنساخ بذكاء 405B!**"
        else: return "❌ فشل التحليل."
    except Exception as e:
        return f"خطأ: {e}"

# ==========================================
#      5. فحص LTC
# ==========================================
async def verify_ltc(tx_hash):
    try:
        tx_hash = re.sub(r'[^a-fA-F0-9]', '', tx_hash)
        if len(tx_hash) < 10: return False, "هاش خطأ"
        url = f"https://api.blockcypher.com/v1/ltc/main/txs/{tx_hash}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                if response.status != 200: return False, "غير موجود"
                data = await response.json()
        found = False
        val = 0.0
        for out in data.get("outputs", []):
            if MY_LTC_ADDRESS in out.get("addresses", []):
                val = out.get("value", 0) / 100000000.0
                found = True
                break
        if found: return True, f"{val} LTC"
        else: return False, "لم تصلك"
    except: return False, "خطأ شبكة"

# ==========================================
#      6. تشغيل اليوزربوت
# ==========================================
async def start_userbot(owner_id, session_str):
    try:
        if owner_id in active_clients: await active_clients[owner_id].disconnect()
        client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
        await client.connect()
        if not await client.is_user_authorized():
            await sessions_col.delete_one({"_id": owner_id})
            return False
        client.owner_id = owner_id
        client.cooldowns = {} 
        client.add_event_handler(lambda e: userbot_incoming_handler(client, e), events.NewMessage(incoming=True))
        client.add_event_handler(lambda e: forced_sub_handler(client, e), events.NewMessage(incoming=True))
        active_clients[owner_id] = client
        return True
    except: return False

async def load_all_sessions():
    async for doc in sessions_col.find({}):
        asyncio.create_task(start_userbot(doc['_id'], doc['session_string']))

# ==========================================
#      7. المعالجات
# ==========================================
async def userbot_incoming_handler(client, event):
    if not event.is_private and not event.is_group: return 
    try:
        owner_id = client.owner_id
        text = event.raw_text or ""
        sender_id = event.sender_id # معرف المرسل
        
        # 1. التحقق من الردود المحفوظة (مع ميزة 10 دقائق)
        cursor = replies_col.find({"owner_id": owner_id})
        async for d in cursor:
            if d['keyword'] in text:
                # 🆕 --- المنطق الجديد (10 دقائق) ---
                # المفتاح: (رقم الشات، رقم المرسل، الكلمة)
                cool_key = (event.chat_id, sender_id, d['keyword'])
                last_reply_time = REPLY_COOLDOWN.get(cool_key, 0)
                current_time = time.time()
                
                # إذا لم تمر 10 دقائق (600 ثانية) تجاهل
                if current_time - last_reply_time < 600:
                    return 
                
                # تحديث الوقت والرد
                REPLY_COOLDOWN[cool_key] = current_time
                await event.reply(d['reply'])
                return 

        # 2. التحقق من الذكاء الاصطناعي (للخاص فقط)
        if not event.is_private: return

        settings = await ai_settings_col.find_one({"owner_id": owner_id})
        is_ai_active = settings.get('active', False) if settings else False
        has_img = bool(event.message.photo)

        if has_img:
            try:
                sender = await event.get_sender()
                await client.send_message("me", f"📸 **إثبات من:** {sender.first_name}", file=event.message.photo)
            except: pass

        if not is_ai_active: return 

        # مؤقت الذكاء الاصطناعي (5 ثواني لمنع الإزعاج العام)
        current_time = time.time()
        if current_time - client.cooldowns.get(event.chat_id, 0) > 5: 
            try:
                async with client.action(event.chat_id, 'typing'): await asyncio.sleep(1.5)
            except: pass

            pay_info = ""
            hm = re.search(r'\b[a-fA-F0-9]{64}\b', text)
            if hm:
                v, i = await verify_ltc(hm.group(0))
                pay_info = f"\n[النظام: العميل أرسل إشعار دفع نتيجته: {'تم' if v else 'فشل'} مبلغ {i}]"
            elif has_img: pay_info = "\n[النظام: العميل أرسل صورة]"

            saved_persona = settings.get('prompt', "أنت تاجر.") if settings else "أنت تاجر."
            msgs = [
                {"role": "system", "content": f"{STRICT_RULE}\n\nبياناتك وشخصيتك:\n{saved_persona}\n{pay_info}"},
                {"role": "user", "content": text if text else "صورة"}
            ]
            ai_reply = await ask_smart_ai(msgs)
            if ai_reply: await event.reply(ai_reply)
            client.cooldowns[event.chat_id] = current_time
    except: pass

async def forced_sub_handler(client, event):
    try:
        if any(x in event.raw_text.lower() for x in ["join", "اشترك"]):
            links = re.findall(r'(https?://t\.me/[^\s]+)', event.raw_text)
            for l in links: await process_temp_join(client, l)
            if event.message.buttons:
                for row in event.message.buttons:
                    for b in row:
                        if b.url: await process_temp_join(client, b.url)
                        else: 
                            await asyncio.sleep(2)
                            try: await b.click()
                            except: pass
    except: pass

async def process_temp_join(client, link):
    try:
        link = link.strip()
        cid = 0
        if "+" in link or "joinchat" in link:
            h = link.split("+")[-1].replace("https://t.me/joinchat/", "")
            u = await client(ImportChatInviteRequest(h))
            cid = u.chats[0].id
        else:
            link = link.replace('@', '').replace('https://t.me/', '')
            await client(JoinChannelRequest(link))
            en = await client.get_entity(link)
            cid = en.id
        if cid: await subs_col.update_one({"owner_id": client.owner_id, "chat_id": cid}, {"$set": {"join_time": time.time()}}, upsert=True)
    except: pass

# ==========================================
#      8. المهام الخلفية
# ==========================================
async def global_auto_leave():
    while True:
        try:
            now = time.time()
            async for d in subs_col.find({}):
                if now - d['join_time'] > 86400:
                    try: await active_clients[d['owner_id']](LeaveChannelRequest(d['chat_id']))
                    except: pass
                    await subs_col.delete_one({"_id": d['_id']})
        except: pass
        await asyncio.sleep(3600)

async def run_bc(client, msg, obj, trg):
    s = 0
    try:
        async for d in client.iter_dialogs():
            ok = (trg=="groups" and d.is_group) or (trg=="private" and d.is_user and not d.entity.bot)
            if ok:
                try: await client.send_message(d.id, obj); s+=1; await asyncio.sleep(0.5)
                except: pass
    except: pass
    await msg.reply(f"✅ تم النشر: {s}")

async def run_task(client, msg, h, k, r, delay):
    c = 0
    lim = time.time() - (h*3600)
    # 🆕 قائمة لتتبع من تم الرد عليهم في هذه المهمة فقط
    replied_users_this_task = set()
    
    try:
        me = await client.get_me()
        async for d in client.iter_dialogs(limit=None):
            if d.is_group:
                async for m in client.iter_messages(d.id, limit=20, search=k):
                    if m.date.timestamp() > lim and m.sender_id != me.id:
                        # 🆕 --- المنطق الجديد (رد واحد لكل مستخدم) ---
                        if m.sender_id in replied_users_this_task:
                            continue # تجاهل إذا رددنا عليه سابقاً في هذه المهمة
                        
                        try: 
                            await client.send_message(d.id, r, reply_to=m.id)
                            c+=1
                            replied_users_this_task.add(m.sender_id) # تسجيل المستخدم
                            await asyncio.sleep(delay)
                        except: pass
    except: pass
    await msg.reply(f"✅ تم الرد: {c}")

async def clean_acc(client, msg):
    c=0
    async for d in client.iter_dialogs():
        if isinstance(d.entity, User) and d.entity.deleted:
            try: await client.delete_dialog(d.id); c+=1
            except: pass
    await msg.edit(f"✅ حذف: {c}")

async def get_stats(client):
    try:
        d = await client.get_dialogs()
        return f"📊 محادثات: {len(d)}"
    except: return "خطأ"

# ==========================================
#      9. القائمة والتفاعل
# ==========================================
@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    await show_menu(event)

async def show_menu(event):
    cid = event.chat_id
    if cid in active_clients and await active_clients[cid].is_user_authorized():
        s = await ai_settings_col.find_one({"owner_id": cid})
        act = s.get('active', False) if s else False
        btn_text = "🟢 الذكاء يعمل" if act else "🔴 الذكاء متوقف"
        btn_data = b"ai_off" if act else b"ai_on"
        btns = [
            [Button.inline(btn_text, btn_data)],
            [Button.inline("🕵️‍♂️ استنساخ (405B)", b"deep_scan")],
            [Button.inline("🗣️ نقاش لتدريب البوت", b"consult"), Button.inline("💰 فحص LTC", b"chk_pay")],
            [Button.inline("📢 نشر للجروبات", b"bc_groups"), Button.inline("📢 نشر للخاص", b"bc_private")],
            [Button.inline("🚀 مهام بحث", b"task"), Button.inline("⏳ انضمام مؤقت", b"join")],
            [Button.inline("📊 إحصائيات", b"stats"), Button.inline("🧹 تنظيف", b"clean")],
            [Button.inline("➕ إضافة رد", b"add_rep"), Button.inline("📋 الردود", b"list_rep")],
            [Button.inline("🗑️ حذف رد", b"del_rep"), Button.inline("ℹ️ معلومات", b"info")]
        ]
        await event.respond("✅ **لوحة التحكم (SambaNova Llama 405B)**\n🚀 أذكى نموذج مجاني في العالم حالياً.", buttons=btns)
    else:
        await event.respond("👋", buttons=[[Button.inline("🔐 دخول", b"login")]])

@bot.on(events.CallbackQuery)
async def callback_handler(event):
    cid = event.chat_id
    data = event.data
    cli = active_clients.get(cid)
    if data == b"login":
        USER_STATE[cid] = "SESS"
        await event.respond("🔐 **كود الجلسة:**")
    elif data == b"ai_on":
        await ai_settings_col.update_one({"owner_id": cid}, {"$set": {"active": True}}, upsert=True)
        await show_menu(event)
    elif data == b"ai_off":
        await ai_settings_col.update_one({"owner_id": cid}, {"$set": {"active": False}}, upsert=True)
        await show_menu(event)
    elif data == b"deep_scan":
        if not cli: return
        msg = await event.respond("🚀 **بدأ التحليل بالذكاء الخارق...**")
        asyncio.create_task(perform_ultimate_analysis(cli, cid, msg))
    elif data == b"consult":
        USER_STATE[cid] = "CONSULT"
        AI_CONTEXT[cid] = [{"role": "system", "content": "أنت خبير تطوير أعمال. قم بإجراء مقابلة مع المستخدم (التاجر) لفهم منتجاته وأسعاره. اسأل سؤالاً واحداً في كل مرة."}]
        first_q = await ask_smart_ai(AI_CONTEXT[cid])
        AI_CONTEXT[cid].append({"role": "assistant", "content": first_q})
        await event.respond(f"🗣️ **بدء جلسة التدريب والمناقشة**\n\n{first_q}\n\n(لإنهاء وحفظ المناقشة اكتب: **تم**)")
    elif data == b"chk_pay":
        USER_STATE[cid] = "TX"
        await event.respond("💰 **الهاش:**")
    elif data == b"bc_groups":
        USER_STATE[cid] = "BC_GROUP"
        await event.respond("📢 **رسالة الجروبات:**")
    elif data == b"bc_private":
        USER_STATE[cid] = "BC_PRIVATE"
        await event.respond("📢 **رسالة الخاص:**")
    elif data == b"task":
        USER_STATE[cid] = "TASK_H"
        TASK_DATA[cid] = {}
        await event.respond("1️⃣ الساعات؟")
    elif data == b"join":
        USER_STATE[cid] = "JOIN"
        await event.respond("⏳ الرابط:")
    elif data == b"stats":
        msg = await get_stats(cli)
        await event.respond(msg)
    elif data == b"clean":
        m = await event.respond("🧹...")
        asyncio.create_task(clean_acc(cli, m))
    elif data == b"add_rep":
        USER_STATE[cid] = "ADD_KEY"
        await event.respond("📝 **الكلمة:**")
    elif data == b"list_rep":
        s="**📋 الردود:**\n"
        async for d in replies_col.find({"owner_id": cid}): s+=f"- `{d['keyword']}`\n"
        await event.respond(s)
    elif data == b"del_rep":
        USER_STATE[cid] = "DEL_KEY"
        await event.respond("🗑️ **الكلمة:**")
    elif data == b"info":
        await event.respond("🤖 **Model:** Llama 3.1 405B (SambaNova)\n✅ **Status:** Super Intelligent")

@bot.on(events.NewMessage)
async def input_handler(event):
    cid = event.chat_id
    txt = event.text.strip()
    st = USER_STATE.get(cid)
    if not st or txt.startswith('/'): return
    if st == "SESS":
        if await start_userbot(cid, txt):
            await sessions_col.update_one({"_id": cid}, {"$set": {"session_string": txt}}, upsert=True)
            await event.respond("✅")
            await show_menu(event)
        else: await event.respond("❌")
        USER_STATE[cid] = None
    elif st == "CONSULT":
        if txt == "تم" or txt == "انتهى":
            await event.respond("⏳ **جاري تلخيص المناقشة وحفظ شخصية البوت...**")
            AI_CONTEXT[cid].append({"role": "user", "content": "تم. الآن بناءً على كل نقاشنا السابق، اكتب System Prompt نهائي وشامل يمثلني كتاجر، يتضمن كل الأسعار والخدمات."})
            final_save = await ask_smart_ai(AI_CONTEXT[cid])
            if final_save:
                await ai_settings_col.update_one({"owner_id": cid}, {"$set": {"prompt": final_save}}, upsert=True)
                await event.respond(f"✅ **تم الحفظ!**\n\nالبوت الآن جاهز ويعرف كل التفاصيل.\n`{final_save[:200]}...`")
            else: await event.respond("❌ حدث خطأ أثناء الحفظ.")
            USER_STATE[cid] = None
            AI_CONTEXT[cid] = []
        else:
            async with bot.action(cid, 'typing'):
                AI_CONTEXT[cid].append({"role": "user", "content": txt})
                ai_response = await ask_smart_ai(AI_CONTEXT[cid])
                if ai_response:
                    AI_CONTEXT[cid].append({"role": "assistant", "content": ai_response})
                    await event.reply(ai_response)
    elif st == "TX":
        v, i = await verify_ltc(txt)
        await event.respond(f"{'✅' if v else '❌'} {i}")
        USER_STATE[cid] = None
    elif st == "BC_GROUP":
        m = await event.respond("🚀...")
        asyncio.create_task(run_bc(active_clients[cid], m, event.message, "groups"))
        USER_STATE[cid] = None
    elif st == "BC_PRIVATE":
        m = await event.respond("🚀...")
        asyncio.create_task(run_bc(active_clients[cid], m, event.message, "private"))
        USER_STATE[cid] = None
    elif st == "JOIN":
        m = await event.respond("⏳...")
        asyncio.create_task(process_temp_join(active_clients[cid], txt))
        USER_STATE[cid] = None
    elif st == "ADD_KEY":
        TASK_DATA[cid] = {"k": txt}
        USER_STATE[cid] = "VAL"
        await event.respond("📝 **الرد:**")
    elif st == "VAL":
        await replies_col.update_one({"owner_id": cid, "keyword": TASK_DATA[cid]["k"]}, {"$set": {"reply": txt}}, upsert=True)
        await event.respond("✅")
        USER_STATE[cid] = None
    elif st == "DEL_KEY":
        await replies_col.delete_one({"owner_id": cid, "keyword": txt})
        await event.respond("🗑️")
        USER_STATE[cid] = None
    elif st == "TASK_H":
        try:
            TASK_DATA[cid] = {"h": int(txt)}
            USER_STATE[cid] = "TK"
            await event.respond("🔎 **كلمة:**")
        except: await event.respond("❌ رقم خطأ")
    elif st == "TK":
        TASK_DATA[cid]["k"] = txt
        USER_STATE[cid] = "TR"
        await event.respond("📝 **الرد:**")
    elif st == "TR":
        TASK_DATA[cid]["r"] = event.message
        USER_STATE[cid] = "TD"
        await event.respond("⏱️ **ثواني:**")
    elif st == "TD":
        try:
            m = await event.respond("🚀...")
            asyncio.create_task(run_task(active_clients[cid], m, TASK_DATA[cid]["h"], TASK_DATA[cid]["k"], TASK_DATA[cid]["r"], int(txt)))
            USER_STATE[cid] = None
        except: await event.respond("❌ رقم خطأ")

async def main():
    await start_web_server()
    await load_all_sessions()
    asyncio.create_task(global_auto_leave())
    print("✅ Bot Started (SambaNova Engine)")
    await bot.start(bot_token=BOT_TOKEN)
    await bot.run_until_disconnected()

if __name__ == '__main__':
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main())
    except KeyboardInterrupt: pass
    except Exception as e: print(f"Error: {e}")
