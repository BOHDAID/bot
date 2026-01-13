# ==============================================================================
# 🤖 TELEGRAM USERBOT - SINGLE USER (RENDER + MONGODB FIXED)
# ==============================================================================

import asyncio
import json
import os
import time
import random
import datetime
import requests
import traceback
import zipfile
import io
import sys
import warnings
import logging
import pymongo
import certifi
from aiohttp import web
from fpdf import FPDF
import arabic_reshaper
from bidi.algorithm import get_display
from telethon import TelegramClient, events, Button, functions, types
from telethon.sessions import StringSession
from telethon.tl.functions.channels import CreateChannelRequest, EditBannedRequest, InviteToChannelRequest, GetParticipantsRequest, JoinChannelRequest
from telethon.tl.functions.messages import SendReactionRequest, SetTypingRequest, ReadHistoryRequest, DeleteHistoryRequest
from telethon.tl.functions.account import UpdateProfileRequest, UpdateStatusRequest
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.types import SendMessageCancelAction, ChannelParticipantsAdmins, UserStatusOnline, UserStatusOffline, UserStatusRecently
from telethon.errors import MessageNotModifiedError, FloodWaitError

# --- إعدادات النظام ---
warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO)

# --- المتغيرات (من Render Environment) ---
# يتم سحب البيانات من إعدادات الموقع
API_ID = int(os.environ.get("API_ID", 6))
API_HASH = os.environ.get("API_HASH", "eb06d4abfb49dc3eeb1aeb98ae0f581e")
BOT_TOKEN = os.environ.get("BOT_TOKEN") 
MONGO_URI = os.environ.get("MONGO_URI")

LOGO_FILE = "saved_store_logo.jpg"
FONT_FILE = "font.ttf"
FONT_URL = "https://github.com/google/fonts/raw/main/ofl/amiri/Amiri-Regular.ttf"

# --- الاتصال بقاعدة البيانات (MongoDB) ---
mongo_client = None
db = None
settings_collection = None

print("⏳ جاري الاتصال بقاعدة البيانات...")
try:
    if MONGO_URI:
        mongo_client = pymongo.MongoClient(MONGO_URI, tlsCAFile=certifi.where())
        db = mongo_client["telegram_userbot_db"]
        settings_collection = db["settings"]
        print("✅ تم الاتصال بقاعدة البيانات بنجاح!")
    else:
        print("⚠️ تحذير: لم يتم وضع رابط MONGO_URI في الإعدادات.")
except Exception as e:
    print(f"❌ خطأ في الاتصال بقاعدة البيانات: {e}")

# --- تحميل الخط ---
if not os.path.exists(FONT_FILE) or os.path.getsize(FONT_FILE) < 1000:
    try:
        r = requests.get(FONT_URL)
        with open(FONT_FILE, 'wb') as f: f.write(r.content)
    except: pass

# --- تشغيل العميل ---
bot = None
try:
    bot = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)
except:
    bot = TelegramClient('bot_session', API_ID, API_HASH)

user_client = None
bio_task = None

# --- الإعدادات الافتراضية ---
default_settings = {
    "_id": "bot_config", "session": None, "running": False, "log_channel": None,
    "spy_mode": False, "ghost_mode": False, "anti_typing": False, "fake_offline": False,
    "keywords": [], "replies": [], "typing_delay": 2, "work_mode": False,
    "work_start": 0, "work_end": 23,
    "store_name": "My Store", "store_user": "@Store", "invoices_archive": {},
    "auto_bio": False, "bio_template": "Time: %TIME% | Online",
    "stalk_list": [], "typing_watch_list": [],
    "anti_link_group": False, "auto_save_destruct": True,
    "reaction_mode": False, "reaction_emoji": "❤️"
}

settings = default_settings.copy()
user_cooldowns = {}
user_state = {}
invoice_drafts = {}
temp_scan_data = {}
message_cache = {}
active_relay_config = {}

