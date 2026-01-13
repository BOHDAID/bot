# ==============================================================================
# 🤖 TELEGRAM USERBOT - ULTIMATE EXPANDED VERSION
# ==============================================================================
# - Render Web Server (Fixed)
# - MongoDB Cloud (Fixed Collection Check)
# - Full Arabic UI
# - Expanded Code Style (No Shortcuts)
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

# ------------------------------------------------------------------------------
# استيراد مكتبات السيرفر
# ------------------------------------------------------------------------------
from aiohttp import web

# ------------------------------------------------------------------------------
# استيراد مكتبات قاعدة البيانات
# ------------------------------------------------------------------------------
import pymongo
import certifi

# ------------------------------------------------------------------------------
# استيراد مكتبات PDF
# ------------------------------------------------------------------------------
from fpdf import FPDF
import arabic_reshaper
from bidi.algorithm import get_display

# ------------------------------------------------------------------------------
# استيراد مكتبات تيليجرام (كاملة)
# ------------------------------------------------------------------------------
from telethon import TelegramClient
from telethon import events
from telethon import Button
from telethon import functions
from telethon import types
from telethon.sessions import StringSession

# القنوات
from telethon.tl.functions.channels import CreateChannelRequest
from telethon.tl.functions.channels import EditBannedRequest
from telethon.tl.functions.channels import InviteToChannelRequest
from telethon.tl.functions.channels import GetParticipantsRequest
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.channels import JoinChannelRequest

# الرسائل
from telethon.tl.functions.messages import SendReactionRequest
from telethon.tl.functions.messages import GetHistoryRequest
from telethon.tl.functions.messages import SetTypingRequest
from telethon.tl.functions.messages import ReadHistoryRequest
from telethon.tl.functions.messages import DeleteHistoryRequest

# الحساب
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.tl.functions.account import UpdateStatusRequest

# المستخدمين
from telethon.tl.functions.users import GetFullUserRequest

# الأنواع
from telethon.tl.types import ReactionEmoji
from telethon.tl.types import UserStatusOnline
from telethon.tl.types import UserStatusOffline
from telethon.tl.types import UserStatusRecently
from telethon.tl.types import UserStatusLastWeek
from telethon.tl.types import UserStatusLastMonth
from telethon.tl.types import UserStatusEmpty
from telethon.tl.types import MessageMediaPhoto
from telethon.tl.types import MessageMediaDocument
from telethon.tl.types import ChatBannedRights
from telethon.tl.types import SendMessageCancelAction
from telethon.tl.types import InputPeerChannel
from telethon.tl.types import InputPeerUser
from telethon.tl.types import ChannelParticipantsAdmins

# الأخطاء
from telethon.errors import MessageNotModifiedError
from telethon.errors import FloodWaitError
from telethon.errors import UserPrivacyRestrictedError
from telethon.errors import UserBotError
from telethon.errors import UserNotMutualContactError
from telethon.errors import UserChannelsTooMuchError
from telethon.errors import UserKickedError
from telethon.errors import UserBannedInChannelError
from telethon.errors import PeerFloodError
from telethon.errors import ChatWriteForbiddenError
from telethon.errors import UserIdInvalidError
from telethon.errors import InputUserDeactivatedError
from telethon.errors import UserNotParticipantError
from telethon.errors import MessageIdInvalidError

# ------------------------------------------------------------------------------
# إعدادات النظام
# ------------------------------------------------------------------------------
warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Userbot")

# متغيرات البيئة (Render)
API_ID = int(os.environ.get("API_ID", 6))
API_HASH = os.environ.get("API_HASH", "eb06d4abfb49dc3eeb1aeb98ae0f581e")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
MONGO_URI = os.environ.get("MONGO_URI")

LOGO_FILE = "saved_store_logo.jpg"
FONT_FILE = "font.ttf"
FONT_URL = "https://github.com/google/fonts/raw/main/ofl/amiri/Amiri-Regular.ttf"

# ------------------------------------------------------------------------------
# الاتصال بقاعدة البيانات (تم الإصلاح)
# ------------------------------------------------------------------------------
mongo_client = None
db = None
settings_collection = None

print("⏳ جاري الاتصال بقاعدة البيانات السحابية...")

try:
    if MONGO_URI:
        mongo_client = pymongo.MongoClient(MONGO_URI, tlsCAFile=certifi.where())
        db = mongo_client["telegram_userbot_db"]
        settings_collection = db["settings"]
        print("✅ تم الاتصال بقاعدة البيانات بنجاح!")
    else:
        print("⚠️ تحذير: لا يوجد رابط قاعدة بيانات.")
