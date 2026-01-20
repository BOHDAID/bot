import os
import sys
import asyncio
import logging
import time
import re
import aiohttp
from datetime import datetime
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.tl.types import UserStatusOnline, UserStatusRecently, ChannelParticipantsAdmins
from telethon.tl.functions.messages import ImportChatInviteRequest, GetHistoryRequest
from telethon.tl.functions.channels import JoinChannelRequest, LeaveChannelRequest
from motor.motor_asyncio import AsyncIOMotorClient
from aiohttp import web
from openai import AsyncOpenAI
from dotenv import load_dotenv

# تحميل متغيرات البيئة
load_dotenv()

# ==========================================
#      1. الإعدادات والتهيئة
# ==========================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- استدعاء المتغيرات ---
API_ID_RAW = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")

if not all([API_ID_RAW, API_HASH, BOT_TOKEN, MONGO_URI]):
    print(f"❌ خطأ: المتغيرات ناقصة في ملف .env أو إعدادات السيرفر.")
    sys.exit(1)

API_ID = int(API_ID_RAW)
MY_LTC_ADDRESS = os.getenv("MY_LTC_ADDRESS", "Your_Address_Here")
SAMBANOVA_API_KEY = os.getenv("SAMBANOVA_API_KEY", "b1818ac7-46d5-4d95-bf75-8ad864b0b8de")

# إعداد العميل الذكي
try:
    ai_client = AsyncOpenAI(base_url="https://api.sambanova.ai/v1", api_key=SAMBANOVA_API_KEY)
    AI_MODEL = "Meta-Llama-3.1-405B-Instruct"
except: pass

STRICT_RULE = """
أنت تاجر سعودي محترف. 
- لهجتك سعودية عامية.
- هدفك البيع وخدمة العميل.
- لا تعتذر كثيراً وكن واثقاً.
"""

active_clients = {}
USER_STATE = {}
TASK_DATA = {}
AUTO_POST_CONFIG = {} 
LAST_MSG_IDS = {} 
REPLY_COOLDOWN = {} # لتخزين توقيت الردود (10 دقائق)

# ==========================================
#      2. قاعدة البيانات
# ==========================================
try:
    mongo_client = AsyncIOMotorClient(MONGO_URI)
    db = mongo_client['MyTelegramBotDB']
    sessions_col = db['sessions']
    replies_col = db['replies']      # الردود التلقائية
    reactions_col = db['reactions']  # التفاعلات
    ai_settings_col = db['ai_prompts'] # إعدادات الذكاء
    config_col = db['autopost_config'] # إعدادات النشر الحربي
    blacklist_col = db['groups_blacklist'] # الجروبات المجمدة
    admins_watch_col = db['admins_watch']  # رادار المشرفين
    print("✅ DB Connected - All Systems Ready")
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

# ==========================================
#      4. أدوات مساعدة (AI & LTC)
# ==========================================
async def ask_smart_ai(messages_history):
    try:
        response = await ai_client.chat.completions.create(
            model=AI_MODEL, messages=messages_history, temperature=0.7, top_p=0.9
        )
        return response.choices[0].message.content
    except: return None

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
#      5. تشغيل اليوزربوت والمهام
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

        # 1. المعالج العام (ردود، تفاعل، ذكاء)
        client.add_event_handler(lambda e: main_incoming_handler(client, e), events.NewMessage(incoming=True))
        # 2. معالج الاشتراك الآمن
        client.add_event_handler(lambda e: safe_join_handler(client, e), events.NewMessage(incoming=True))
        # 3. ⚔️ مراقب تجميد المشرفين
        client.add_event_handler(lambda e: admin_reply_monitor(client, e), events.NewMessage(incoming=True))
        # 4. ⚔️ مراقب فك التجميد (رد المالك)
        client.add_event_handler(lambda e: owner_reply_resume_handler(client, e), events.NewMessage(outgoing=True))
        
        active_clients[owner_id] = client
        
        # استعادة النشر التلقائي
        saved_config = await config_col.find_one({"owner_id": owner_id})
        if saved_config and saved_config.get('active', False):
            asyncio.create_task(autopost_engine(client, owner_id))
            
        return True
    except: return False

