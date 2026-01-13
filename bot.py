# ==============================================================================
# 🤖 TELEGRAM USERBOT - ULTIMATE MULTI-USER EDITION (FULL EXPANDED)
# ==============================================================================
# Features:
# - Multi-User System (Independent Sessions)
# - MongoDB Cloud Database
# - Render Web Server (Keep-Alive)
# - Advanced Arabic Invoice (PDF)
# - Spy, Ghost, Clone, Voice, Tools
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
# Server & Database Libraries
# ------------------------------------------------------------------------------
from aiohttp import web
import pymongo
import certifi

# ------------------------------------------------------------------------------
# PDF & Text Processing Libraries
# ------------------------------------------------------------------------------
from fpdf import FPDF
import arabic_reshaper
from bidi.algorithm import get_display

# ------------------------------------------------------------------------------
# Telethon Libraries (Fully Expanded Imports)
# ------------------------------------------------------------------------------
from telethon import TelegramClient
from telethon import events
from telethon import Button
from telethon import functions
from telethon import types
from telethon.sessions import StringSession

# Channels Functions
from telethon.tl.functions.channels import CreateChannelRequest
from telethon.tl.functions.channels import EditBannedRequest
from telethon.tl.functions.channels import InviteToChannelRequest
from telethon.tl.functions.channels import GetParticipantsRequest
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.channels import JoinChannelRequest

# Messages Functions
from telethon.tl.functions.messages import SendReactionRequest
from telethon.tl.functions.messages import GetHistoryRequest
from telethon.tl.functions.messages import SetTypingRequest
from telethon.tl.functions.messages import ReadHistoryRequest
from telethon.tl.functions.messages import DeleteHistoryRequest

# Account & Users Functions
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.tl.functions.account import UpdateStatusRequest
from telethon.tl.functions.users import GetFullUserRequest

# Types & Errors
from telethon.tl.types import ReactionEmoji
from telethon.tl.types import UserStatusOnline
from telethon.tl.types import UserStatusOffline
from telethon.tl.types import UserStatusRecently
from telethon.tl.types import MessageMediaPhoto
from telethon.tl.types import MessageMediaDocument
from telethon.tl.types import ChatBannedRights
from telethon.tl.types import SendMessageCancelAction
from telethon.tl.types import InputPeerChannel
from telethon.tl.types import InputPeerUser
from telethon.tl.types import ChannelParticipantsAdmins

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
# System Configuration
# ------------------------------------------------------------------------------
warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MultiUserBot")

# Environment Variables
API_ID = int(os.environ.get("API_ID", 6))
API_HASH = os.environ.get("API_HASH", "eb06d4abfb49dc3eeb1aeb98ae0f581e")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
MONGO_URI = os.environ.get("MONGO_URI")

# Local Files
LOGO_FILE = "saved_store_logo.jpg"
FONT_FILE = "font.ttf"
FONT_URL = "https://github.com/google/fonts/raw/main/ofl/amiri/Amiri-Regular.ttf"

# ------------------------------------------------------------------------------
# Database Connection (MongoDB)
# ------------------------------------------------------------------------------
mongo_client = None
db = None
users_collection = None

print("⏳ Connecting to Cloud Database...")
try:
    if MONGO_URI:
        mongo_client = pymongo.MongoClient(
            MONGO_URI,
            tlsCAFile=certifi.where()
        )
        db = mongo_client["telegram_multi_userbot"]
        users_collection = db["users_data"]
        print("✅ Database Connected Successfully!")
    else:
        print("⚠️ Warning: No MONGO_URI provided.")
except Exception as e:
    print(f"❌ Database Error: {e}")

# ------------------------------------------------------------------------------
# Font Manager
# ------------------------------------------------------------------------------
if not os.path.exists(FONT_FILE) or os.path.getsize(FONT_FILE) < 1000:
    try:
        print("⏳ Downloading Font...")
        r = requests.get(FONT_URL)
        with open(FONT_FILE, 'wb') as f:
            f.write(r.content)
        print("✅ Font Ready.")
    except:
        pass