except Exception as e:
    print(f"❌ فشل الاتصال بقاعدة البيانات: {e}")

# ------------------------------------------------------------------------------
# تحميل الخط العربي
# ------------------------------------------------------------------------------
def download_font_if_missing():
    is_missing = False
    
    if not os.path.exists(FONT_FILE):
        is_missing = True
    elif os.path.getsize(FONT_FILE) < 1000:
        is_missing = True
        try:
            os.remove(FONT_FILE)
        except:
            pass

    if is_missing:
        try:
            print("⏳ جاري تحميل الخط العربي...")
            r = requests.get(FONT_URL)
            with open(FONT_FILE, 'wb') as f:
                f.write(r.content)
            print("✅ تم تحميل الخط.")
        except Exception as e:
            print(f"❌ فشل تحميل الخط: {e}")

download_font_if_missing()

# ------------------------------------------------------------------------------
# تشغيل العميل
# ------------------------------------------------------------------------------
bot = None
try:
    if BOT_TOKEN:
        bot = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)
    else:
        bot = TelegramClient('bot_session', API_ID, API_HASH)
except Exception as e:
    print(f"❌ خطأ تشغيل البوت: {e}")
    bot = TelegramClient('bot_session', API_ID, API_HASH)

user_client = None 
bio_task = None

# ------------------------------------------------------------------------------
# الإعدادات الافتراضية
# ------------------------------------------------------------------------------
default_settings = {
    "_id": "bot_config",
    "session": None,
    "keywords": [],
    "replies": [],
    "running": False,
    "log_channel": None,
    "typing_delay": 2,
    "work_start": 0,
    "work_end": 23,
    "work_mode": False,
    "reaction_mode": False,
    "reaction_emoji": "❤️",
    "spy_mode": False,
    "ghost_mode": False,
    "auto_bio": False,
    "bio_template": "Time: %TIME% | Status: Online",
    "store_name": "My Store",
    "store_user": "@Store",
    "has_logo": False,
    "invoices_archive": {},
    "fake_offline": False,
    "anti_typing": False,
    "freeze_last_seen": False,
    "screenshot_detect": False,
    "anti_link_group": False,
    "auto_save_destruct": True,
    "stalk_list": [],
    "typing_watch_list": []
}

settings = default_settings.copy()

# متغيرات التشغيل
user_cooldowns = {} 
user_state = {} 
invoice_drafts = {} 
temp_data = {} 
message_cache = {} 
active_relay_config = {} 

# ------------------------------------------------------------------------------
# إدارة البيانات (تم إصلاح خطأ Collection)
# ------------------------------------------------------------------------------
def save_data():
    """حفظ البيانات"""
    # استخدام is None هو الحل الصحيح مع المكتبات الحديثة
    if settings_collection is None:
        return
    
    try:
        settings_collection.replace_one(
            {"_id": "bot_config"}, 
            settings, 
            upsert=True
        )
    except Exception as e:
        print(f"❌ خطأ الحفظ: {e}")

def load_data():
    """تحميل البيانات"""
    global settings
    
    if settings_collection is None:
        return

    try:
        data = settings_collection.find_one({"_id": "bot_config"})
        if data:
            for key, value in data.items():
                settings[key] = value
            print("☁️ تم تحميل البيانات من السحابة.")
        else:
            save_data()
        
        # التأكد من القوائم
        if "invoices_archive" not in settings: settings["invoices_archive"] = {}
        if "stalk_list" not in settings: settings["stalk_list"] = []
        if "typing_watch_list" not in settings: settings["typing_watch_list"] = []
            
    except Exception as e:
        print(f"❌ خطأ التحميل: {e}")

def is_working_hour():
    if not settings["work_mode"]:
        return True
    curr = datetime.datetime.now().hour
    start = settings["work_start"]
    end = settings["work_end"]
    if start < end:
        return start <= curr < end
    else:
        return start <= curr or curr < end

# ------------------------------------------------------------------------------
# نظام الفواتير الكامل
# ------------------------------------------------------------------------------
def fix_text(text):
    if text is None:
        return ""
    text_str = str(text)
    try:
        reshaped_text = arabic_reshaper.reshape(text_str)
        bidi_text = get_display(reshaped_text)
        return bidi_text
    except:
        return text_str

