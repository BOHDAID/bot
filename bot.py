# ==============================================================================
# 🤖 TELEGRAM USERBOT - PROFESSIONAL MONOLITHIC EDITION (v7.0)
# ==============================================================================
# Developed for Render + MongoDB
# Architecture: Single User | OOP | Fully Expanded
# Lines: ~750+ (Combined)
# ==============================================================================

import asyncio
import logging
import os
import sys
import time
import json
import random
import datetime
import traceback
import requests
import zipfile
import io
import warnings

# Third-party libraries
try:
    import pymongo
    import certifi
    from aiohttp import web
    from fpdf import FPDF
    import arabic_reshaper
    from bidi.algorithm import get_display
    from telethon import TelegramClient, events, Button, functions, types
    from telethon.sessions import StringSession
    from telethon.tl.functions.channels import (
        CreateChannelRequest, EditBannedRequest, InviteToChannelRequest,
        GetParticipantsRequest, GetFullChannelRequest, JoinChannelRequest
    )
    from telethon.tl.functions.messages import (
        SendReactionRequest, SetTypingRequest, ReadHistoryRequest, DeleteHistoryRequest
    )
    from telethon.tl.functions.account import (
        UpdateProfileRequest, UpdateStatusRequest
    )
    from telethon.tl.functions.users import GetFullUserRequest
    from telethon.tl.types import (
        SendMessageCancelAction, ChannelParticipantsAdmins, ChatBannedRights
    )
    from telethon.errors import (
        MessageNotModifiedError, FloodWaitError, UserPrivacyRestrictedError
    )
except ImportError as e:
    print(f"❌ Missing Library: {e}")
    sys.exit(1)

# ------------------------------------------------------------------------------
# 1. SYSTEM CONFIGURATION & LOGGING
# ------------------------------------------------------------------------------
warnings.filterwarnings("ignore")
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("LegendaryBot")

# ------------------------------------------------------------------------------
# 2. CONFIGURATION CLASS (MANAGES ENV VARIABLES)
# ------------------------------------------------------------------------------
class Config:
    API_ID = int(os.environ.get("API_ID", 6))
    API_HASH = os.environ.get("API_HASH", "eb06d4abfb49dc3eeb1aeb98ae0f581e")
    BOT_TOKEN = os.environ.get("BOT_TOKEN")
    MONGO_URI = os.environ.get("MONGO_URI")
    SESSION = os.environ.get("SESSION") # كود الجلسة الاختياري من البيئة
    PORT = int(os.environ.get("PORT", 8080))
    
    # Local Assets
    LOGO_PATH = "saved_store_logo.jpg"
    FONT_PATH = "font.ttf"
    FONT_URL = "https://github.com/google/fonts/raw/main/ofl/amiri/Amiri-Regular.ttf"

# ------------------------------------------------------------------------------
# 3. DATABASE MANAGER CLASS (MONGODB)
# ------------------------------------------------------------------------------
class DatabaseManager:
    def __init__(self):
        self.client = None
        self.db = None
        self.col = None
        self.is_connected = False

    def connect(self):
        print("⏳ [Database] Initializing connection...")
        try:
            if Config.MONGO_URI:
                self.client = pymongo.MongoClient(
                    Config.MONGO_URI,
                    tlsCAFile=certifi.where(),
                    serverSelectionTimeoutMS=5000
                )
                self.db = self.client["telegram_advanced_bot"]
                self.col = self.db["user_settings"]
                # Test connection
                self.client.server_info()
                self.is_connected = True
                print("✅ [Database] Connected successfully!")
            else:
                print("⚠️ [Database] No MONGO_URI found. Running in memory mode.")
        except Exception as e:
            print(f"❌ [Database] Connection Failed: {e}")
            self.is_connected = False

    def get_settings(self):
        """Fetch settings document, create default if not exists"""
        default = {
            "_id": "main_config",
            "session": Config.SESSION,
            "running": False,
            "log_channel": None,
            "spy_mode": False,
            "ghost_mode": False,
            "anti_typing": False,
            "fake_offline": False,
            "keywords": [],
            "replies": [],
            "typing_delay": 2,
            "work_mode": False,
            "work_start": 8,
            "work_end": 22,
            "store_name": "My Digital Store",
            "invoices_archive": {},
            "auto_bio": False,
            "bio_template": "Time: %TIME% | Status: Online",
            "stalk_list": [],
            "typing_watch_list": [],
            "anti_link_group": False,
            "auto_save_destruct": True
        }
        
        if not self.is_connected:
            return default

        try:
            data = self.col.find_one({"_id": "main_config"})
            if data:
                # Merge keys to ensure new features exist
                for key, val in default.items():
                    if key not in data:
                        data[key] = val
                return data
            else:
                self.col.insert_one(default)
                return default
        except Exception as e:
            print(f"❌ [Database] Read Error: {e}")
            return default

    def update_settings(self, new_data):
        """Update the settings document"""
        if not self.is_connected:
            return
        try:
            self.col.update_one(
                {"_id": "main_config"},
                {"$set": new_data},
                upsert=True
            )
        except Exception as e:
            print(f"❌ [Database] Write Error: {e}")