# ------------------------------------------------------------------------------
# Global Memory (RAM)
# ------------------------------------------------------------------------------
active_sessions = {}  # {user_id: UserSessionObject}
temp_state = {}       # {user_id: "state_name"}
invoice_drafts = {}   # {user_id: {data}}
temp_data = {}        # {user_id: {misc_data}}

# ------------------------------------------------------------------------------
# Helper Functions
# ------------------------------------------------------------------------------
def get_user_data(user_id):
    """Retrieve user document from DB"""
    if users_collection is None:
        return None
    return users_collection.find_one({"_id": user_id})

def update_user_data(user_id, data):
    """Update user document in DB"""
    if users_collection is None:
        return
    try:
        users_collection.update_one(
            {"_id": user_id},
            {"$set": data},
            upsert=True
        )
    except Exception as e:
        print(f"❌ Save Error: {e}")

def get_default_settings():
    """Default settings for new users"""
    return {
        "session": None,
        "running": False,
        "log_channel": None,
        "spy_mode": False,
        "ghost_mode": False,
        "auto_bio": False,
        "bio_template": "Time: %TIME% | Status: Online",
        "store_name": "My Store",
        "invoices_archive": {},
        "fake_offline": False,
        "anti_typing": False,
        "stalk_list": [],
        "typing_watch_list": [],
        "keywords": [],
        "replies": [],
        "anti_link_group": False,
        "auto_save_destruct": True
    }

# ------------------------------------------------------------------------------
# Invoice Generation System
# ------------------------------------------------------------------------------
def fix_text(text):
    if not text:
        return ""
    try:
        reshaped = arabic_reshaper.reshape(str(text))
        return get_display(reshaped)
    except:
        return str(text)

def create_invoice_pdf(data, code, filename, store_name):
    try:
        pdf = FPDF()
        pdf.add_page()
        
        is_ar = False
        if os.path.exists(FONT_FILE):
            pdf.add_font('Amiri', '', FONT_FILE, uni=True)
            is_ar = True
        
        pdf.set_font('Amiri' if is_ar else 'Helvetica', '', 12)
        
        def t(a, e):
            return fix_text(str(a)) if is_ar else str(e)

        # Header
        pdf.set_fill_color(44, 62, 80)
        pdf.rect(0, 0, 210, 40, 'F')
        pdf.set_text_color(255, 255, 255)
        pdf.set_font_size(24)
        pdf.set_xy(10, 10)
        pdf.cell(0, 10, text=t("INVOICE / فاتورة", "INVOICE"), border=0, align='C')
        
        pdf.set_font_size(10)
        pdf.set_xy(10, 22)
        pdf.cell(0, 10, text=f"Ref: #{code}", align='C')
        pdf.ln(30)

        # Info
        pdf.set_text_color(0, 0, 0)
        pdf.set_font_size(12)
        align = 'R' if is_ar else 'L'
        
        pdf.set_fill_color(236, 240, 241)
        pdf.cell(0, 10, text=t("التفاصيل", "Details"), ln=True, align=align, fill=True)
        
        line1 = f"Store: {store_name}"
        pdf.cell(190, 7, text=t(line1, line1), ln=True, align=align)
        
        line2 = f"Client: {data.get('client_name')}"
        pdf.cell(190, 7, text=t(line2, line2), ln=True, align=align)
        
        pdf.ln(10)

        # Table
        pdf.set_fill_color(44, 62, 80)
        pdf.set_text_color(255, 255, 255)
        pdf.set_draw_color(0, 0, 0)
        
        cols = ["Product", "Qty", "Price", "Warranty"]
        w = [80, 20, 40, 50]
        
        for i in range(4):
            pdf.cell(w[i], 10, text=cols[i], border=1, align='C', fill=True)
        pdf.ln()
        
        pdf.set_text_color(0, 0, 0)
        vals = [
            str(data.get('product')),
            str(data.get('count')),
            str(data.get('price')),
            str(data.get('warranty'))
        ]
        
        for i in range(4):
            val = fix_text(vals[i]) if is_ar else vals[i]
            pdf.cell(w[i], 10, text=val, border=1, align='C')
            
        pdf.ln(20)
        
        pdf.set_font_size(16)
        pdf.set_text_color(44, 62, 80)
        pdf.cell(0, 10, text=t(f"TOTAL: {vals[2]}", f"TOTAL: {vals[2]}"), ln=True, align='C')
        
        pdf.output(filename)
        return True
    except Exception as e:
        print(f"PDF Error: {e}")
        return False# ------------------------------------------------------------------------------