def create_invoice_pdf(data, code_16, filename):
    try:
        pdf = FPDF()
        pdf.add_page()
        
        is_ar = False
        try:
            if os.path.exists(FONT_FILE):
                pdf.add_font('Amiri', '', FONT_FILE, uni=True)
                is_ar = True
        except:
            pass
        
        font_name = 'Amiri' if is_ar else 'Helvetica'
        pdf.set_font(font_name, '', 12)

        def t(ar, en):
            if is_ar:
                return fix_text(str(ar))
            return str(en)

        # الرأس
        pdf.set_fill_color(44, 62, 80)
        pdf.rect(0, 0, 210, 40, 'F')
        pdf.set_text_color(255, 255, 255)
        pdf.set_font_size(24)
        pdf.set_xy(10, 10)
        
        title = "INVOICE / فاتورة" if is_ar else "INVOICE"
        pdf.cell(0, 10, text=t(title, "INVOICE"), border=0, align='C')
        
        pdf.set_font_size(10)
        pdf.set_xy(10, 22)
        pdf.cell(0, 10, text=f"Ref: #{code_16}", align='C')

        if os.path.exists(LOGO_FILE):
            pdf.image(LOGO_FILE, x=170, y=5, w=30)

        pdf.ln(30)

        # المعلومات
        pdf.set_text_color(0, 0, 0)
        pdf.set_font_size(12)
        align = 'R' if is_ar else 'L'
        
        pdf.set_fill_color(236, 240, 241)
        pdf.cell(0, 10, text=t("التفاصيل", "Details"), ln=True, align=align, fill=True)
        
        store_n = settings.get("store_name", "Store")
        client_n = data.get('client_name', 'Client')
        date_s = datetime.datetime.now().strftime("%Y-%m-%d")
        
        pdf.cell(190, 7, text=t(f"Store: {store_n}", f"Store: {store_n}"), ln=True, align=align)
        pdf.cell(190, 7, text=t(f"Client: {client_n}", f"Client: {client_n}"), ln=True, align=align)
        pdf.cell(190, 7, text=t(f"Date: {date_s}", f"Date: {date_s}"), ln=True, align=align)
        
        pdf.ln(10)

        # الجدول
        pdf.set_fill_color(44, 62, 80)
        pdf.set_text_color(255, 255, 255)
        pdf.set_draw_color(0, 0, 0)
        
        h_ar = ["المنتج", "العدد", "الضمان", "السعر"]
        h_en = ["Product", "Qty", "Warranty", "Price"]
        w = [80, 25, 45, 40]
        
        if is_ar:
            for i in reversed(range(4)):
                pdf.cell(w[i], 10, text=t(h_ar[i], ""), border=1, align='C', fill=True)
        else:
            for i in range(4):
                pdf.cell(w[i], 10, text=h_en[i], border=1, align='C', fill=True)
        pdf.ln()
        
        pdf.set_text_color(0, 0, 0)
        vp = str(data.get('product', '-'))
        vc = str(data.get('count', '1'))
        vw = str(data.get('warranty', '-'))
        vpr = str(data.get('price', '0'))
        
        if is_ar:
            pdf.cell(w[3], 10, text=t(vpr,""), border=1, align='C')
            pdf.cell(w[2], 10, text=t(vw,""), border=1, align='C')
            pdf.cell(w[1], 10, text=t(vc,""), border=1, align='C')
            pdf.cell(w[0], 10, text=t(vp,""), border=1, align='R')
        else:
            pdf.cell(w[0], 10, text=vp, border=1, align='L')
            pdf.cell(w[1], 10, text=vc, border=1, align='C')
            pdf.cell(w[2], 10, text=vw, border=1, align='C')
            pdf.cell(w[3], 10, text=vpr, border=1, align='C')
            
        pdf.ln(20)
        
        pdf.set_font_size(16)
        pdf.set_text_color(44, 62, 80)
        pdf.cell(0, 10, text=t(f"TOTAL: {vpr}", f"TOTAL: {vpr}"), ln=True, align='C')
        
        pdf.output(filename)
        return True
    except Exception as e:
        print(f"PDF Error: {e}")
        return False# ------------------------------------------------------------------------------
# الوظائف الخلفية
# ------------------------------------------------------------------------------
async def bio_loop():
    print("✅ بدء خدمة البايو")
    while True:
        if settings["auto_bio"]:
            if user_client:
                try:
                    now = datetime.datetime.now().strftime("%I:%M %p")
                    bio_txt = settings["bio_template"].replace("%TIME%", now)
                    await user_client(UpdateProfileRequest(about=bio_txt))
                except:
                    pass
        await asyncio.sleep(60)

async def get_log_channel():
    if not settings["log_channel"]:
        return None
    if not user_client:
        return None
    try:
        return await user_client.get_entity(settings["log_channel"])
    except:
        return None

