# ==============================================================================
# 🤖 TELEGRAM USERBOT - ULTIMATE SINGLE USER (FULL FEATURES)
# ==============================================================================
# - ميزة الرد التلقائي (الكلمات والردود) ✅
# - سيرفر رندر (للبقاء 24 ساعة) ✅
# - قاعدة بيانات مونجو (لحفظ كل شيء) ✅
# - نظام الفواتير (عربي/إنجليزي) ✅
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

# مكتبات السيرفر والويب
from aiohttp import web

# مكتبات قاعدة البيانات
import pymongo
import certifi

# مكتبات PDF
from fpdf import FPDF
import arabic_reshaper
from bidi.algorithm import get_display

# مكتبات تيليجرام
from telethon import TelegramClient, events, Button, functions, types
from telethon.sessions import StringSession
from telethon.tl.functions.channels import CreateChannelRequest, EditBannedRequest, InviteToChannelRequest, GetParticipantsRequest, JoinChannelRequest
from telethon.tl.functions.messages import SendReactionRequest, SetTypingRequest, ReadHistoryRequest, DeleteHistoryRequest
from telethon.tl.functions.account import UpdateProfileRequest, UpdateStatusRequest
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.types import SendMessageCancelAction, ChannelParticipantsAdmins
from telethon.errors import *

# إعدادات النظام
warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO)

# متغيرات البيئة
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

print("⏳ Connecting to Database...")
try:
    if MONGO_URI:
        mongo_client = pymongo.MongoClient(MONGO_URI, tlsCAFile=certifi.where())
        db = mongo_client["telegram_userbot_db"]
        settings_collection = db["settings"]
        print("✅ Database Connected!")
    else:
        print("⚠️ No MongoDB URI found.")
except Exception as e:
    print(f"❌ DB Error: {e}")

# --- تحميل الخط ---
def download_font():
    if not os.path.exists(FONT_FILE) or os.path.getsize(FONT_FILE) < 1000:
        try:
            r = requests.get(FONT_URL)
            with open(FONT_FILE, 'wb') as f: f.write(r.content)
        except: pass
download_font()

# --- تشغيل العميل ---
bot = None
try:
    bot = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)
except:
    bot = TelegramClient('bot_session', API_ID, API_HASH)

user_client = None
bio_task = None

# --- الإعدادات الافتراضية (مع الردود والكلمات) ---
default_settings = {
    "_id": "bot_config",
    "session": None,
    "running": False, # حالة التشغيل
    "log_channel": None,
    # التجسس والشبح
    "spy_mode": False,
    "ghost_mode": False,
    "anti_typing": False,
    "fake_offline": False,
    # الرد التلقائي (الميزة المطلوبة)
    "keywords": [], # قائمة الكلمات المفتاحية
    "replies": [],  # قائمة الردود العشوائية
    "typing_delay": 2,
    "work_mode": False,
    "work_start": 0, "work_end": 23,
    # المتجر
    "store_name": "My Store",
    "invoices_archive": {},
    # أدوات أخرى
    "auto_bio": False,
    "bio_template": "Time: %TIME% | Online",
    "stalk_list": [],
    "typing_watch_list": [],
    "anti_link_group": False,
    "auto_save_destruct": True
}

settings = default_settings.copy()

# متغيرات التشغيل
user_cooldowns = {} 
user_state = {} 
invoice_drafts = {} 
temp_data = {} 
message_cache = {} 

# --- دوال الحفظ والتحميل ---
def save_data():
    if settings_collection is None: return
    try:
        settings_collection.replace_one({"_id": "bot_config"}, settings, upsert=True)
    except: pass

def load_data():
    global settings
    if settings_collection is None: return
    try:
        data = settings_collection.find_one({"_id": "bot_config"})
        if data:
            for k in data: settings[k] = data[k]
            print("☁️ Data Loaded.")
        else:
            save_data()
        
        # التأكد من وجود القوائم
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