async def load_all_sessions():
    async for doc in sessions_col.find({}):
        asyncio.create_task(start_userbot(doc['_id'], doc['session_string']))

# ==========================================
#      6. المعالجات الأساسية (Handlers)
# ==========================================
async def main_incoming_handler(client, event):
    if not event.is_private and not event.is_group: return 
    try:
        owner_id = client.owner_id
        text = event.raw_text or ""
        sender_id = event.sender_id 
        
        # أ. التفاعل الصامت (Auto-React)
        cursor_react = reactions_col.find({"owner_id": owner_id})
        async for d in cursor_react:
            if d['keyword'] in text:
                try: await event.message.react(d['emoji']); break
                except: pass

        # ب. الردود التلقائية (مع ميزة 10 دقائق Cooldown)
        cursor = replies_col.find({"owner_id": owner_id})
        async for d in cursor:
            if d['keyword'] in text:
                cool_key = (event.chat_id, sender_id, d['keyword'])
                last_reply = REPLY_COOLDOWN.get(cool_key, 0)
                # الشرط: إذا لم تمر 600 ثانية (10 دقائق) -> تجاهل
                if time.time() - last_reply < 600: return 
                REPLY_COOLDOWN[cool_key] = time.time()
                await event.reply(d['reply'])
                return 

        # ج. الذكاء الاصطناعي (للخاص فقط)
        if not event.is_private: return
        settings = await ai_settings_col.find_one({"owner_id": owner_id})
        if settings and settings.get('active', False):
            if time.time() - client.cooldowns.get(event.chat_id, 0) > 5: 
                async with client.action(event.chat_id, 'typing'): await asyncio.sleep(1.5)
                
                pay_info = ""
                hm = re.search(r'\b[a-fA-F0-9]{64}\b', text)
                if hm:
                    v, i = await verify_ltc(hm.group(0))
                    pay_info = f"\n[فحص الدفع: {'تم' if v else 'فشل'} مبلغ {i}]"
                elif event.message.photo: pay_info = "\n[العميل أرسل صورة]"
                
                msgs = [{"role": "system", "content": f"{STRICT_RULE}\n{settings.get('prompt', '')}\n{pay_info}"}, 
                        {"role": "user", "content": text or "صورة"}]
                ai_reply = await ask_smart_ai(msgs)
                if ai_reply: await event.reply(ai_reply)
                client.cooldowns[event.chat_id] = time.time()
    except: pass

async def safe_join_handler(client, event):
    """ الانضمام الآمن: ينضم فقط إذا كانت الرسالة رداً عليك """
    try:
        if not (event.is_reply or event.mentioned): return 
        reply_msg = await event.get_reply_message()
        me = await client.get_me()
        if reply_msg.sender_id != me.id: return # تجاهل إذا لم يرد عليك

        if any(x in event.raw_text.lower() for x in ["join", "اشترك"]):
            links = re.findall(r'(https?://t\.me/[^\s]+)', event.raw_text)
            for l in links: 
                try:
                    if "+" in l: await client(ImportChatInviteRequest(l.split("+")[-1]))
                    else: await client(JoinChannelRequest(l))
                except: pass
            if event.message.buttons:
                for row in event.message.buttons:
                    for b in row:
                        if b.url: 
                            try: await client(JoinChannelRequest(b.url)) 
                            except: pass
                        else: 
                            try: await b.click()
                            except: pass
    except: pass

# ==========================================
#      7. ⚔️ نظام النشر الحربي (Sniper Logic)
# ==========================================

# --- الرادار (فحص المشرفين) ---
async def check_admin_danger(client, owner_id):
    danger = False
    try:
        cursor = admins_watch_col.find({"owner_id": owner_id})
        async for doc in cursor:
            try:
                entity = await client.get_entity(doc['username'])
                if isinstance(entity.status, (UserStatusOnline, UserStatusRecently)):
                    danger = True; break 
            except: pass
    except: pass
    return danger