# Initialize DB
db_manager = DatabaseManager()
db_manager.connect()
SETTINGS = db_manager.get_settings()

# ------------------------------------------------------------------------------
# 4. INVOICE GENERATOR CLASS (PDF SYSTEM)
# ------------------------------------------------------------------------------
class InvoiceGenerator:
    def __init__(self):
        self._check_font()

    def _check_font(self):
        if not os.path.exists(Config.FONT_PATH) or os.path.getsize(Config.FONT_PATH) < 1000:
            try:
                print("⏳ [Font] Downloading Arabic Font...")
                r = requests.get(Config.FONT_URL)
                with open(Config.FONT_PATH, 'wb') as f:
                    f.write(r.content)
                print("✅ [Font] Download complete.")
            except Exception as e:
                print(f"❌ [Font] Error: {e}")

    def _fix_text(self, text):
        if not text: return ""
        try:
            reshaped_text = arabic_reshaper.reshape(str(text))
            return get_display(reshaped_text)
        except:
            return str(text)

    def generate(self, data, ref_code, filename):
        try:
            pdf = FPDF()
            pdf.add_page()
            
            is_arabic = False
            if os.path.exists(Config.FONT_PATH):
                pdf.add_font('Amiri', '', Config.FONT_PATH, uni=True)
                is_arabic = True
            
            font_family = 'Amiri' if is_arabic else 'Helvetica'
            pdf.set_font(font_family, '', 12)

            # Helper for bilingual support
            def t(ar, en): return self._fix_text(str(ar)) if is_arabic else str(en)

            # --- Header Section ---
            pdf.set_fill_color(44, 62, 80)
            pdf.rect(0, 0, 210, 40, 'F')
            pdf.set_text_color(255, 255, 255)
            pdf.set_font_size(24)
            pdf.set_xy(10, 10)
            pdf.cell(0, 10, text=t("INVOICE / فاتورة", "INVOICE"), border=0, align='C')
            
            pdf.set_font_size(10)
            pdf.set_xy(10, 22)
            pdf.cell(0, 10, text=f"Reference: #{ref_code}", align='C')
            
            if os.path.exists(Config.LOGO_PATH):
                pdf.image(Config.LOGO_PATH, x=170, y=5, w=30)
            
            pdf.ln(30)

            # --- Info Section ---
            pdf.set_text_color(0, 0, 0)
            pdf.set_font_size(12)
            align = 'R' if is_arabic else 'L'
            
            pdf.set_fill_color(236, 240, 241)
            pdf.cell(0, 10, text=t("تفاصيل الفاتورة", "Invoice Details"), ln=True, align=align, fill=True)
            
            store_name = SETTINGS.get("store_name", "Unknown Store")
            client_name = data.get("client_name", "Client")
            date_str = datetime.datetime.now().strftime("%Y-%m-%d")
            
            pdf.cell(190, 7, text=t(f"From: {store_name}", f"From: {store_name}"), ln=True, align=align)
            pdf.cell(190, 7, text=t(f"To: {client_name}", f"To: {client_name}"), ln=True, align=align)
            pdf.cell(190, 7, text=t(f"Date: {date_str}", f"Date: {date_str}"), ln=True, align=align)
            pdf.ln(10)

            # --- Table Section ---
            pdf.set_fill_color(44, 62, 80)
            pdf.set_text_color(255, 255, 255)
            pdf.set_draw_color(0, 0, 0)
            
            headers_ar = ["المنتج", "العدد", "الضمان", "السعر"]
            headers_en = ["Product", "Qty", "Warranty", "Price"]
            widths = [80, 25, 45, 40]
            
            # Draw Headers
            if is_arabic:
                for i in reversed(range(4)):
                    pdf.cell(widths[i], 10, text=t(headers_ar[i], ""), border=1, align='C', fill=True)
            else:
                for i in range(4):
                    pdf.cell(widths[i], 10, text=headers_en[i], border=1, align='C', fill=True)
            pdf.ln()
            
            # Draw Values
            pdf.set_text_color(0, 0, 0)
            val_prod = str(data.get('product', '-'))
            val_qty = str(data.get('count', '1'))
            val_warr = str(data.get('warranty', '-'))
            val_price = str(data.get('price', '0'))
            
            if is_arabic:
                pdf.cell(widths[3], 10, text=self._fix_text(val_price), border=1, align='C')
                pdf.cell(widths[2], 10, text=self._fix_text(val_warr), border=1, align='C')
                pdf.cell(widths[1], 10, text=self._fix_text(val_qty), border=1, align='C')
                pdf.cell(widths[0], 10, text=self._fix_text(val_prod), border=1, align='R')
            else:
                pdf.cell(widths[0], 10, text=val_prod, border=1, align='L')
                pdf.cell(widths[1], 10, text=val_qty, border=1, align='C')
                pdf.cell(widths[2], 10, text=val_warr, border=1, align='C')
                pdf.cell(widths[3], 10, text=val_price, border=1, align='C')
            
            pdf.ln(20)
            
            # --- Footer ---
            pdf.set_font_size(16)
            pdf.set_text_color(44, 62, 80)
            pdf.cell(0, 10, text=t(f"TOTAL: {val_price}", f"TOTAL: {val_price}"), ln=True, align='C')
            
            pdf.output(filename)
            return True
        except Exception as e:
            print(f"❌ PDF Error: {e}")
            return False