def create_invoice_pdf(data, code, filename):
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
        pdf.set_fill_color(44, 62, 80); pdf.rect(0, 0, 210, 40, 'F')
        pdf.set_text_color(255, 255, 255); pdf.set_font_size(24); pdf.set_xy(10, 10)
        pdf.cell(0, 10, text=t("INVOICE", "INVOICE"), border=0, align='C')
        pdf.set_font_size(10); pdf.set_xy(10, 22)
        pdf.cell(0, 10, text=f"#{code}", align='C')
        if os.path.exists(LOGO_FILE): pdf.image(LOGO_FILE, x=170, y=5, w=30)
        pdf.ln(30)

        # Info
        pdf.set_text_color(0, 0, 0); pdf.set_font_size(12)
        align = 'R' if is_ar else 'L'
        pdf.set_fill_color(236, 240, 241)
        pdf.cell(0, 10, text=t("التفاصيل", "Details"), ln=True, align=align, fill=True)
        pdf.cell(190, 7, text=t(f"Store: {settings['store_name']}", f"Store: {settings['store_name']}"), ln=True, align=align)
        pdf.cell(190, 7, text=t(f"Client: {data.get('client_name')}", f"Client: {data.get('client_name')}"), ln=True, align=align)
        pdf.ln(10)

        # Table
        pdf.set_fill_color(44, 62, 80); pdf.set_text_color(255, 255, 255); pdf.set_draw_color(0, 0, 0)
        cols = ["Product", "Qty", "Price", "Warranty"]
        w = [80, 20, 40, 50]
        for i in range(4): pdf.cell(w[i], 10, text=cols[i], border=1, align='C', fill=True)
        pdf.ln()
        
        pdf.set_text_color(0, 0, 0)
        vals = [str(data.get('product')), str(data.get('count')), str(data.get('price')), str(data.get('warranty'))]
        for i in range(4): pdf.cell(w[i], 10, text=fix_text(vals[i]) if is_ar else vals[i], border=1, align='C')
        pdf.ln(20)
        
        pdf.set_font_size(16); pdf.set_text_color(44, 62, 80)
        pdf.cell(0, 10, text=t(f"TOTAL: {vals[2]}", f"TOTAL: {vals[2]}"), ln=True, align='C')
        pdf.output(filename)
        return True
    except: return False# ------------------------------------------------------------------------------
# الوظائف الخلفية
# ------------------------------------------------------------------------------
async def bio_loop():
    print("✅ Bio Started")
    while True:
        if settings["auto_bio"] and user_client:
            try:
                now = datetime.datetime.now().strftime("%I:%M %p")
                await user_client(UpdateProfileRequest(about=settings["bio_template"].replace("%TIME%", now)))
            except: pass
        await asyncio.sleep(60)

async def get_log():
    if not settings["log_channel"] or not user_client: return None
    try: return await user_client.get_entity(settings["log_channel"])
    except: return None

# ------------------------------------------------------------------------------
# المعالجات (Handlers)
# ------------------------------------------------------------------------------
async def message_edited_handler(event):
    if not settings["spy_mode"] or not event.is_private: return
    try:
        log = await get_log()
        if log:
            s = await event.get_sender()
            n = getattr(s, 'first_name', 'Unknown')
            await user_client.send_message(log, f"✏️ **تعديل**\n👤: {n}\n📝: `{event.raw_text}`")
    except: pass

async def message_deleted_handler(event):
    if not settings["spy_mode"]: return
    try:
        log = await get_log()
        if log:
            for m in event.deleted_ids:
                if m in message_cache:
                    d = message_cache[m]
                    if d.get('is_private'):
                        await user_client.send_message(log, f"🗑️ **حذف**\n👤: {d['sender']}\n📝: `{d['text']}`")
    except: pass