# ------------------------------------------------------------------------------
# معالجات الأحداث
# ------------------------------------------------------------------------------
async def message_edited_handler(event):
    if not settings["spy_mode"]:
        return
    if not event.is_private:
        return 
    try:
        log = await get_log_channel()
        if not log:
            return
        sender = await event.get_sender()
        name = getattr(sender, 'first_name', 'Unknown')
        msg = f"✏️ **تعديل رسالة**\n👤: {name}\n📝: `{event.raw_text}`"
        await user_client.send_message(log, msg)
    except:
        pass

async def message_deleted_handler(event):
    if not settings["spy_mode"]:
        return
    try:
        log = await get_log_channel()
        if not log:
            return
        for m_id in event.deleted_ids:
            if m_id in message_cache:
                d = message_cache[m_id]
                if d.get('is_private'):
                    msg = f"🗑️ **حذف رسالة**\n👤: {d['sender']}\n📝: `{d['text']}`"
                    await user_client.send_message(log, msg)
    except:
        pass

async def main_watcher_handler(event):
    try:
        # التخزين
        if event.is_private:
            sender = await event.get_sender()
            name = getattr(sender, 'first_name', 'Unknown')
            message_cache[event.id] = {
                "text": event.raw_text,
                "sender": name,
                "is_private": True
            }
            if len(message_cache) > 2000:
                keys = list(message_cache.keys())
                for k in keys[:500]:
                    del message_cache[k]

        # الشبح
        if settings["ghost_mode"]:
            if not event.out:
                if event.is_private:
                    if settings["log_channel"]:
                        await event.forward_to(settings["log_channel"])
                        sn = message_cache.get(event.id, {}).get('sender', 'Unknown')
                        await user_client.send_message(settings["log_channel"], f"👻 **شبح: رسالة من {sn}**")

        # مانع الكتابة
        if settings["anti_typing"]:
            if event.out:
                try:
                    await user_client(SetTypingRequest(event.chat_id, SendMessageCancelAction()))
                except:
                    pass

        # التدمير الذاتي
        ttl = getattr(event.message, 'ttl_period', None)
        if settings["auto_save_destruct"]:
            if ttl and ttl > 0:
                if not event.out:
                    if event.media:
                        try:
                            p = await event.download_media()
                            c = f"💣 **موقوتة** ({ttl}s)"
                            await user_client.send_file("me", p, caption=c)
                            if settings["log_channel"]:
                                await user_client.send_file(settings["log_channel"], p, caption="💣")
                            os.remove(p)
                        except:
                            pass

        # الرد التلقائي
        if settings["running"]:
            if is_working_hour():
                if not event.out:
                    if any(k in event.raw_text for k in settings["keywords"]):
                        last = user_cooldowns.get(event.sender_id, 0)
                        if time.time() - last > 600:
                            async with user_client.action(event.chat_id, 'typing'):
                                await asyncio.sleep(settings["typing_delay"])
                                await event.reply(random.choice(settings["replies"]))
                            user_cooldowns[event.sender_id] = time.time()

        # منع الروابط
        if settings["anti_link_group"]:
            if event.is_group or event.is_channel:
                if not event.out:
                    if "http" in event.raw_text.lower():
                        try:
                            await event.delete()
                        except:
                            pass
    except:
        pass

@bot.on(events.UserUpdate)
async def user_update_handler(event):
    if not user_client:
        return
    try:
        if event.user_id in settings["stalk_list"]:
            if event.online:
                await user_client.send_message("me", f"🚨 **مراقب {event.user_id} متصل!**")
        if event.user_id in settings["typing_watch_list"]:
            if event.typing:
                await user_client.send_message("me", f"✍️ **مراقب {event.user_id} يكتب...**")
    except:
        pass

# ------------------------------------------------------------------------------
# واجهة التحكم
# ------------------------------------------------------------------------------
async def show_main_panel(event, edit=False):
    s = "🟢" if settings["running"] else "🔴"
    
    text = (
        f"🎛️ **لوحة التحكم السحابية**\n"
        f"ـــــــــــــــــــــــــــــــــــــــــــــــــ\n"
        f"📡 **الحالة:** {s}\n"
        f"👮 **تجسس:** {'✅' if settings['spy_mode'] else '❌'}\n"
        f"👻 **شبح:** {'✅' if settings['ghost_mode'] else '❌'}\n"
        f"🧾 **متجر:** {'✅' if settings['store_name'] else '⚠️'}\n"
        f"ـــــــــــــــــــــــــــــــــــــــــــــــــ"
    )
    
    btns = [
        [
            Button.inline("🕵️ التجسس", data=b"menu_spy"),
            Button.inline("👻 الشبح", data=b"menu_ghost")
        ],
        [
            Button.inline("🏪 المتجر", data=b"menu_store"),
            Button.inline("🛠️ الأدوات", data=b"menu_tools")
        ],
        [
            Button.inline("🎤 وسيط صوتي", data=b"menu_voice"),
            Button.inline("🛡️ مجموعات", data=b"menu_group")
        ],
        [
            Button.inline(f"تشغيل/إيقاف {s}", data=b"toggle_run"),
            Button.inline("📢 السجل", data=b"log_settings")
        ],
        [
            Button.inline("🔄 تحديث", data=b"refresh_panel"),
            Button.inline("❌ إغلاق", data=b"close_panel")
        ]
    ]
    
    if edit:
        try: await event.edit(text, buttons=btns)
        except: await event.respond(text, buttons=btns)
    else:
        await event.respond(text, buttons=btns)