# --- المحرك ---
async def autopost_engine(client, owner_id):
    print(f"🚀 War Engine Started for {owner_id}")
    while True:
        config = await config_col.find_one({"owner_id": owner_id})
        if not config or not config.get('active', False): break 

        target_groups = config['groups']
        for chat_id in target_groups:
            # 1. هل الجروب مجمد؟
            if await blacklist_col.find_one({"owner_id": owner_id, "chat_id": chat_id}): continue 
            
            # 2. هل الرادار يكشف خطر؟
            if await check_admin_danger(client, owner_id):
                # حذف آخر رسالة واختفاء 5 دقائق
                last_msg_id = LAST_MSG_IDS.get(f"{owner_id}_{chat_id}")
                if last_msg_id:
                    try: await client.delete_messages(chat_id, [last_msg_id])
                    except: pass
                await asyncio.sleep(300)
                continue 
            
            # 3. النشر
            try:
                sent = await client.send_message(int(chat_id), config['message'])
                LAST_MSG_IDS[f"{owner_id}_{chat_id}"] = sent.id
                await asyncio.sleep(3)
            except: pass
        
        await asyncio.sleep(config['interval'] * 60)

# --- تجميد الاشتباك (عند رد الأدمن) ---
async def admin_reply_monitor(client, event):
    try:
        if not event.is_group or not event.is_reply: return
        me = await client.get_me()
        reply = await event.get_reply_message()
        if reply.sender_id != me.id: return
        
        sender = await event.get_sender()
        perms = await client.get_permissions(event.chat_id, sender)
        if perms.is_admin or perms.is_creator:
            # تجميد وحفظ هوية المشرف
            await blacklist_col.update_one(
                {"owner_id": client.owner_id, "chat_id": event.chat_id},
                {"$set": {"reason": "AdminReply", "admin_id": sender.id, "ts": time.time()}},
                upsert=True
            )
            await client.send_message("me", f"⛔ **تم تجميد الجروب:** {event.chat.title}\n👮 المشرف: {sender.id}\n💡 **الحل:** رد على هذا المشرف لفك الحظر.")
    except: pass

# --- فك الاشتباك (عند ردك على المشرف) ---
async def owner_reply_resume_handler(client, event):
    try:
        if not event.is_group or not event.is_reply: return
        owner_id = client.owner_id
        chat_id = event.chat_id
        
        frozen = await blacklist_col.find_one({"owner_id": owner_id, "chat_id": chat_id})
        if not frozen: return
        
        reply_msg = await event.get_reply_message()
        if reply_msg.sender_id == frozen.get('admin_id'):
            # إصابة دقيقة ✅
            await blacklist_col.delete_one({"owner_id": owner_id, "chat_id": chat_id})
            await client.send_message("me", f"✅ **تم استئناف النشر!** لقد رديت على المشرف.")
    except: pass

# ==========================================
#      8. مهام البحث (Task Sniper)
# ==========================================
async def run_task(client, msg, h, k, r, delay):
    c = 0
    lim = time.time() - (h*3600)
    replied_users = set() # Anti-Spam (رد واحد لكل شخص)
    try:
        me = await client.get_me()
        async for d in client.iter_dialogs(limit=None):
            if d.is_group:
                async for m in client.iter_messages(d.id, limit=20, search=k):
                    if m.date.timestamp() > lim and m.sender_id != me.id:
                        if m.sender_id in replied_users: continue 
                        try: 
                            await client.send_message(d.id, r, reply_to=m.id)
                            replied_users.add(m.sender_id)
                            c+=1; await asyncio.sleep(delay)
                        except: pass
    except: pass
    await msg.reply(f"✅ انتهت المهمة. تم الرد على: {c}")

# ==========================================
#      9. القائمة والتفاعل
# ==========================================
@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    await show_menu(event)