# --- المعالج الرئيسي (شامل الرد التلقائي) ---
async def main_watcher_handler(event):
    try:
        # 1. التخزين (للتجسس)
        if event.is_private:
            sender = await event.get_sender()
            name = getattr(sender, 'first_name', 'Unknown')
            message_cache[event.id] = {"text": event.raw_text, "sender": name, "is_private": True}
            if len(message_cache) > 500: 
                keys = list(message_cache.keys())
                for k in keys[:100]: del message_cache[k]

        # 2. الشبح
        if settings["ghost_mode"] and not event.out and event.is_private:
            log = settings["log_channel"]
            if log:
                await event.forward_to(log)
                s_name = message_cache.get(event.id, {}).get('sender', 'Unknown')
                await user_client.send_message(log, f"👻 **شبح: رسالة من {s_name}**")

        # 3. مانع الكتابة
        if settings["anti_typing"] and event.out:
            try: await user_client(SetTypingRequest(event.chat_id, SendMessageCancelAction()))
            except: pass

        # 4. حفظ الموقوتة
        ttl = getattr(event.message, 'ttl_period', None)
        if settings["auto_save_destruct"] and ttl and ttl > 0 and not event.out:
            if event.media:
                p = await event.download_media()
                await user_client.send_file("me", p, caption=f"💣 **موقوتة** ({ttl}s)")
                if settings["log_channel"]: await user_client.send_file(settings["log_channel"], p, caption="💣")
                os.remove(p)

        # 5. الرد التلقائي (هنا الميزة المطلوبة)
        if settings["running"] and is_working_hour() and not event.out:
            incoming = event.raw_text.strip()
            # التحقق من الكلمات
            if any(k in incoming for k in settings["keywords"]):
                # التحقق من الكول داون (10 ثواني)
                last_time = user_cooldowns.get(event.sender_id, 0)
                if time.time() - last_time > 10:
                    async with user_client.action(event.chat_id, 'typing'):
                        await asyncio.sleep(settings["typing_delay"])
                        # اختيار رد عشوائي
                        if settings["replies"]:
                            reply_text = random.choice(settings["replies"])
                            await event.reply(reply_text)
                    
                    user_cooldowns[event.sender_id] = time.time()

        # 6. منع الروابط
        if settings["anti_link_group"] and (event.is_group or event.is_channel) and not event.out:
            if "http" in event.raw_text.lower():
                try: await event.delete()
                except: pass

    except Exception as e:
        print(f"Main Error: {e}")

@bot.on(events.UserUpdate)
async def user_update_handler(event):
    if not user_client: return
    try:
        if event.user_id in settings["stalk_list"] and event.online:
            await user_client.send_message("me", f"🚨 **المراقب {event.user_id} متصل!**")
        if event.user_id in settings["typing_watch_list"] and event.typing:
            await user_client.send_message("me", f"✍️ **المراقب {event.user_id} يكتب...**")
    except: pass

# ------------------------------------------------------------------------------
# واجهة التحكم (تتضمن أزرار الرد التلقائي)
# ------------------------------------------------------------------------------
async def show_main_panel(event, edit=False):
    s = "🟢" if settings["running"] else "🔴"
    text = (
        f"🎛️ **لوحة التحكم الرئيسية**\n"
        f"ــــــــــــــــــــــــــــــــــــــــ\n"
        f"📡 **الرد التلقائي:** {s}\n"
        f"👮 **التجسس:** {'✅' if settings['spy_mode'] else '❌'}\n"
        f"👻 **الشبح:** {'✅' if settings['ghost_mode'] else '❌'}\n"
        f"🧾 **المتجر:** {'✅' if settings['store_name'] else '⚠️'}\n"
        f"ــــــــــــــــــــــــــــــــــــــــ"
    )
    
    btns = [
        [
            Button.inline("💬 الردود والكلمات", b"menu_reply"), # زر الردود
            Button.inline("🕵️ التجسس", b"menu_spy")
        ],
        [
            Button.inline("👻 الشبح", b"menu_ghost"),
            Button.inline("🏪 المتجر", b"menu_store")
        ],
        [
            Button.inline("🛠️ الأدوات", b"menu_tools"),
            Button.inline("🛡️ المجموعات", b"menu_group")
        ],
        [
            Button.inline(f"تشغيل/إيقاف {s}", b"toggle_run"),
            Button.inline("📢 السجل", b"log_settings")
        ],
        [
            Button.inline("🔄 تحديث", b"refresh_panel"),
            Button.inline("❌ إغلاق", b"close_panel")
        ]
    ]
    if edit: await event.edit(text, buttons=btns)
    else: await event.respond(text, buttons=btns)