# --- دوال البيانات (تم التعديل لتدعم Mongo) ---
def save_data():
    if settings_collection is None: return
    try:
        settings_collection.replace_one({"_id": "bot_config"}, settings, upsert=True)
    except Exception as e:
        print(f"Error saving: {e}")

def load_data():
    global settings
    if settings_collection is None: return
    try:
        data = settings_collection.find_one({"_id": "bot_config"})
        if data:
            for k in data: settings[k] = data[k]
            print("☁️ تم تحميل البيانات.")
        else:
            save_data()
        
        # ضمان وجود القوائم
        if "keywords" not in settings: settings["keywords"] = []
        if "replies" not in settings: settings["replies"] = []
        if "invoices_archive" not in settings: settings["invoices_archive"] = {}
    except: pass

def is_working_hour():
    if not settings["work_mode"]: return True
    h = datetime.datetime.now().hour
    return settings["work_start"] <= h < settings["work_end"]

# --- نظام الفواتير ---
def fix_text(text):
    if not text: return ""
    try: return get_display(arabic_reshaper.reshape(str(text)))
    except: return str(text)

def create_arabic_invoice(data, code_16, output_filename):
    try:
        pdf = FPDF()
        pdf.add_page()
        is_ar = False
        if os.path.exists(FONT_FILE):
            pdf.add_font('Amiri', '', FONT_FILE, uni=True)
            is_ar = True
        
        pdf.set_font('Amiri' if is_ar else 'Helvetica', '', 12)
        def t(a, e): return fix_text(str(a)) if is_ar else str(e)

        # Header
        pdf.set_fill_color(100, 50, 150); pdf.rect(0, 0, 210, 45, 'F')
        if os.path.exists(LOGO_FILE):
            pdf.image(LOGO_FILE, x=95, y=5, w=25)
        
        pdf.set_text_color(255, 255, 255); pdf.set_font_size(26); pdf.set_xy(0, 32)
        pdf.cell(210, 10, text=t("INVOICE / فاتورة", "INVOICE"), ln=True, align='C')
        pdf.ln(15)

        # Ref
        pdf.set_text_color(0, 0, 0); pdf.set_font_size(12)
        pdf.cell(0, 10, text=str(f"Ref: {code_16}"), ln=True, align='C'); pdf.ln(8)

        # Details
        store_name = settings.get("store_name", "Store")
        client_name = data.get('client_name', 'Client')
        date_str = datetime.datetime.now().strftime("%Y-%m-%d")

        pdf.set_fill_color(240, 240, 240); pdf.set_font_size(16)
        pdf.cell(190, 12, text=t("تفاصيل الفاتورة", "Details"), ln=True, align='R' if is_ar else 'L', fill=True)
        
        pdf.set_font_size(14)
        align = 'R' if is_ar else 'L'
        pdf.cell(190, 9, text=t(f"المتجر: {store_name}", f"Store: {store_name}"), ln=True, align=align)
        pdf.cell(190, 9, text=t(f"العميل: {client_name}", f"Client: {client_name}"), ln=True, align=align)
        pdf.cell(190, 9, text=t(f"التاريخ: {date_str}", f"Date: {date_str}"), ln=True, align=align)
        pdf.ln(12)

        # Table
        pdf.set_fill_color(100, 50, 150); pdf.set_text_color(255, 255, 255); pdf.set_font_size(14)
        cols = ["السعر", "الضمان", "العدد", "المنتج"]
        w = [35, 45, 25, 85]
        
        if is_ar:
            for i in range(4): pdf.cell(w[i], 12, text=t(cols[i], ""), border=1, align='C', fill=True)
        else:
            for i in reversed(range(4)): pdf.cell(w[i], 12, text=cols[i], border=1, align='C', fill=True)
        pdf.ln()

        pdf.set_text_color(0, 0, 0)
        vals = [
            str(data.get('price', '0')),
            str(data.get('warranty', '-')),
            str(data.get('count', '1')),
            str(data.get('product', 'Item'))
        ]
        
        if is_ar:
            for i in range(4): pdf.cell(w[i], 14, text=t(vals[i], ""), border=1, align='C')
        else:
            for i in reversed(range(4)): pdf.cell(w[i], 14, text=vals[i], border=1, align='C')
        pdf.ln(25)

        # Total
        pdf.set_font_size(18); pdf.set_text_color(0, 128, 0)
        pdf.cell(0, 12, text=t(f"الإجمالي: {vals[0]}", f"Total: {vals[0]}"), ln=True, align='C')
        
        pdf.output(output_filename)
        return True
    except Exception as e:
        print(f"PDF Error: {e}")
        return False# --- الوظائف الخلفية ---