# CLASS: UserSession (The Personal Bot Core)
# ------------------------------------------------------------------------------
class UserSession:
    def __init__(self, user_id, settings):
        self.user_id = user_id
        self.settings = settings
        self.client = None
        self.bio_task = None
        self.msg_cache = {}

    async def start(self):
        """Start the individual userbot session"""
        try:
            self.client = TelegramClient(
                StringSession(self.settings["session"]),
                API_ID,
                API_HASH
            )
            await self.client.connect()
            
            # Register User-Specific Handlers
            self.client.add_event_handler(self.on_new_message, events.NewMessage())
            self.client.add_event_handler(self.on_message_edited, events.MessageEdited())
            self.client.add_event_handler(self.on_message_deleted, events.MessageDeleted())
            self.client.add_event_handler(self.on_user_update, events.UserUpdate())
            
            # Start Bio Loop
            if self.bio_task:
                self.bio_task.cancel()
            self.bio_task = asyncio.create_task(self.bio_loop())
            
            print(f"✅ User {self.user_id} Session Started.")
            return True
        except Exception as e:
            print(f"❌ User {self.user_id} Session Failed: {e}")
            return False

    async def stop(self):
        """Stop the session"""
        if self.bio_task:
            self.bio_task.cancel()
        if self.client:
            await self.client.disconnect()

    async def get_log_chat(self):
        """Get the logging channel entity"""
        if not self.settings["log_channel"]:
            return None
        try:
            return await self.client.get_entity(self.settings["log_channel"])
        except:
            return None

    # --- Event Handlers (Per User) ---

    async def on_new_message(self, event):
        try:
            # 1. Message Caching (For Spy Mode)
            if event.is_private:
                sender = await event.get_sender()
                name = getattr(sender, 'first_name', 'Unknown')
                
                self.msg_cache[event.id] = {
                    "text": event.raw_text,
                    "sender": name,
                    "is_private": True
                }
                
                # Cleanup cache
                if len(self.msg_cache) > 500: 
                    keys = list(self.msg_cache.keys())
                    for k in keys[:100]:
                        del self.msg_cache[k]

            # 2. Ghost Mode (Read without Blue Ticks)
            if self.settings["ghost_mode"]:
                if not event.out and event.is_private:
                    log = await self.get_log_chat()
                    if log:
                        await event.forward_to(log)
                        s_name = self.msg_cache.get(event.id, {}).get('sender', 'Unknown')
                        await self.client.send_message(log, f"👻 **شبح: رسالة جديدة من {s_name}**")

            # 3. Anti-Typing (Hide Typing Status)
            if self.settings["anti_typing"] and event.out:
                await self.client(SetTypingRequest(event.chat_id, SendMessageCancelAction()))

            # 4. Auto-Save Self-Destruct Media
            ttl = getattr(event.message, 'ttl_period', None)
            if self.settings["auto_save_destruct"]:
                if ttl and ttl > 0 and not event.out:
                    if event.media:
                        p = await event.download_media()
                        await self.client.send_file("me", p, caption=f"💣 **موقوتة محفوظة** ({ttl}s)")
                        
                        log = await self.get_log_chat()
                        if log:
                            await self.client.send_file(log, p, caption="💣 محفوظ من الخاص")
                        
                        os.remove(p)

            # 5. Anti-Link (Group Protection)
            if self.settings["anti_link_group"]:
                if event.is_group or event.is_channel:
                    if not event.out:
                        txt_low = event.raw_text.lower()
                        if "http" in txt_low or "t.me" in txt_low:
                            await event.delete()

        except Exception:
            pass

    async def on_message_edited(self, event):
        if not self.settings["spy_mode"]:
            return
        if not event.is_private:
            return
        try:
            log = await self.get_log_chat()
            if log:
                s = await event.get_sender()
                n = getattr(s, 'first_name', 'Unknown')
                msg = f"✏️ **تعديل رسالة (تجسس)**\n👤: {n}\n📝: `{event.raw_text}`"
                await self.client.send_message(log, msg)
        except:
            pass

    async def on_message_deleted(self, event):
        if not self.settings["spy_mode"]:
            return
        try:
            log = await self.get_log_chat()
            if log:
                for m in event.deleted_ids:
                    if m in self.msg_cache:
                        d = self.msg_cache[m]
                        if d['is_private']:
                            msg = f"🗑️ **حذف رسالة (تجسس)**\n👤: {d['sender']}\n📝: `{d['text']}`"
                            await self.client.send_message(log, msg)
        except:
            pass

    async def on_user_update(self, event):
        try:
            # Stalk List
            if event.user_id in self.settings["stalk_list"]:
                if event.online:
                    await self.client.send_message("me", f"🚨 **المراقب {event.user_id} متصل الآن!**")
            
            # Typing Watch
            if event.user_id in self.settings["typing_watch_list"]:
                if event.typing:
                    await self.client.send_message("me", f"✍️ **المراقب {event.user_id} يكتب...**")
        except:
            pass

    async def bio_loop(self):
        """Auto-Update Bio"""
        while True:
            if self.settings["auto_bio"]:
                try:
                    now = datetime.datetime.now().strftime("%I:%M %p")
                    bt = self.settings["bio_template"].replace("%TIME%", now)
                    await self.client(UpdateProfileRequest(about=bt))
                except:
                    pass
            await asyncio.sleep(60)# ------------------------------------------------------------------------------