# قوائم فرعية
async def show_reply_menu(event):
    # إحصائيات
    k_count = len(settings["keywords"])
    r_count = len(settings["replies"])
    txt = f"💬 **قائمة الرد التلقائي**\n🔑 الكلمات المفتاحية: {k_count}\n🗣️ الردود المسجلة: {r_count}"
    btns = [
        [Button.inline("➕ أضف كلمة", b"add_kw"), Button.inline("➕ أضف رد", b"add_rep")],
        [Button.inline("🗑️ حذف الكل", b"clr_rep"), Button.inline("🔙 رجوع", b"refresh_panel")]
    ]
    await event.edit(txt, buttons=btns)

async def show_store_menu(event):
    btns = [[Button.inline("➕ فاتورة", b"add_inv"), Button.inline("⚙️ المتجر", b"set_store")], [Button.inline("🔙", b"refresh_panel")]]
    await event.edit("🏪 **المتجر:**", buttons=btns)

async def show_spy_menu(event):
    btns = [[Button.inline(f"تجسس {'✅' if settings['spy_mode'] else '❌'}", b"toggle_spy"), Button.inline(f"حفظ {'✅' if settings['auto_save_destruct'] else '❌'}", b"toggle_destruct")], [Button.inline("👁️ مراقب", b"tool_stalk"), Button.inline("✍️ كاشف", b"tool_watch_type")], [Button.inline("🔙", b"refresh_panel")]]
    await event.edit("🕵️ **التجسس:**", buttons=btns)

async def show_ghost_menu(event):
    btns = [[Button.inline(f"شبح {'✅' if settings['ghost_mode'] else '❌'}", b"toggle_ghost"), Button.inline(f"أوفلاين {'✅' if settings['fake_offline'] else '❌'}", b"toggle_fake_off")], [Button.inline(f"لا تكتب {'✅' if settings['anti_typing'] else '❌'}", b"toggle_anti_type"), Button.inline("❄️ تجميد", b"tool_freeze_last")], [Button.inline("🔙", b"refresh_panel")]]
    await event.edit("👻 **الشبح:**", buttons=btns)

async def show_tools_menu(event):
    btns = [[Button.inline("📦 Zip", b"tool_zip"), Button.inline("📄 PDF", b"tool_pdf")], [Button.inline("📥 رابط", b"tool_download"), Button.inline("🌐 IP", b"tool_ip")], [Button.inline("🔙", b"refresh_panel")]]
    await event.edit("🛠️ **الأدوات:**", buttons=btns)

async def show_group_menu(event):
    btns = [[Button.inline("🧹 تنظيف", b"g_clean"), Button.inline("🔁 حذف", b"g_purge")], [Button.inline("👥 استنساخ", b"g_clone"), Button.inline("🔙", b"refresh_panel")]]
    await event.edit("🛡️ **المجموعات:**", buttons=btns)# ------------------------------------------------------------------------------