# القوائم الفرعية
async def show_store_menu(event):
    btns = [
        [Button.inline("➕ فاتورة", b"start_fast_invoice"), Button.inline("🔎 بحث", b"search_invoice")],
        [Button.inline("⏰ تذكير", b"tool_payment_remind"), Button.inline("⚙️ إعدادات", b"store_settings")],
        [Button.inline("🔙 رجوع", b"refresh_panel")]
    ]
    await event.edit("🏪 **المتجر:**", buttons=btns)

async def show_spy_menu(event):
    btns = [
        [Button.inline(f"تجسس {'✅' if settings['spy_mode'] else '❌'}", b"toggle_spy"), Button.inline(f"حفظ الموقوت {'✅' if settings['auto_save_destruct'] else '❌'}", b"toggle_destruct")],
        [Button.inline("👁️ راصد", b"tool_stalk"), Button.inline("✍️ كاشف", b"tool_watch_type")],
        [Button.inline("🔙 رجوع", b"refresh_panel")]
    ]
    await event.edit("🕵️ **التجسس:**", buttons=btns)

async def show_ghost_menu(event):
    btns = [
        [Button.inline(f"شبح {'✅' if settings['ghost_mode'] else '❌'}", b"toggle_ghost"), Button.inline(f"أوفلاين {'✅' if settings['fake_offline'] else '❌'}", b"toggle_fake_off")],
        [Button.inline(f"لا تكتب {'✅' if settings['anti_typing'] else '❌'}", b"toggle_anti_type"), Button.inline("❄️ تجميد", b"tool_freeze_last")],
        [Button.inline("🔙 رجوع", b"refresh_panel")]
    ]
    await event.edit("👻 **الشبح:**", buttons=btns)

async def show_tools_menu(event):
    btns = [
        [Button.inline("📦 Zip", b"tool_zip"), Button.inline("📄 PDF", b"tool_pdf")],
        [Button.inline("📥 تحميل", b"tool_download"), Button.inline("🌐 IP", b"tool_ip")],
        [Button.inline("📶 Ping", b"tool_ping"), Button.inline("🔗 اختصار", b"tool_short")],
        [Button.inline("📟 تيرمينال", b"tool_shell"), Button.inline("🔙 رجوع", b"refresh_panel")]
    ]
    await event.edit("🛠️ **الأدوات:**", buttons=btns)

async def show_voice_menu(event):
    btns = [
        [Button.inline("🔇 بدون", b"voice_mode_none")],
        [Button.inline("🚗 سيارة", b"voice_mode_car"), Button.inline("🌧️ مطر", b"voice_mode_rain")],
        [Button.inline("🔙 رجوع", b"refresh_panel")]
    ]
    await event.edit("🎤 **الوسيط:**", buttons=btns)

async def show_group_menu(event):
    btns = [
        [Button.inline("🧹 تنظيف", b"group_mass_clean"), Button.inline("🔁 حذف رسائلي", b"group_purge_me")],
        [Button.inline("👥 استنساخ", b"group_clone"), Button.inline("👮 مشرفين", b"group_admins")],
        [Button.inline(f"منع روابط {'✅' if settings['anti_link_group'] else '❌'}", b"toggle_anti_link"), Button.inline("🔙 رجوع", b"refresh_panel")]
    ]
    await event.edit("🛡️ **المجموعات:**", buttons=btns)# ------------------------------------------------------------------------------