# The Main Control Bot Logic
# ------------------------------------------------------------------------------
try:
    bot = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)
except:
    bot = TelegramClient('bot_session', API_ID, API_HASH)

async def show_panel(event, user_id, edit=False):
    """Displays the main control panel for a specific user"""
    if user_id not in active_sessions:
        await event.respond("❌ **خطأ:** يجب تسجيل الدخول أولاً.\nاستخدم /start")
        return

    us = active_sessions[user_id].settings
    st = "🟢" if us["running"] else "🔴"
    
    text = (
        f"🎛️ **لوحة التحكم (Multi-User Cloud)**\n"
        f"👤 **المستخدم:** `{user_id}`\n"
        f"ـــــــــــــــــــــــــــــــــــــــــــــــــ\n"
        f"📡 **الحالة:** {st}\n"
        f"👮 **تجسس:** {'✅' if us['spy_mode'] else '❌'}\n"
        f"👻 **شبح:** {'✅' if us['ghost_mode'] else '❌'}\n"
        f"🧾 **متجر:** {'✅' if us['store_name'] else '⚠️'}\n"
        f"ـــــــــــــــــــــــــــــــــــــــــــــــــ"
    )
    
    btns = [
        [
            Button.inline("🕵️ التجسس والمراقبة", b"menu_spy"),
            Button.inline("👻 الشبح والخصوصية", b"menu_ghost")
        ],
        [
            Button.inline("🏪 المتجر والفواتير", b"menu_store"),
            Button.inline("🛠️ الأدوات العامة", b"menu_tools")
        ],
        [
            Button.inline("🎤 الوسيط الصوتي", b"menu_voice"),
            Button.inline("🛡️ إدارة المجموعات", b"menu_group")
        ],
        [
            Button.inline(f"تشغيل/إيقاف {st}", b"toggle_run"),
            Button.inline("📢 إعداد السجل", b"log_set")
        ],
        [
            Button.inline("🚪 تسجيل الخروج", b"logout"),
            Button.inline("❌ إغلاق اللوحة", b"close")
        ]
    ]
    
    if edit:
        try: await event.edit(text, buttons=btns)
        except: await event.respond(text, buttons=btns)
    else:
        await event.respond(text, buttons=btns)