async def bio_loop():
    print("✅ Bio Service Started")
    while True:
        if settings["auto_bio"] and user_client:
            try:
                now = datetime.datetime.now().strftime("%I:%M %p")
                bt = settings["bio_template"].replace("%TIME%", now)
                await user_client(UpdateProfileRequest(about=bt))
            except: pass
        await asyncio.sleep(60)

async def get_log_channel_entity():
    if not settings["log_channel"]: return None
    try: return await user_client.get_entity(settings["log_channel"])
    except: return None

# --- المعالجات (Handlers) ---
async def message_edited_handler(event):
    if not settings["spy_mode"] or not event.is_private: return
    try:
        log = await get_log_channel_entity()
        if log:
            s = await event.get_sender()
            n = getattr(s, 'first_name', 'Unknown')
            await user_client.send_message(log, f"✏️ **تعديل (خاص)**\n👤: {n}\n📝: `{event.raw_text}`")
    except: pass

async def message_deleted_handler(event):
    if not settings["spy_mode"]: return
    try:
        log = await get_log_channel_entity()
        if log:
            for m in event.deleted_ids:
                if m in message_cache:
                    d = message_cache[m]
                    if d.get('is_private'):
                        await user_client.send_message(log, f"🗑️ **حذف (خاص)**\n👤: {d['sender']}\n📝: `{d['text']}`")
    except: pass

async def global_reply_handler(event):
    # Ghost Logic (Read in background)
    if settings["ghost_mode"] and event.is_private and not event.out:
        try:
            log = await get_log_channel_entity()
            if log:
                await event.forward_to(log)
                s = await event.get_sender()
                n = getattr(s, 'first_name', 'Unknown')
                await user_client.send_message(log, f"👻 **شبح: رسالة من {n}**")
        except: pass

    # Auto Reply Logic
    if not settings["running"] or not settings["keywords"] or not settings["replies"]: return
    if event.out or not is_working_hour(): return

    text = event.raw_text.strip()
    if any(k in text for k in settings["keywords"]):
        sid = event.sender_id
        if sid in user_cooldowns:
            if time.time() - user_cooldowns[sid] < 600: return # 10 mins cooldown
        
        try:
            async with user_client.action(event.chat_id, 'typing'):
                await asyncio.sleep(settings["typing_delay"])
                await event.reply(random.choice(settings["replies"]))
            user_cooldowns[sid] = time.time()
        except: pass

async def cache_messages_handler(event):
    try:
        if event.is_private:
            s = await event.get_sender()
            n = getattr(s, 'first_name', 'Unknown')
            message_cache[event.id] = {"text": event.raw_text, "sender": n, "is_private": True}
            if len(message_cache) > 500:
                keys = list(message_cache.keys())
                for k in keys[:100]: del message_cache[k]
    except: pass