# معالج الأزرار (Callbacks)
# ------------------------------------------------------------------------------
@bot.on(events.CallbackQuery)
async def callback_handler(event):
    try:
        data = event.data.decode()
        sid = event.sender_id
        
        # تنقل
        if data == "refresh_panel": await show_main_panel(event, edit=True)
        elif data == "close_panel": await event.delete()
        elif data == "menu_spy": await show_spy_menu(event)
        elif data == "menu_ghost": await show_ghost_menu(event)
        elif data == "menu_store": await show_store_menu(event)
        elif data == "menu_tools": await show_tools_menu(event)
        elif data == "menu_voice": await show_voice_menu(event)
        elif data == "menu_group": await show_group_menu(event)
        
        # تبديل
        elif data == "toggle_run": settings["running"] = not settings["running"]; save_data(); await show_main_panel(event, edit=True)
        elif data == "toggle_spy": settings["spy_mode"] = not settings["spy_mode"]; save_data(); await show_spy_menu(event)
        elif data == "toggle_ghost": settings["ghost_mode"] = not settings["ghost_mode"]; save_data(); await show_ghost_menu(event)
        elif data == "toggle_fake_off": settings["fake_offline"] = not settings["fake_offline"]; save_data(); await show_ghost_menu(event)
        elif data == "toggle_anti_type": settings["anti_typing"] = not settings["anti_typing"]; save_data(); await show_ghost_menu(event)
        elif data == "toggle_destruct": settings["auto_save_destruct"] = not settings["auto_save_destruct"]; save_data(); await show_spy_menu(event)
        elif data == "toggle_anti_link": settings["anti_link_group"] = not settings["anti_link_group"]; save_data(); await show_group_menu(event)

        # أوامر
        elif data == "tool_stalk": user_state[sid] = "wait_stalk_id"; await event.respond("👁️ أرسل المعرف:")
        elif data == "tool_watch_type": user_state[sid] = "wait_type_id"; await event.respond("✍️ أرسل المعرف:")
        elif data == "tool_freeze_last": 
            if user_client: await user_client(UpdateStatusRequest(offline=True)); await event.answer("❄️ تم التجميد")
        elif data == "store_settings": user_state[sid] = "set_store_name"; await event.respond("🏪 اسم المتجر:")
        elif data == "start_fast_invoice": invoice_drafts[sid] = {}; user_state[sid] = "inv_client"; await event.respond("👤 العميل:")
        elif data == "search_invoice": user_state[sid] = "wait_search_inv"; await event.respond("🔎 الكود:")
        elif data == "tool_payment_remind": user_state[sid] = "wait_remind_user"; await event.respond("⏰ العميل:")
        
        elif data == "tool_ping": s=time.time(); await user_client.send_message("me", "Pong"); await event.answer(f"⚡ {round((time.time()-s)*1000)}ms", alert=True)
        elif data == "tool_ip": user_state[sid] = "wait_ip"; await event.respond("🌐 IP:")
        elif data == "tool_short": user_state[sid] = "wait_short_link"; await event.respond("🔗 الرابط:")
        elif data == "tool_download": user_state[sid] = "wait_dl_link"; await event.respond("📥 الرابط:")
        elif data == "tool_shell": user_state[sid] = "wait_shell"; await event.respond("📟 الأمر:")
        elif data == "tool_zip": user_state[sid] = "wait_zip_files"; temp_data[sid] = []; await event.respond("📦 أرسل ملفات ثم 'تم':")
        elif data == "tool_pdf": user_state[sid] = "wait_pdf_imgs"; temp_data[sid] = []; await event.respond("📄 أرسل صور ثم 'تم':")
        
        elif data.startswith("voice_mode_"):
            mode = data.split("_")[2]; user_state[sid] = "voice_wait_user"; temp_data[sid] = {"noise": mode}
            await event.respond(f"🎤 {mode}: معرف الضحية:")
        
        elif data == "group_mass_clean": await event.respond("⏳ تنظيف..."); asyncio.create_task(clean_deleted_accounts(event.chat_id))
        elif data == "group_purge_me": await event.respond("⏳ حذف..."); asyncio.create_task(purge_my_msgs(event.chat_id))
        elif data == "group_clone": user_state[sid] = "wait_clone_src"; await event.respond("👥 المصدر:")
        elif data == "group_admins": await list_admins(event)
        
        elif data == "log_settings": await event.respond(f"السجل: {settings.get('log_channel')}", buttons=[[Button.inline("إنشاء", b"set_log_auto")]])
        elif data == "set_log_auto": 
            try: ch = await user_client(CreateChannelRequest("Userbot Logs", "Logs", megagroup=False)); settings["log_channel"] = int(f"-100{ch.chats[0].id}"); save_data(); await event.answer("✅ تم")
            except: await event.answer("❌ خطأ", alert=True)
        elif data == "login": user_state[sid] = "waiting_session"; await event.respond("📩 الكود:")
        elif data == "logout": settings["session"] = None; save_data(); await event.edit("✅ تم الخروج"); await show_login_button(event)
        
        if data != "close_panel" and not data.startswith("toggle") and "menu" not in data: await event.delete()
    except: traceback.print_exc()