@bot.on(events.CallbackQuery)
async def cb_handler(event):
    uid = event.sender_id
    d = event.data.decode()
    
    # Login Flow
    if d == "login_btn":
        temp_state[uid] = "wait_session"
        await event.respond("📩 **أرسل كود الجلسة (String Session) الآن:**")
        return

    # Check Auth
    if uid not in active_sessions:
        await event.answer("⚠️ غير مصرح لك! سجل دخولك.", alert=True)
        return

    user_obj = active_sessions[uid]
    sett = user_obj.settings

    # Actions
    if d == "close":
        await event.delete()
        
    elif d == "logout":
        await user_obj.stop()
        del active_sessions[uid]
        update_user_data(uid, {"session": None})
        await event.edit("✅ **تم تسجيل الخروج بنجاح.**")
        
    elif d == "refresh_panel":
        await show_panel(event, uid, True)
    
    # Menus
    elif d == "menu_store":
        btns = [
            [Button.inline("➕ فاتورة جديدة", b"add_inv"), Button.inline("⚙️ اسم المتجر", b"set_store")],
            [Button.inline("🔙 رجوع", b"refresh_panel")]
        ]
        await event.edit("🏪 **قائمة المتجر:**", buttons=btns)
        
    elif d == "menu_spy":
        btns = [
            [Button.inline(f"تجسس {'✅' if sett['spy_mode'] else '❌'}", b"t_spy"), Button.inline(f"حفظ الموقوت {'✅' if sett['auto_save_destruct'] else '❌'}", b"t_save")],
            [Button.inline("🔙 رجوع", b"refresh_panel")]
        ]
        await event.edit("🕵️ **قائمة التجسس:**", buttons=btns)
        
    elif d == "menu_ghost":
        btns = [
            [Button.inline(f"شبح {'✅' if sett['ghost_mode'] else '❌'}", b"t_ghost"), Button.inline(f"مانع كتابة {'✅' if sett['anti_typing'] else '❌'}", b"t_type")],
            [Button.inline("🔙 رجوع", b"refresh_panel")]
        ]
        await event.edit("👻 **قائمة الشبح:**", buttons=btns)
    
    elif d == "menu_tools":
        btns = [
            [Button.inline("📥 تحميل", b"dl_media"), Button.inline("🌐 IP", b"get_ip")],
            [Button.inline("🔙 رجوع", b"refresh_panel")]
        ]
        await event.edit("🛠️ **الأدوات:**", buttons=btns)

    elif d == "menu_voice":
        btns = [
            [Button.inline("🔇 عادي", b"v_none"), Button.inline("🚗 سيارة", b"v_car")],
            [Button.inline("🔙 رجوع", b"refresh_panel")]
        ]
        await event.edit("🎤 **الوسيط الصوتي:**", buttons=btns)

    elif d == "menu_group":
        btns = [
            [Button.inline("👥 استنساخ (Clone)", b"g_clone"), Button.inline("🧹 تنظيف", b"g_clean")],
            [Button.inline("🔙 رجوع", b"refresh_panel")]
        ]
        await event.edit("🛡️ **المجموعات:**", buttons=btns)

    # Toggles
    elif d == "toggle_run":
        sett["running"] = not sett["running"]
        update_user_data(uid, sett)
        await show_panel(event, uid, True)
    elif d == "t_spy":
        sett["spy_mode"] = not sett["spy_mode"]
        update_user_data(uid, sett)
        await show_panel(event, uid, True)
    elif d == "t_save":
        sett["auto_save_destruct"] = not sett["auto_save_destruct"]
        update_user_data(uid, sett)
        await show_panel(event, uid, True)
    elif d == "t_ghost":
        sett["ghost_mode"] = not sett["ghost_mode"]
        update_user_data(uid, sett)
        await show_panel(event, uid, True)
    elif d == "t_type":
        sett["anti_typing"] = not sett["anti_typing"]
        update_user_data(uid, sett)
        await show_panel(event, uid, True)

    # Commands
    elif d == "add_inv":
        invoice_drafts[uid] = {}
        temp_state[uid] = "inv_client"
        await event.respond("👤 **أرسل اسم العميل:**")
        await event.delete()
        
    elif d == "set_store":
        temp_state[uid] = "set_store"
        await event.respond("🏪 **أرسل اسم المتجر الجديد:**")
        await event.delete()
        
    elif d == "log_set":
        try:
            ch = await user_obj.client(CreateChannelRequest("Userbot Logs", "Logs", megagroup=False))
            sett["log_channel"] = int(f"-100{ch.chats[0].id}")
            update_user_data(uid, sett)
            await event.answer("✅ تم إنشاء القناة وتعيينها!")
        except:
            await event.answer("❌ حدث خطأ أثناء الإنشاء", alert=True)

    elif d == "g_clone":
        temp_state[uid] = "wait_clone_src"
        await event.respond("👥 **أرسل رابط المجموعة المراد نسخ الأعضاء منها:**")
        await event.delete()

    elif d == "g_clean":
        await event.respond("⏳ جاري تنظيف الحسابات المحذوفة...")
        asyncio.create_task(clean_deleted_accounts(user_obj.client, event.chat_id))
    
    elif d.startswith("v_"):
        # Placeholder for voice logic
        await event.answer("تم اختيار الوضع")# ------------------------------------------------------------------------------