# --- تشغيل البوت ---
async def start_user_bot():
    global user_client, bio_task
    if not settings["session"]: return
    try:
        if user_client: await user_client.disconnect()
        user_client = TelegramClient(StringSession(settings["session"]), API_ID, API_HASH)
        await user_client.connect()
        
        user_client.add_event_handler(global_reply_handler, events.NewMessage())
        user_client.add_event_handler(message_edited_handler, events.MessageEdited())
        user_client.add_event_handler(message_deleted_handler, events.MessageDeleted())
        user_client.add_event_handler(cache_messages_handler, events.NewMessage())
        
        if bio_task: bio_task.cancel()
        bio_task = asyncio.create_task(bio_loop())
        print("✅ Userbot Active")
    except Exception as e:
        print(f"❌ Start Error: {e}")

# --- واجهات المستخدم ---
async def show_invoice_menu(event):
    btns = [
        [Button.inline("➕ فاتورة جديدة", b"start_fast_invoice"), Button.inline("⚙️ إعداد المتجر", b"store_settings")],
        [Button.inline("🔙 رجوع", b"refresh_panel")]
    ]
    try: await event.edit("🧾 **نظام الفواتير**", buttons=btns)
    except: await event.respond("🧾 **نظام الفواتير**", buttons=btns)

async def show_control_panel(event, edit=False):
    st = "🟢 يعمل" if settings["running"] else "🔴 متوقف"
    msg = f"🎛️ **لوحة التحكم**\n📡 الحالة: {st}\n👮 تجسس: {'✅' if settings['spy_mode'] else '❌'}\n👻 شبح: {'✅' if settings['ghost_mode'] else '❌'}"
    
    btns = [
        [Button.inline("🛠️ الأدوات", b"tools_menu"), Button.inline("🧾 الفواتير", b"invoice_menu")],
        [Button.inline("💬 الردود", b"manage_kw_menu"), Button.inline("🕵️ التجسس", b"toggle_spy")],
        [Button.inline("👻 الشبح", b"toggle_ghost"), Button.inline("📝 البايو", b"toggle_bio")],
        [Button.inline(f"تشغيل/إيقاف {st}", b"toggle_run"), Button.inline("📢 السجل", b"log_settings")],
        [Button.inline("🔄 تحديث", b"refresh_panel"), Button.inline("❌ خروج", b"logout")]
    ]
    if edit: 
        try: await event.edit(msg, buttons=btns)
        except: await event.respond(msg, buttons=btns)
    else: await event.respond(msg, buttons=btns)

# --- القوائم الفرعية ---
async def show_tools_menu(event):
    btns = [[Button.inline("📥 تحميل", b"tool_dl"), Button.inline("🌐 IP", b"tool_ip")], [Button.inline("🔙", b"refresh_panel")]]
    await event.edit("🛠️ **الأدوات:**", buttons=btns)

async def show_keywords_main_menu(event):
    k=len(settings["keywords"]); r=len(settings["replies"])
    btns = [
        [Button.inline(f"الكلمات ({k})", b"list_kw"), Button.inline(f"الردود ({r})", b"list_rep")],
        [Button.inline("➕ كلمة", b"add_word"), Button.inline("➕ رد", b"add_reply")],
        [Button.inline("🔙", b"refresh_panel")]
    ]
    await event.edit("🔠 **إدارة الردود:**", buttons=btns)