# ------------------------------------------------------------------------------
# معالج النصوص (Input Handler) - تم إصلاح Syntax Error هنا
# ------------------------------------------------------------------------------
@bot.on(events.NewMessage)
async def input_handler(event):
    if event.sender_id == (await bot.get_me()).id: return
    sid = event.sender_id; state = user_state.get(sid); text = event.text.strip()

    if state == "waiting_session":
        try:
            c = TelegramClient(StringSession(text), API_ID, API_HASH); await c.connect()
            if await c.is_user_authorized(): settings["session"] = text; save_data(); await c.disconnect(); await event.reply("✅ تم"); await start_user_bot(); await show_main_panel(event)
            else: await event.reply("❌ خطأ")
        except: await event.reply("❌ اتصال")
        user_state[sid] = None

    elif state == "set_store_name": settings["store_name"] = text; save_data(); await event.reply("✅ تم"); user_state[sid] = None
    elif state == "inv_client": invoice_drafts[sid]['client_name'] = text; user_state[sid] = "inv_prod"; await event.reply("🛍️ المنتج:")
    elif state == "inv_prod": invoice_drafts[sid]['product'] = text; user_state[sid] = "inv_count"; await event.reply("🔢 العدد:")
    elif state == "inv_count": invoice_drafts[sid]['count'] = text; user_state[sid] = "inv_price"; await event.reply("💰 السعر:")
    elif state == "inv_price": invoice_drafts[sid]['price'] = text; user_state[sid] = "inv_warranty"; await event.reply("🛡️ الضمان:")
    elif state == "inv_warranty":
        invoice_drafts[sid]['warranty'] = text
        code = ''.join([str(random.randint(0,9)) for _ in range(16)])
        settings["invoices_archive"][code] = invoice_drafts[sid]; save_data()
        fn = f"Invoice_{code}.pdf"
        if create_invoice_pdf(invoice_drafts[sid], code, fn): await event.client.send_file(event.chat_id, fn, caption=f"🧾 **تم**\n🔐 `{code}`"); os.remove(fn)
        else: await event.reply("❌ خطأ")
        user_state[sid] = None; await show_store_menu(event)

    elif state == "wait_search_inv":
        d = settings["invoices_archive"].get(text)
        if d:
            fn = f"Copy_{text}.pdf"
            if create_invoice_pdf(d, text, fn): await event.client.send_file(event.chat_id, fn); os.remove(fn)
            else: await event.reply("❌")
        else: await event.reply("❌")
        user_state[sid] = None

    elif state == "wait_remind_user":
        try: await user_client.send_message(text, "👋 **تذكير:** يرجى الدفع."); await event.reply("✅")
        except: await event.reply("❌")
        user_state[sid] = None

    elif state == "voice_wait_user":
        try: ent = await user_client.get_entity(text); temp_data[sid]['target'] = ent.id; user_state[sid] = "voice_wait_record"; await event.reply("2️⃣ أرسل الفويس:")
        except: await event.reply("❌")
    
    # 🔴 التصحيح هنا: فصل الأوامر
    elif state == "voice_wait_record":
        if event.voice or event.audio:
            tgt = temp_data[sid]['target']
            
            # تم الفصل لسطرين منفصلين لمنع SyntaxError
            async with user_client.action(tgt, 'record-audio'):
                await asyncio.sleep(3)
                
            p = await event.download_media()
            await user_client.send_file(tgt, p, voice_note=True)
            os.remove(p)
            await event.reply("✅ تم")
            user_state[sid] = None
        else:
            await event.reply("⚠️ صوت فقط")

    elif state == "wait_stalk_id":
        try: ent = await user_client.get_input_entity(text); settings["stalk_list"].append(ent.user_id); save_data(); await event.reply("✅")
        except: await event.reply("❌")
        user_state[sid] = None
    elif state == "wait_type_id":
        try: ent = await user_client.get_input_entity(text); settings["typing_watch_list"].append(ent.user_id); await event.reply("✅")
        except: await event.reply("❌")
        user_state[sid] = None

    elif state == "wait_ip":
        try: r = requests.get(f"http://ip-api.com/json/{text}").json(); await event.reply(f"🌍 {r.get('country')}")
        except: await event.reply("❌")
        user_state[sid] = None
    elif state == "wait_short_link":
        try: await event.reply(requests.get(f"https://tinyurl.com/api-create.php?url={text}").text)
        except: await event.reply("❌")
        user_state[sid] = None
    elif state == "wait_shell":
        try: await event.reply(f"`{os.popen(text).read()[:4000]}`")
        except: await event.reply("❌")
        user_state[sid] = None
    elif state == "wait_zip_files":
        if text == "تم":
            if temp_data.get(sid):
                zname = "archive.zip"
                with zipfile.ZipFile(zname, 'w') as zf:
                    for f in temp_data[sid]: zf.write(f)
                await user_client.send_file("me", zname); [os.remove(f) for f in temp_data[sid]]; os.remove(zname); await event.reply("✅")
            user_state[sid] = None
        elif event.media:
            p = await event.download_media(); 
            if sid not in temp_data: temp_data[sid] = []
            temp_data[sid].append(p); await event.reply("📥")

    elif state == "wait_clone_src":
        if not user_client: await event.reply("⚠️"); return
        msg = await event.reply("⏳...")
        try:
            if "t.me" in text: 
                try: await user_client(functions.channels.JoinChannelRequest(text))
                except: pass
            src = await user_client.get_entity(text); parts = await user_client.get_participants(src, aggressive=True)
            valid = [u for u in parts if not u.bot and not u.deleted]
            if not valid: await msg.edit("❌ 0"); user_state[sid] = None; return
            temp_data[sid] = {'scraped': valid}; await msg.edit(f"✅ {len(valid)}.\n2️⃣ العدد؟"); user_state[sid] = "wait_clone_count"
        except Exception as e: await msg.edit(f"❌ {e}"); user_state[sid] = None

    elif state == "wait_clone_count":
        try: temp_data[sid]['limit'] = int(text); await event.reply("3️⃣ الوجهة:"); user_state[sid] = "wait_clone_dest"
        except: await event.reply("❌")

    elif state == "wait_clone_dest":
        users = temp_data[sid]['scraped']; limit = temp_data[sid]['limit']
        msg = await event.reply(f"🚀 بدء ({limit})...")
        asyncio.create_task(add_members_task(user_client, text, users, limit, msg)); user_state[sid] = None