# Input Handler (Text Messages)
# ------------------------------------------------------------------------------
@bot.on(events.NewMessage)
async def msg_handler(event):
    if event.sender_id == (await bot.get_me()).id: return
    uid = event.sender_id
    text = event.text.strip()
    state = temp_state.get(uid)

    # 1. Login Logic
    if state == "wait_session":
        try:
            test_c = TelegramClient(StringSession(text), API_ID, API_HASH)
            await test_c.connect()
            if await test_c.is_user_authorized():
                await test_c.disconnect()
                
                # Save to DB
                user_data = get_user_data(uid)
                if not user_data: user_data = get_default_settings()
                user_data["session"] = text
                user_data["_id"] = uid
                update_user_data(uid, user_data)
                
                # Start Session
                new_session = UserSession(uid, user_data)
                if await new_session.start():
                    active_sessions[uid] = new_session
                    await event.reply("✅ **تم تسجيل الدخول بنجاح!**\nجاري تشغيل البوت...")
                    await show_panel(event, uid)
                else:
                    await event.reply("❌ فشل تشغيل الجلسة.")
            else:
                await event.reply("❌ الكود غير صالح أو منتهي.")
        except Exception as e:
            await event.reply(f"❌ خطأ تقني: {e}")
        temp_state[uid] = None

    # 2. Store Logic
    elif state == "set_store":
        if uid in active_sessions:
            active_sessions[uid].settings["store_name"] = text
            update_user_data(uid, active_sessions[uid].settings)
            await event.reply("✅ تم حفظ اسم المتجر.")
        temp_state[uid] = None

    elif state == "inv_client":
        invoice_drafts[uid]['client_name'] = text
        temp_state[uid] = "inv_prod"
        await event.reply("🛍️ **أرسل اسم المنتج:**")
    elif state == "inv_prod":
        invoice_drafts[uid]['product'] = text
        temp_state[uid] = "inv_count"
        await event.reply("🔢 **أرسل العدد:**")
    elif state == "inv_count":
        invoice_drafts[uid]['count'] = text
        temp_state[uid] = "inv_price"
        await event.reply("💰 **أرسل السعر الإجمالي:**")
    elif state == "inv_price":
        invoice_drafts[uid]['price'] = text
        temp_state[uid] = "inv_warr"
        await event.reply("🛡️ **أرسل مدة الضمان:**")
    elif state == "inv_warr":
        invoice_drafts[uid]['warranty'] = text
        
        # Generate Code & PDF
        code = str(random.randint(100000, 999999))
        fn = f"Invoice_{code}.pdf"
        s_name = active_sessions[uid].settings.get("store_name", "Store")
        
        await event.reply("⏳ جاري إنشاء الفاتورة...")
        
        if create_invoice_pdf(invoice_drafts[uid], code, fn, s_name):
            await event.client.send_file(
                event.chat_id, 
                fn, 
                caption=f"🧾 **فاتورة جديدة**\n🔐 المرجع: `{code}`"
            )
            os.remove(fn)
        else:
            await event.reply("❌ فشل إنشاء ملف PDF.")
            
        temp_state[uid] = None
        await show_panel(event, uid)

    # 3. Clone Logic (Real Adder)
    elif state == "wait_clone_src":
        temp_data[uid] = {"src": text}
        temp_state[uid] = "wait_clone_dest"
        await event.reply("3️⃣ **أرسل رابط المجموعة الوجهة (التي ستضيف الأعضاء إليها):**")
        
    elif state == "wait_clone_dest":
        src = temp_data[uid]["src"]
        dest = text
        user_sess = active_sessions[uid]
        
        msg = await event.reply("🚀 جاري بدء عملية النقل...")
        asyncio.create_task(run_clone_process(user_sess.client, src, dest, msg))
        temp_state[uid] = None