async def show_menu(event):
    cid = event.chat_id
    if cid in active_clients and await active_clients[cid].is_user_authorized():
        conf = await config_col.find_one({"owner_id": cid})
        st_pub = "🟢" if conf and conf.get('active') else "🔴"
        
        btns = [
            [Button.inline(f"النشر الحربي {st_pub}", b"menu_autopost"), Button.inline("🕵️‍♂️ الرادار", b"watch_admin_menu")],
            [Button.inline("🚀 مهام البحث", b"task"), Button.inline("🤖 الذكاء", b"toggle_ai")],
            [Button.inline("➕ رد تلقائي", b"add_rep"), Button.inline("🎭 تفاعل", b"add_react")],
            [Button.inline("🗑️ حذف رد", b"del_rep"), Button.inline("❄️ المجمدة", b"show_blacklist")],
            [Button.inline("📊 الحالة", b"stats")]
        ]
        await event.respond("⚔️ **نظام التاجر الحربي (Full Version)**", buttons=btns)
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

    # --- القوائم الفرعية ---
    elif data == b"menu_autopost":
        btns = [[Button.inline("⚙️ إعداد جديد", b"setup_autopost"), Button.inline("🟢/🔴 تشغيل/إيقاف", b"toggle_autopost")]]
        await event.respond("📢 **إعدادات النشر:**", buttons=btns)
        
    elif data == b"setup_autopost":
        AUTO_POST_CONFIG[cid] = {}
        USER_STATE[cid] = "SET_MSG"
        await event.respond("📝 **أرسل الرسالة:**")
        
    elif data == b"toggle_autopost":
        conf = await config_col.find_one({"owner_id": cid})
        new_st = not conf.get('active', False) if conf else False
        if not conf: return await event.respond("❌ لا توجد إعدادات!")
        await config_col.update_one({"owner_id": cid}, {"$set": {"active": new_st}}, upsert=True)
        if new_st: asyncio.create_task(autopost_engine(cli, cid))
        await event.respond(f"الحالة: {'🟢' if new_st else '🔴'}")

    elif data == b"watch_admin_menu":
        s = "**👮 المراقبين:**\n"
        async for doc in admins_watch_col.find({"owner_id": cid}): s += f"- @{doc['username']}\n"
        btns = [[Button.inline("➕ إضافة", b"add_watch"), Button.inline("🗑️ حذف", b"del_watch")]]
        await event.respond(s, buttons=btns)
        
    elif data == b"add_watch": USER_STATE[cid] = "ADD_ADMIN"; await event.respond("اليوزر (بدون @):")
    elif data == b"del_watch": USER_STATE[cid] = "DEL_ADMIN"; await event.respond("اليوزر:")

    elif data == b"task": USER_STATE[cid] = "TASK_H"; TASK_DATA[cid] = {}; await event.respond("1️⃣ الساعات؟")
    elif data == b"add_rep": USER_STATE[cid] = "ADD_KEY"; await event.respond("الكلمة:")
    elif data == b"del_rep": USER_STATE[cid] = "DEL_KEY"; await event.respond("الكلمة:")
    elif data == b"add_react": USER_STATE[cid] = "ADD_REACT_KEY"; await event.respond("الكلمة:")
    
    elif data == b"show_blacklist":
        s = "**❄️ الجروبات المجمدة:**\n"
        async for doc in blacklist_col.find({"owner_id": cid}): s += f"- Chat: `{doc['chat_id']}` (Admin: {doc.get('admin_id')})\n"
        await event.respond(s or "✅ نظيف", buttons=[[Button.inline("فك الكل", b"clear_bl")]])
    elif data == b"clear_bl":
        await blacklist_col.delete_many({"owner_id": cid})
        await event.respond("✅ تم.")
        
    elif data == b"stats":
        if cli: d = await cli.get_dialogs(); await event.respond(f"📊 المحادثات: {len(d)}")