# معالج الأزرار (Callbacks)
# ------------------------------------------------------------------------------
@bot.on(events.CallbackQuery)
async def callback_handler(event):
    try:
        d = event.data.decode(); sid = event.sender_id
        
        if d == "refresh_panel": await show_main_panel(event, edit=True)
        elif d == "close_panel": await event.delete()
        elif d == "menu_reply": await show_reply_menu(event)
        elif data == "menu_spy": await show_spy_menu(event)
        elif data == "menu_ghost": await show_ghost_menu(event)
        elif data == "menu_store": await show_store_menu(event)
        elif data == "menu_tools": await show_tools_menu(event)
        elif data == "menu_group": await show_group_menu(event)
        
        # التبديل
        elif d == "toggle_run": settings["running"] = not settings["running"]; save_data(); await show_main_panel(event, edit=True)
        elif d == "toggle_spy": settings["spy_mode"] = not settings["spy_mode"]; save_data(); await show_spy_menu(event)
        elif d == "toggle_ghost": settings["ghost_mode"] = not settings["ghost_mode"]; save_data(); await show_ghost_menu(event)
        elif d == "toggle_fake_off": settings["fake_offline"] = not settings["fake_offline"]; save_data(); await show_ghost_menu(event)
        elif d == "toggle_anti_type": settings["anti_typing"] = not settings["anti_typing"]; save_data(); await show_ghost_menu(event)
        elif d == "toggle_destruct": settings["auto_save_destruct"] = not settings["auto_save_destruct"]; save_data(); await show_spy_menu(event)
        
        # أوامر الرد التلقائي (الجديدة)
        elif d == "add_kw":
            user_state[sid] = "add_keyword"
            await event.respond("🔑 **أرسل الكلمة المفتاحية لإضافتها:**")
            await event.delete()
        elif d == "add_rep":
            user_state[sid] = "add_reply"
            await event.respond("🗣️ **أرسل الرد لإضافته:**")
            await event.delete()
        elif d == "clr_rep":
            settings["keywords"] = []
            settings["replies"] = []
            save_data()
            await event.answer("🗑️ تم حذف جميع الردود!", alert=True)
            await show_reply_menu(event)

        # باقي الأوامر
        elif d == "add_inv": user_state[sid] = "inv_client"; await event.respond("👤 العميل:"); await event.delete()
        elif d == "set_store": user_state[sid] = "set_store"; await event.respond("🏪 اسم المتجر:"); await event.delete()
        elif d == "tool_stalk": user_state[sid] = "w_stalk"; await event.respond("👁️ المعرف:"); await event.delete()
        elif d == "tool_watch_type": user_state[sid] = "w_type"; await event.respond("✍️ المعرف:"); await event.delete()
        elif d == "g_clone": user_state[sid] = "w_clone"; await event.respond("👥 المصدر:"); await event.delete()
        
        elif d == "tool_freeze_last": 
            if user_client: await user_client(UpdateStatusRequest(offline=True)); await event.answer("❄️ تم")
        
        elif d == "login": user_state[sid] = "login"; await event.respond("📩 الكود:"); await event.delete()
        elif d == "logout": settings["session"] = None; save_data(); await event.edit("✅ خروج"); await show_login_button(event)
    except: traceback.print_exc()

# ------------------------------------------------------------------------------
# معالج النصوص (Input)
# ------------------------------------------------------------------------------
@bot.on(events.NewMessage)
async def input_handler(event):
    if event.sender_id == (await bot.get_me()).id: return
    sid = event.sender_id; state = user_state.get(sid); text = event.text.strip()

    # 1. تسجيل الدخول
    if state == "login":
        try:
            c = TelegramClient(StringSession(text), API_ID, API_HASH); await c.connect()
            if await c.is_user_authorized(): settings["session"] = text; save_data(); await c.disconnect(); await event.reply("✅ تم"); await start_user_bot(); await show_main_panel(event)
            else: await event.reply("❌ خطأ")
        except: await event.reply("❌ اتصال")
        user_state[sid] = None

    # 2. إدارة الردود (الجديد)
    elif state == "add_keyword":
        settings["keywords"].append(text)
        save_data()
        await event.reply(f"✅ تمت إضافة الكلمة: `{text}`")
        user_state[sid] = None
    
    elif state == "add_reply":
        settings["replies"].append(text)
        save_data()
        await event.reply(f"✅ تمت إضافة الرد: `{text}`")
        user_state[sid] = None

    # 3. المتجر
    elif state == "set_store": settings["store_name"] = text; save_data(); await event.reply("✅ تم"); user_state[sid] = None
    elif state == "inv_client": invoice_drafts[sid] = {'client_name': text}; user_state[sid] = "inv_prod"; await event.reply("🛍️ المنتج:")
    elif state == "inv_prod": invoice_drafts[sid]['product'] = text; user_state[sid] = "inv_count"; await event.reply("🔢 العدد:")
    elif state == "inv_count": invoice_drafts[sid]['count'] = text; user_state[sid] = "inv_price"; await event.reply("💰 السعر:")
    elif state == "inv_price": invoice_drafts[sid]['price'] = text; user_state[sid] = "inv_warr"; await event.reply("🛡️ الضمان:")
    elif state == "inv_warr":
        invoice_drafts[sid]['warranty'] = text
        code = str(random.randint(10000, 99999))
        fn = f"Inv_{code}.pdf"
        if create_invoice_pdf(invoice_drafts[sid], code, fn): await event.client.send_file(event.chat_id, fn); os.remove(fn)
        user_state[sid] = None

    # 4. النقل
    elif state == "w_clone":
        temp_data[sid] = {"src": text}; user_state[sid] = "w_clone_dest"; await event.reply("3️⃣ الوجهة:")
    elif state == "w_clone_dest":
        asyncio.create_task(add_members_task(user_client, temp_data[sid]["src"], text, await event.reply("🚀 بدء..."))); user_state[sid] = None