# --- الكالباك ---
@bot.on(events.CallbackQuery)
async def callback_handler(event):
    try:
        data = event.data.decode(); sid = event.sender_id
        
        if data == "refresh_panel": await show_control_panel(event, edit=True)
        elif data == "invoice_menu": await show_invoice_menu(event)
        elif data == "tools_menu": await show_tools_menu(event)
        elif data == "manage_kw_menu": await show_keywords_main_menu(event)
        
        elif data == "toggle_run": settings["running"]=not settings["running"]; save_data(); await show_control_panel(event, edit=True)
        elif data == "toggle_spy": settings["spy_mode"]=not settings["spy_mode"]; save_data(); await show_control_panel(event, edit=True)
        elif data == "toggle_ghost": settings["ghost_mode"]=not settings["ghost_mode"]; save_data(); await show_control_panel(event, edit=True)
        elif data == "toggle_bio": settings["auto_bio"]=not settings["auto_bio"]; save_data(); await show_control_panel(event, edit=True)
        
        elif data == "add_word": user_state[sid]="add_word"; await event.respond("أرسل الكلمة:"); await event.delete()
        elif data == "add_reply": user_state[sid]="add_reply"; await event.respond("أرسل الرد:"); await event.delete()
        
        elif data == "store_settings": user_state[sid]="set_store"; await event.respond("اسم المتجر:"); await event.delete()
        elif data == "start_fast_invoice": invoice_drafts[sid]={}; user_state[sid]="inv_c"; await event.respond("العميل:"); await event.delete()
        
        elif data == "login": user_state[sid]="login"; await event.respond("الكود:"); await event.delete()
        elif data == "logout": settings["session"]=None; save_data(); await event.edit("✅"); await show_login_button(event)
        
        elif data == "log_settings":
            try: c=await user_client(CreateChannelRequest("Logs", "Logs", megagroup=False)); settings["log_channel"]=int(f"-100{c.chats[0].id}"); save_data(); await event.answer("تم")
            except: await event.answer("Error")

    except: traceback.print_exc()

@bot.on(events.NewMessage)
async def input_handler(event):
    if event.sender_id == (await bot.get_me()).id: return
    sid = event.sender_id; st = user_state.get(sid); txt = event.text.strip()

    if st == "login":
        try:
            c = TelegramClient(StringSession(txt), API_ID, API_HASH); await c.connect()
            if await c.is_user_authorized(): settings["session"]=txt; save_data(); await c.disconnect(); await event.reply("✅"); await start_user_bot(); await show_control_panel(event)
            else: await event.reply("❌")
        except: await event.reply("❌")
        user_state[sid] = None

    elif st == "add_word": settings["keywords"].append(txt); save_data(); await event.reply("✅"); user_state[sid]=None
    elif st == "add_reply": settings["replies"].append(txt); save_data(); await event.reply("✅"); user_state[sid]=None
    
    elif st == "set_store": settings["store_name"]=txt; save_data(); await event.reply("✅"); user_state[sid]=None
    elif st == "inv_c": invoice_drafts[sid]['client_name']=txt; user_state[sid]="inv_p"; await event.reply("المنتج:")
    elif st == "inv_p": invoice_drafts[sid]['product']=txt; user_state[sid]="inv_q"; await event.reply("العدد:")
    elif st == "inv_q": invoice_drafts[sid]['count']=txt; user_state[sid]="inv_pr"; await event.reply("السعر:")
    elif st == "inv_pr": invoice_drafts[sid]['price']=txt; user_state[sid]="inv_w"; await event.reply("الضمان:")
    elif st == "inv_w":
        invoice_drafts[sid]['warranty']=txt; code=''.join([str(random.randint(0,9)) for _ in range(16)])
        settings["invoices_archive"][code]=invoice_drafts[sid]; save_data()
        fn=f"Inv_{code}.pdf"
        if create_arabic_invoice(invoice_drafts[sid], code, fn): await event.client.send_file(event.chat_id, fn, caption=f"`{code}`"); os.remove(fn)
        user_state[sid]=None; await show_invoice_menu(event)

# --- Server & Start ---
async def web_page(request): return web.Response(text="Bot Alive")
async def server():
    app=web.Application(); app.add_routes([web.get('/', web_page)])
    runner=web.AppRunner(app); await runner.setup()
    site=web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT",8080))); await site.start()

async def show_login_button(event): await event.respond("👋", buttons=[[Button.inline("➕ Login", b"login")]])

@bot.on(events.NewMessage(pattern='/start'))
async def on_start(event):
    load_data()
    if settings["session"]: await start_user_bot(); await show_control_panel(event)
    else: await show_login_button(event)

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.create_task(server())
    bot.run_until_disconnected()