# Initialize Invoice Generator
invoice_gen = InvoiceGenerator()# ------------------------------------------------------------------------------
# 5. MAIN USERBOT CONTROLLER CLASS
# ------------------------------------------------------------------------------
class UserBotController:
    def __init__(self):
        self.bot = TelegramClient('bot_session', Config.API_ID, Config.API_HASH)
        self.user = None
        self.bio_task = None
        
        # Runtime Memory
        self.user_cooldowns = {}
        self.user_state = {}
        self.invoice_drafts = {}
        self.temp_data = {}
        self.message_cache = {}

    async def start(self):
        """Starts the Controller Bot (Bot Token)"""
        try:
            await self.bot.start(bot_token=Config.BOT_TOKEN)
            print("✅ [Controller] Bot Started.")
            
            # Try to start User Client if session exists
            if SETTINGS.get("session"):
                await self.start_user_client(SETTINGS["session"])
                
            # Register Bot Handlers
            self.bot.add_event_handler(self.handle_callback, events.CallbackQuery)
            self.bot.add_event_handler(self.handle_bot_message, events.NewMessage)
            
        except Exception as e:
            print(f"❌ [Controller] Error: {e}")

    async def start_user_client(self, session_str):
        """Starts the User Client (String Session)"""
        try:
            if self.user:
                await self.user.disconnect()
            
            self.user = TelegramClient(StringSession(session_str), Config.API_ID, Config.API_HASH)
            await self.user.connect()
            
            if not await self.user.is_user_authorized():
                print("❌ [User] Session expired or invalid.")
                return False
            
            # Add User Handlers
            self.user.add_event_handler(self.user_watcher, events.NewMessage())
            self.user.add_event_handler(self.user_edited, events.MessageEdited())
            self.user.add_event_handler(self.user_deleted, events.MessageDeleted())
            self.user.add_event_handler(self.user_update_status, events.UserUpdate())
            
            # Start Bio Task
            if self.bio_task: self.bio_task.cancel()
            self.bio_task = asyncio.create_task(self.bio_loop())
            
            print("✅ [User] Userbot Client Connected!")
            return True
        except Exception as e:
            print(f"❌ [User] Connection Failed: {e}")
            return False

    # --- Userbot Event Handlers (The Logic) ---
    
    async def get_log_chat(self):
        if not SETTINGS.get("log_channel") or not self.user: return None
        try: return await self.user.get_entity(SETTINGS["log_channel"])
        except: return None

    async def user_watcher(self, event):
        try:
            # 1. Message Caching (For Spy)
            if event.is_private:
                sender = await event.get_sender()
                name = getattr(sender, 'first_name', 'Unknown')
                self.message_cache[event.id] = {
                    "text": event.raw_text,
                    "sender": name,
                    "is_private": True
                }
                # Cleanup cache
                if len(self.message_cache) > 500:
                    keys = list(self.message_cache.keys())
                    for k in keys[:100]: del self.message_cache[k]

            # 2. Ghost Mode
            if SETTINGS.get("ghost_mode") and not event.out and event.is_private:
                log = await self.get_log_chat()
                if log:
                    await event.forward_to(log)
                    s_name = self.message_cache.get(event.id, {}).get('sender', 'Unknown')
                    await self.user.send_message(log, f"👻 **Ghost Read:** Message from {s_name}")

            # 3. Anti-Typing
            if SETTINGS.get("anti_typing") and event.out:
                await self.user(SetTypingRequest(event.chat_id, SendMessageCancelAction()))

            # 4. Save Self-Destructs
            ttl = getattr(event.message, 'ttl_period', None)
            if SETTINGS.get("auto_save_destruct") and ttl and ttl > 0 and not event.out:
                if event.media:
                    p = await event.download_media()
                    caption = f"💣 **Saved Destruct Media** ({ttl}s)"
                    await self.user.send_file("me", p, caption=caption)
                    
                    log = await self.get_log_chat()
                    if log: await self.user.send_file(log, p, caption=caption)
                    os.remove(p)

            # 5. Auto-Reply
            if SETTINGS.get("running") and self.is_working_hours() and not event.out:
                txt = event.raw_text.strip()
                if any(k in txt for k in SETTINGS.get("keywords", [])):
                    last = self.user_cooldowns.get(event.chat_id, 0)
                    if time.time() - last > 10: # 10s cooldown
                        async with self.user.action(event.chat_id, 'typing'):
                            await asyncio.sleep(SETTINGS.get("typing_delay", 2))
                            if SETTINGS.get("replies"):
                                await event.reply(random.choice(SETTINGS["replies"]))
                        self.user_cooldowns[event.chat_id] = time.time()

            # 6. Anti-Link
            if SETTINGS.get("anti_link_group") and (event.is_group or event.is_channel) and not event.out:
                if "http" in event.raw_text.lower():
                    await event.delete()

        except Exception as e:
            print(f"Handler Error: {e}")

    async def user_edited(self, event):
        if not SETTINGS.get("spy_mode") or not event.is_private: return
        try:
            log = await self.get_log_chat()
            if log:
                s = await event.get_sender()
                n = getattr(s, 'first_name', 'Unknown')
                msg = f"✏️ **Spy Edit**\n👤: {n}\n📝: `{event.raw_text}`"
                await self.user.send_message(log, msg)
        except: pass

    async def user_deleted(self, event):
        if not SETTINGS.get("spy_mode"): return
        try:
            log = await self.get_log_chat()
            if log:
                for m in event.deleted_ids:
                    if m in self.message_cache:
                        d = self.message_cache[m]
                        if d['is_private']:
                            msg = f"🗑️ **Spy Delete**\n👤: {d['sender']}\n📝: `{d['text']}`"
                            await self.user.send_message(log, msg)
        except: pass

    async def user_update_status(self, event):
        if not self.user: return
        try:
            if event.user_id in SETTINGS.get("stalk_list", []) and event.online:
                await self.user.send_message("me", f"🚨 **Stalk Alert:** User {event.user_id} Online!")
            if event.user_id in SETTINGS.get("typing_watch_list", []) and event.typing:
                await self.user.send_message("me", f"✍️ **Typing Alert:** User {event.user_id} is typing...")
        except: pass

    async def bio_loop(self):
        while True:
            if SETTINGS.get("auto_bio") and self.user:
                try:
                    now = datetime.datetime.now().strftime("%I:%M %p")
                    bt = SETTINGS.get("bio_template", "").replace("%TIME%", now)
                    await self.user(UpdateProfileRequest(about=bt))
                except: pass
            await asyncio.sleep(60)

    def is_working_hours(self):
        if not SETTINGS.get("work_mode"): return True
        h = datetime.datetime.now().hour
        s = SETTINGS.get("work_start", 0)
        e = SETTINGS.get("work_end", 23)
        return s <= h < e

    # --- UI & Interaction Handlers ---

    async def handle_bot_message(self, event):
        if event.sender_id == (await self.bot.get_me()).id: return
        sid = event.sender_id
        text = event.text.strip()
        state = self.user_state.get(sid)

        # Login
        if state == "login":
            try:
                if await self.start_user_client(text):
                    SETTINGS["session"] = text
                    db_manager.update_settings(SETTINGS)
                    await event.reply("✅ **Login Successful!**")
                    await self.send_panel(event)
                else:
                    await event.reply("❌ **Invalid Session.**")
            except Exception as e:
                await event.reply(f"❌ **Error:** {e}")
            self.user_state[sid] = None

        # Auto Reply Inputs
        elif state == "add_kw":
            SETTINGS["keywords"].append(text)
            db_manager.update_settings(SETTINGS)
            await event.reply(f"✅ Keyword Added: `{text}`")
            self.user_state[sid] = None
        elif state == "add_rep":
            SETTINGS["replies"].append(text)
            db_manager.update_settings(SETTINGS)
            await event.reply(f"✅ Reply Added: `{text}`")
            self.user_state[sid] = None

        # Store Inputs
        elif state == "set_store":
            SETTINGS["store_name"] = text
            db_manager.update_settings(SETTINGS)
            await event.reply("✅ Store Name Saved.")
            self.user_state[sid] = None
        elif state == "inv_client":
            self.invoice_drafts[sid] = {"client_name": text}
            self.user_state[sid] = "inv_prod"
            await event.reply("🛍️ **Enter Product Name:**")
        elif state == "inv_prod":
            self.invoice_drafts[sid]["product"] = text
            self.user_state[sid] = "inv_count"
            await event.reply("🔢 **Enter Quantity:**")
        elif state == "inv_count":
            self.invoice_drafts[sid]["count"] = text
            self.user_state[sid] = "inv_price"
            await event.reply("💰 **Enter Total Price:**")
        elif state == "inv_price":
            self.invoice_drafts[sid]["price"] = text
            self.user_state[sid] = "inv_warr"
            await event.reply("🛡️ **Enter Warranty Period:**")
        elif state == "inv_warr":
            self.invoice_drafts[sid]["warranty"] = text
            # Generate
            code = str(random.randint(100000, 999999))
            fn = f"Inv_{code}.pdf"
            
            if invoice_gen.generate(self.invoice_drafts[sid], code, fn):
                await event.client.send_file(
                    event.chat_id, fn, 
                    caption=f"🧾 **Invoice Created**\nRef: `{code}`"
                )
                os.remove(fn)
                # Archive
                SETTINGS["invoices_archive"][code] = self.invoice_drafts[sid]
                db_manager.update_settings(SETTINGS)
            else:
                await event.reply("❌ Failed to generate PDF.")
            
            self.user_state[sid] = None
            await self.send_panel(event) # Return to main

        # Default Start
        elif text == "/start":
            if SETTINGS.get("session"):
                await self.send_panel(event)
            else:
                await event.respond(
                    "👋 **Welcome to Ultimate Userbot**\nLogin to continue.",
                    buttons=[[Button.inline("➕ Login via Session", b"login")]]
                )

    async def handle_callback(self, event):
        try:
            data = event.data.decode()
            sid = event.sender_id
            
            if data == "close":
                await event.delete()
            elif data == "refresh":
                await self.send_panel(event, edit=True)
            elif data == "login":
                self.user_state[sid] = "login"
                await event.respond("📩 **Send your String Session Code:**")
                await event.delete()
            elif data == "logout":
                if self.user: await self.user.disconnect()
                SETTINGS["session"] = None
                db_manager.update_settings(SETTINGS)
                await event.edit("✅ Logged Out.")
            
            # Toggles
            elif data.startswith("t_"):
                key = data[2:] # run, spy, ghost, etc
                if key == "run": SETTINGS["running"] = not SETTINGS["running"]
                elif key == "spy": SETTINGS["spy_mode"] = not SETTINGS["spy_mode"]
                elif key == "ghost": SETTINGS["ghost_mode"] = not SETTINGS["ghost_mode"]
                elif key == "save": SETTINGS["auto_save_destruct"] = not SETTINGS["auto_save_destruct"]
                elif key == "type": SETTINGS["anti_typing"] = not SETTINGS["anti_typing"]
                
                db_manager.update_settings(SETTINGS)
                await self.send_panel(event, edit=True)

            # Menus
            elif data == "m_reply":
                k = len(SETTINGS["keywords"])
                r = len(SETTINGS["replies"])
                btns = [
                    [Button.inline("➕ Add Keyword", b"add_kw"), Button.inline("➕ Add Reply", b"add_rep")],
                    [Button.inline("🗑️ Clear All", b"clr_rep"), Button.inline("🔙 Back", b"refresh")]
                ]
                await event.edit(f"💬 **Auto Reply Config**\nKeywords: {k}\nReplies: {r}", buttons=btns)
            
            elif data == "m_store":
                btns = [[Button.inline("➕ Create Invoice", b"add_inv"), Button.inline("⚙️ Set Name", b"set_store")], [Button.inline("🔙 Back", b"refresh")]]
                await event.edit("🏪 **Store Management**", buttons=btns)

            elif data == "m_tools":
                btns = [[Button.inline("👥 Clone Group", b"g_clone"), Button.inline("🧹 Clean Deleted", b"g_clean")], [Button.inline("🔙 Back", b"refresh")]]
                await event.edit("🛠️ **Tools Menu**", buttons=btns)

            # Commands
            elif data == "add_kw":
                self.user_state[sid] = "add_kw"
                await event.respond("🔑 **Send the Keyword:**")
                await event.delete()
            elif data == "add_rep":
                self.user_state[sid] = "add_rep"
                await event.respond("🗣️ **Send the Reply:**")
                await event.delete()
            elif data == "clr_rep":
                SETTINGS["keywords"] = []
                SETTINGS["replies"] = []
                db_manager.update_settings(SETTINGS)
                await event.answer("Deleted!")
                await self.send_panel(event, edit=True)
            
            elif data == "add_inv":
                self.invoice_drafts[sid] = {}
                self.user_state[sid] = "inv_client"
                await event.respond("👤 **Enter Client Name:**")
                await event.delete()
            elif data == "set_store":
                self.user_state[sid] = "set_store"
                await event.respond("🏪 **Enter Store Name:**")
                await event.delete()
            
            elif data == "log_set":
                if not self.user: 
                    await event.answer("Userbot not active", alert=True)
                    return
                try:
                    ch = await self.user(CreateChannelRequest("Userbot Logs", "Logs", megagroup=False))
                    SETTINGS["log_channel"] = int(f"-100{ch.chats[0].id}")
                    db_manager.update_settings(SETTINGS)
                    await event.answer("✅ Log Channel Created!")
                except: await event.answer("❌ Error creating channel")

        except Exception as e:
            print(e)

    async def send_panel(self, event, edit=False):
        st = "🟢" if SETTINGS["running"] else "🔴"
        text = (
            f"🎛️ **Ultimate Control Panel**\n"
            f"📡 **Auto-Reply:** {st}\n"
            f"👮 **Spy Mode:** {'✅' if SETTINGS['spy_mode'] else '❌'}\n"
            f"👻 **Ghost Mode:** {'✅' if SETTINGS['ghost_mode'] else '❌'}\n"
            f"💣 **Auto-Save:** {'✅' if SETTINGS['auto_save_destruct'] else '❌'}\n"
            f"🏪 **Store:** {'✅' if SETTINGS['store_name'] else '⚠️'}"
        )
        
        btns = [
            [Button.inline("💬 Reply Settings", b"m_reply"), Button.inline(f"Spy {'ON' if SETTINGS['spy_mode'] else 'OFF'}", b"t_spy")],
            [Button.inline("🏪 Store Menu", b"m_store"), Button.inline(f"Ghost {'ON' if SETTINGS['ghost_mode'] else 'OFF'}", b"t_ghost")],
            [Button.inline("🛠️ Tools & Group", b"m_tools"), Button.inline(f"Save {'ON' if SETTINGS['auto_save_destruct'] else 'OFF'}", b"t_save")],
            [Button.inline(f"Toggle Run {st}", b"t_run"), Button.inline("📢 Set Log", b"log_set")],
            [Button.inline("🔄 Refresh", b"refresh"), Button.inline("❌ Close", b"close")]
        ]
        
        if edit: await event.edit(text, buttons=btns)
        else: await event.respond(text, buttons=btns)

# ------------------------------------------------------------------------------
# 6. WEB SERVER (RENDER KEEP-ALIVE)
# ------------------------------------------------------------------------------
async def web_handler(request):
    return web.Response(text="Bot is Running...")

async def start_web_server():
    app = web.Application()
    app.add_routes([web.get('/', web_handler)])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', Config.PORT)
    await site.start()
    print(f"✅ [Server] Running on port {Config.PORT}")

# ------------------------------------------------------------------------------
# 7. EXECUTION
# ------------------------------------------------------------------------------
if __name__ == '__main__':
    print("🚀 Starting Ultimate Userbot...")
    controller = UserBotController()
    
    loop = asyncio.get_event_loop()
    loop.create_task(start_web_server())
    loop.create_task(controller.start())
    
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