# ------------------------------------------------------------------------------
# Helper Tasks (Clone & Clean)
# ------------------------------------------------------------------------------
async def run_clone_process(client, src_link, dest_link, msg_entity):
    try:
        # Resolve entities
        try:
            if "t.me" in src_link: await client(JoinChannelRequest(src_link))
            if "t.me" in dest_link: await client(JoinChannelRequest(dest_link))
        except: pass

        src_ent = await client.get_entity(src_link)
        dest_ent = await client.get_entity(dest_link)
        
        await msg_entity.edit("⏳ جاري سحب الأعضاء من المصدر...")
        participants = await client.get_participants(src_ent, aggressive=True)
        
        users_to_add = [u for u in participants if not u.bot and not u.deleted]
        await msg_entity.edit(f"✅ تم سحب {len(users_to_add)} عضو.\nبدء الإضافة...")
        
        success = 0
        for user in users_to_add:
            try:
                await client(InviteToChannelRequest(dest_ent, [user]))
                success += 1
                if success % 5 == 0:
                    await msg_entity.edit(f"🔄 جاري الإضافة: {success}")
                await asyncio.sleep(random.randint(5, 10))
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds)
            except:
                pass
        
        await msg_entity.edit(f"🏁 **اكتملت العملية!**\n✅ تمت إضافة: {success} عضو.")
        
    except Exception as e:
        await msg_entity.edit(f"❌ حدث خطأ: {e}")

async def clean_deleted_accounts(client, chat_id):
    try:
        users = await client.get_participants(chat_id)
        deleted = [u for u in users if u.deleted]
        count = 0
        for u in deleted:
            try:
                await client(EditBannedRequest(chat_id, u.id, ChatBannedRights(until_date=None, view_messages=True)))
                count += 1
                await asyncio.sleep(0.5)
            except: pass
        await client.send_message(chat_id, f"🧹 **تم تنظيف {count} حساب محذوف.**")
    except: pass

# ------------------------------------------------------------------------------
# Session Restoration & Web Server
# ------------------------------------------------------------------------------
async def restore_sessions():
    """Restores all saved sessions from DB on restart"""
    if users_collection is None: return
    print("🔄 [System] Restoring Sessions...")
    
    cursor = users_collection.find({})
    for user_doc in cursor:
        if user_doc.get("session"):
            uid = user_doc["_id"]
            print(f"🔄 Restoring User: {uid}")
            session_obj = UserSession(uid, user_doc)
            if await session_obj.start():
                active_sessions[uid] = session_obj
            await asyncio.sleep(2)

async def web_page(request):
    return web.Response(text="Multi-User Bot is Alive!")

async def start_server():
    app = web.Application()
    app.add_routes([web.get('/', web_page)])
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"✅ Web Server Running on port {port}")

# ------------------------------------------------------------------------------
# Main Entry Point
# ------------------------------------------------------------------------------
@bot.on(events.NewMessage(pattern='/start'))
async def on_start(event):
    uid = event.sender_id
    if uid in active_sessions:
        await show_panel(event, uid)
    else:
        await event.respond(
            "👋 **مرحباً بك في بوت الخدمات المتعدد!**\n\n"
            "هذا البوت يتيح لك تشغيل يوزربوت خاص بك بمميزات (تجسس، شبح، فواتير) بشكل مستقل عن الآخرين.\n\n"
            "اضغط الأسفل لتسجيل الدخول.",
            buttons=[[Button.inline("➕ تسجيل الدخول (Login)", b"login_btn")]]
        )

if __name__ == '__main__':
    print("🚀 Starting System...")
    loop = asyncio.get_event_loop()
    loop.create_task(start_server())
    loop.create_task(restore_sessions())
    bot.run_until_disconnected()