@bot.on(events.NewMessage)
async def input_handler(event):
    cid = event.chat_id
    txt = event.text.strip()
    st = USER_STATE.get(cid)
    if not st or txt.startswith('/'): return
    
    if st == "SESS":
        if await start_userbot(cid, txt):
            await sessions_col.update_one({"_id": cid}, {"$set": {"session_string": txt}}, upsert=True)
            await event.respond("✅"); await show_menu(event)
        else: await event.respond("❌")
        USER_STATE[cid] = None

    # --- النشر ---
    elif st == "SET_MSG":
        AUTO_POST_CONFIG[cid]['msg'] = txt; USER_STATE[cid] = "SET_TIME"
        await event.respond("⏱️ الدقائق؟")
    elif st == "SET_TIME":
        try:
            AUTO_POST_CONFIG[cid]['time'] = int(txt); USER_STATE[cid] = "SEL_GROUPS"
            cli = active_clients.get(cid)
            my_groups = []
            async for d in cli.iter_dialogs(limit=30):
                if d.is_group: my_groups.append([Button.inline(d.name[:20], f"p_sel_{d.id}")])
            my_groups.append([Button.inline("✅ حفظ", "save_post")])
            AUTO_POST_CONFIG[cid]['groups'] = []
            await event.respond("اختر الجروبات:", buttons=my_groups)
        except: pass

    # --- الأدوات ---
    elif st == "ADD_ADMIN":
        await admins_watch_col.update_one({"owner_id": cid, "username": txt.replace("@","")}, {"$set": {"ts": time.time()}}, upsert=True)
        await event.respond("✅"); USER_STATE[cid] = None
    elif st == "DEL_ADMIN":
        await admins_watch_col.delete_one({"owner_id": cid, "username": txt.replace("@","")})
        await event.respond("🗑️"); USER_STATE[cid] = None
        
    # --- المهام ---
    elif st == "ADD_KEY": TASK_DATA[cid] = {"k": txt}; USER_STATE[cid] = "VAL"; await event.respond("الرد:")
    elif st == "VAL":
        await replies_col.update_one({"owner_id": cid, "keyword": TASK_DATA[cid]["k"]}, {"$set": {"reply": txt}}, upsert=True)
        await event.respond("✅"); USER_STATE[cid] = None
        
    elif st == "ADD_REACT_KEY": TASK_DATA[cid] = {"k": txt}; USER_STATE[cid] = "ADD_REACT_EMOJI"; await event.respond("الإيموجي:")
    elif st == "ADD_REACT_EMOJI":
        await reactions_col.update_one({"owner_id": cid, "keyword": TASK_DATA[cid]["k"]}, {"$set": {"emoji": txt}}, upsert=True)
        await event.respond("✅"); USER_STATE[cid] = None

    elif st == "TASK_H":
        try: TASK_DATA[cid] = {"h": int(txt)}; USER_STATE[cid] = "TK"; await event.respond("الكلمة:")
        except: pass
    elif st == "TK": TASK_DATA[cid]["k"] = txt; USER_STATE[cid] = "TR"; await event.respond("الرد:")
    elif st == "TR": TASK_DATA[cid]["r"] = event.message; USER_STATE[cid] = "TD"; await event.respond("الانتظار (ثواني):")
    elif st == "TD":
        try:
            m = await event.respond("🚀...")
            asyncio.create_task(run_task(active_clients[cid], m, TASK_DATA[cid]["h"], TASK_DATA[cid]["k"], TASK_DATA[cid]["r"], int(txt)))
            USER_STATE[cid] = None
        except: pass

@bot.on(events.CallbackQuery(pattern=r'p_sel_'))
async def post_group_sel(event):
    cid = event.chat_id; gid = int(event.data.decode().split('_')[2])
    if 'groups' not in AUTO_POST_CONFIG.get(cid, {}): AUTO_POST_CONFIG[cid]['groups'] = []
    if gid not in AUTO_POST_CONFIG[cid]['groups']:
        AUTO_POST_CONFIG[cid]['groups'].append(gid); await event.answer("✅")
    else:
        AUTO_POST_CONFIG[cid]['groups'].remove(gid); await event.answer("❌")

@bot.on(events.CallbackQuery(pattern=b'save_post'))
async def save_post_final(event):
    cid = event.chat_id; data = AUTO_POST_CONFIG.get(cid)
    if not data or not data.get('groups'): return await event.respond("❌")
    await config_col.update_one({"owner_id": cid}, {"$set": {"message": data['msg'], "interval": data['time'], "groups": data['groups'], "active": True}}, upsert=True)
    cli = active_clients.get(cid); asyncio.create_task(autopost_engine(cli, cid))
    await event.respond("✅ تم التشغيل"); USER_STATE[cid] = None

async def main():
    await start_web_server()
    await load_all_sessions()
    print("✅ Bot Started (All Features Included)")
    await bot.start(bot_token=BOT_TOKEN)
    await bot.run_until_disconnected()

if __name__ == '__main__':
    try: loop = asyncio.get_event_loop(); loop.run_until_complete(main())
    except: pass