# دوال مساعدة
async def add_members_task(client, src, dest, msg):
    try:
        src_e = await client.get_entity(src); dest_e = await client.get_entity(dest)
        parts = await client.get_participants(src_e, aggressive=True)
        users = [u for u in parts if not u.bot]
        await msg.edit(f"✅ سحب {len(users)}")
        s = 0
        for u in users:
            try:
                await client(InviteToChannelRequest(dest_e, [u])); s += 1; await asyncio.sleep(5)
                if s % 5 == 0: await msg.edit(f"🔄 {s}")
            except: pass
        await msg.edit(f"🏁 تم: {s}")
    except: await msg.edit("❌")

async def clean_deleted_accounts(chat_id):
    if not user_client: return
    users = await user_client.get_participants(chat_id)
    c = 0
    for u in users:
        if u.deleted:
            try: await user_client(EditBannedRequest(chat_id, u.id, ChatBannedRights(until_date=None, view_messages=True))); c+=1
            except: pass
    await user_client.send_message(chat_id, f"🧹 {c}")

async def purge_my_msgs(chat_id):
    if not user_client: return
    me = await user_client.get_me(); msgs = [m.id async for m in user_client.iter_messages(chat_id, from_user=me, limit=100)]
    await user_client.delete_messages(chat_id, msgs)

# ------------------------------------------------------------------------------
# السيرفر والتشغيل
# ------------------------------------------------------------------------------
async def web_page(request): return web.Response(text="Bot Alive")
async def start_server():
    app = web.Application(); app.add_routes([web.get('/', web_page)])
    runner = web.AppRunner(app); await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 8080)))
    await site.start()
    print("✅ Server Started")

@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    load_data()
    if settings["session"]: await start_user_bot(); await show_main_panel(event)
    else: await show_login_button(event)

async def show_login_button(event): await event.respond("👋 مرحباً", buttons=[[Button.inline("➕ دخول", b"login")]])

async def start_user_bot():
    global user_client, bio_task
    if not settings["session"]: return
    try:
        if user_client: await user_client.disconnect()
        user_client = TelegramClient(StringSession(settings["session"]), API_ID, API_HASH); await user_client.connect()
        user_client.add_event_handler(main_watcher_handler, events.NewMessage())
        user_client.add_event_handler(message_edited_handler, events.MessageEdited())
        user_client.add_event_handler(message_deleted_handler, events.MessageDeleted())
        user_client.add_event_handler(user_update_handler, events.UserUpdate())
        if bio_task: bio_task.cancel()
        bio_task = asyncio.create_task(bio_loop())
        print("✅ Userbot Active")
    except: pass

if __name__ == '__main__':
    print("🚀 Starting...")
    loop = asyncio.get_event_loop()
    loop.create_task(start_server())
    bot.run_until_disconnected()