# دوال مساعدة
async def add_members_task(client, dest, users, limit, msg):
    try:
        dest_ent = await client.get_entity(dest); suc = 0; tried = 0
        while suc < limit and tried < len(users):
            u = users[tried]; tried += 1
            if u.bot or u.deleted: continue
            try:
                await client(InviteToChannelRequest(dest_ent, [u])); await asyncio.sleep(2)
                try: await client.get_permissions(dest_ent, u); suc += 1
                except: pass
                if suc % 5 == 0: await msg.edit(f"🔄 نقل: {suc}/{limit}")
                await asyncio.sleep(random.randint(5, 10))
            except FloodWaitError as e: await asyncio.sleep(e.seconds)
            except: break
        await msg.edit(f"🏁 تم: {suc}")
    except: await msg.edit("❌")

async def clean_deleted_accounts(chat_id):
    if not user_client: return
    users = await user_client.get_participants(chat_id); c=0
    for u in users:
        if u.deleted:
            try: await user_client(EditBannedRequest(chat_id, u.id, ChatBannedRights(until_date=None, view_messages=True))); c+=1; await asyncio.sleep(0.5)
            except: pass
    await user_client.send_message(chat_id, f"🧹 تم: {c}")

async def purge_my_msgs(chat_id):
    if not user_client: return
    me = await user_client.get_me(); msgs = [m.id async for m in user_client.iter_messages(chat_id, from_user=me, limit=100)]
    await user_client.delete_messages(chat_id, msgs)

async def list_admins(event):
    if not user_client: return
    ads = await user_client.get_participants(event.chat_id, filter=ChannelParticipantsAdmins)
    await event.reply("👮\n" + "\n".join([f"- {a.first_name}" for a in ads]))

# ------------------------------------------------------------------------------
# السيرفر الوهمي (Render) والتشغيل
# ------------------------------------------------------------------------------
async def web_page(request): return web.Response(text="Bot Alive on Render!")
async def start_web_server():
    app = web.Application(); app.add_routes([web.get('/', web_page)])
    runner = web.AppRunner(app); await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port); await site.start()
    print(f"✅ Web Server Running on port {port}")

@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    load_data()
    if settings["session"]: await start_user_bot(); await show_main_panel(event)
    else: await show_login_button(event)

async def show_login_button(event): await event.respond("👋 مرحباً", buttons=[[Button.inline("➕ تسجيل الدخول", b"login")]])

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
        print("✅ Userbot Active!")
    except: pass

if __name__ == '__main__':
    print("🚀 Starting Bot...")
    loop = asyncio.get_event_loop()
    loop.create_task(start_web_server())
    bot.run_until_disconnected()
