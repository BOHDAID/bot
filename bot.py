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

# مكتبات السيرفر الوهمي (لإبقاء البوت حياً في Render)
from aiohttp import web

# مكتبات قاعدة البيانات
import pymongo
import certifi

# -----------------------------------------------------------------------------
# استيراد مكتبات التيليجرام (كاملة - سطر بسطر)
# -----------------------------------------------------------------------------
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

# الأنواع (Types)
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

# PDF والعربية
from fpdf import FPDF
import arabic_reshaper
from bidi.algorithm import get_display

# تجاهل التحذيرات
warnings.filterwarnings("ignore")

# -----------------------------------------------------------------------------
# إعدادات الأمان (يتم سحبها من متغيرات البيئة في Render)
# -----------------------------------------------------------------------------
# القيم الافتراضية هنا هي مجرد احتياط، لكن الكود سيعتمد على Environment Variables
API_ID = int(os.environ.get("API_ID", 6))
API_HASH = os.environ.get("API_HASH", "eb06d4abfb49dc3eeb1aeb98ae0f581e")

# التوكن وقاعدة البيانات يتم سحبهما حصراً من البيئة للأمان
BOT_TOKEN = os.environ.get("BOT_TOKEN")
MONGO_URI = os.environ.get("MONGO_URI")

# ملفات محلية (للخطوط والصور فقط)
LOGO_FILE = "saved_store_logo.jpg"
FONT_FILE = "font.ttf"
FONT_URL = "https://github.com/google/fonts/raw/main/ofl/amiri/Amiri-Regular.ttf"

# التحقق من وجود التوكن والداتا
if not BOT_TOKEN:
    print("❌ خطأ: لم يتم العثور على BOT_TOKEN في متغيرات البيئة!")

if not MONGO_URI:
    print("❌ خطأ: لم يتم العثور على MONGO_URI في متغيرات البيئة!")

# -----------------------------------------------------------------------------
# الاتصال بقاعدة البيانات (MongoDB)
# -----------------------------------------------------------------------------
print("⏳ جاري الاتصال بقاعدة البيانات السحابية...")
mongo_client = None
db = None
settings_collection = None

try:
    if MONGO_URI:
        mongo_client = pymongo.MongoClient(MONGO_URI, tlsCAFile=certifi.where())
        db = mongo_client["telegram_userbot_db"]
        settings_collection = db["settings"]
        print("✅ تم الاتصال بقاعدة البيانات بنجاح!")
    else:
        print("⚠️ تحذير: لا يوجد رابط قاعدة بيانات، لن يتم الحفظ السحابي.")
except Exception as e:
    print(f"❌ فشل الاتصال بقاعدة البيانات: {e}")

# -----------------------------------------------------------------------------
# تحميل الخط
# -----------------------------------------------------------------------------
def download_font_if_missing():
    """التحقق من ملف الخط وتحميله إذا لزم الأمر"""
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
            response = requests.get(FONT_URL)
            with open(FONT_FILE, 'wb') as f:
                f.write(response.content)
            print("✅ تم تحميل الخط.")
        except Exception as e:
            print(f"❌ فشل تحميل الخط: {e}")

download_font_if_missing()

# -----------------------------------------------------------------------------
# تشغيل العميل
# -----------------------------------------------------------------------------
# نستخدم try-except لتجنب الانهيار إذا كان التوكن فارغاً أثناء التجربة المحلية
try:
    if BOT_TOKEN:
        bot = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)
    else:
        print("⚠️ لم يتم بدء البوت لعدم وجود توكن.")
        bot = TelegramClient('bot_session', API_ID, API_HASH) # نسخة فارغة لتجنب أخطاء المتغيرات
except Exception as e:
    print(f"❌ فشل تشغيل البوت (تأكد من التوكن): {e}")
    bot = TelegramClient('bot_session', API_ID, API_HASH)

user_client = None 
bio_task = None

# -----------------------------------------------------------------------------
# الإعدادات الافتراضية
# -----------------------------------------------------------------------------
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

# -----------------------------------------------------------------------------
# دوال الحفظ والتحميل (السحابية)
# -----------------------------------------------------------------------------
def save_data():
    """حفظ البيانات في MongoDB"""
    if not settings_collection:
        return
        
    try:
        settings_collection.replace_one(
            {"_id": "bot_config"}, 
            settings, 
            upsert=True
        )
    except Exception as e:
        print(f"❌ خطأ الحفظ السحابي: {e}")

def load_data():
    """تحميل البيانات من MongoDB"""
    global settings
    
    if not settings_collection:
        return

    try:
        data = settings_collection.find_one({"_id": "bot_config"})
        if data:
            for key in data:
                settings[key] = data[key]
            print("☁️ تم تحميل البيانات.")
        else:
            save_data()
            
        # التأكد من القوائم
        if "invoices_archive" not in settings:
            settings["invoices_archive"] = {}
        if "stalk_list" not in settings:
            settings["stalk_list"] = []
        if "typing_watch_list" not in settings:
            settings["typing_watch_list"] = []
            
    except Exception as e:
        print(f"❌ خطأ التحميل السحابي: {e}")

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

# -----------------------------------------------------------------------------
# 🧾 نظام الفواتير (إصلاح اللغة العربية)
# -----------------------------------------------------------------------------
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
        
        # إعداد الخط
        font_name = 'Helvetica'
        is_arabic = False
        
        try:
            if os.path.exists(FONT_FILE):
                if os.path.getsize(FONT_FILE) > 1000:
                    pdf.add_font('Amiri', '', FONT_FILE, uni=True)
                    font_name = 'Amiri'
                    is_arabic = True
        except:
            pass
        
        pdf.set_font(font_name, '', 12)

        # دالة مساعدة للنص
        def t(ar_text, en_text):
            if is_arabic:
                return fix_text(str(ar_text))
            else:
                return str(en_text)

        # 1. الرأس (الأزرق)
        pdf.set_fill_color(44, 62, 80)
        pdf.rect(0, 0, 210, 40, 'F')
        
        pdf.set_text_color(255, 255, 255)
        pdf.set_font_size(24)
        pdf.set_xy(10, 10)
        
        title_txt = "INVOICE / فاتورة"
        if not is_arabic:
            title_txt = "INVOICE"
            
        pdf.cell(0, 10, text=fix_text(title_txt) if is_arabic else title_txt, border=0, align='C')
        
        pdf.set_font_size(10)
        pdf.set_xy(10, 22)
        pdf.cell(0, 10, text=f"#{code_16}", align='C')

        if os.path.exists(LOGO_FILE):
            pdf.image(LOGO_FILE, x=170, y=5, w=30)

        pdf.ln(30)

        # 2. المعلومات
        pdf.set_text_color(0, 0, 0)
        pdf.set_font_size(12)
        
        store_n = settings.get("store_name", "Store")
        store_u = settings.get("store_user", "")
        client_n = data.get('client_name', 'Client')
        date_s = datetime.datetime.now().strftime("%Y-%m-%d")
        
        align_pos = 'R' if is_arabic else 'L'
        
        pdf.set_fill_color(236, 240, 241)
        pdf.cell(0, 10, text=t("تفاصيل الفاتورة", "Details"), ln=True, align=align_pos, fill=True)
        
        # طباعة الأسطر (دمج النصوص لتفادي الانعكاس)
        line1 = f"Store: {store_n}"
        pdf.cell(190, 7, text=t(line1, line1), ln=True, align=align_pos)
        
        line2 = f"User: {store_u}"
        pdf.cell(190, 7, text=t(line2, line2), ln=True, align=align_pos)
        
        line3 = f"Client: {client_n}"
        pdf.cell(190, 7, text=t(line3, line3), ln=True, align=align_pos)
        
        line4 = f"Date: {date_s}"
        pdf.cell(190, 7, text=t(line4, line4), ln=True, align=align_pos)
        
        pdf.ln(10)

        # 3. الجدول
        pdf.set_fill_color(44, 62, 80)
        pdf.set_text_color(255, 255, 255)
        pdf.set_draw_color(0, 0, 0)
        
        headers = ["المنتج", "العدد", "الضمان", "السعر"]
        en_headers = ["Product", "Qty", "Warranty", "Price"]
        w = [80, 25, 45, 40]
        
        if is_arabic:
            for i in reversed(range(4)):
                pdf.cell(w[i], 10, text=t(headers[i], ""), border=1, align='C', fill=True)
        else:
            for i in range(4):
                pdf.cell(w[i], 10, text=en_headers[i], border=1, align='C', fill=True)
                
        pdf.ln()
        
        # البيانات
        pdf.set_text_color(0, 0, 0)
        
        v_prod = str(data.get('product', '-'))
        v_count = str(data.get('count', '1'))
        v_warr = str(data.get('warranty', '-'))
        v_price = str(data.get('price', '0'))
        
        if is_arabic:
            # طباعة القيم العربية
            pdf.cell(w[3], 10, text=t(v_price, ""), border=1, align='C')
            pdf.cell(w[2], 10, text=t(v_warr, ""), border=1, align='C')
            pdf.cell(w[1], 10, text=t(v_count, ""), border=1, align='C')
            pdf.cell(w[0], 10, text=t(v_prod, ""), border=1, align='R')
        else:
            pdf.cell(w[0], 10, text=v_prod, border=1, align='L')
            pdf.cell(w[1], 10, text=v_count, border=1, align='C')
            pdf.cell(w[2], 10, text=v_warr, border=1, align='C')
            pdf.cell(w[3], 10, text=v_price, border=1, align='C')
            
        pdf.ln(20)
        
        # 4. الإجمالي
        pdf.set_font_size(16)
        pdf.set_text_color(44, 62, 80)
        
        tot = f"TOTAL: {v_price}"
        pdf.cell(0, 10, text=t(tot, tot), ln=True, align='C')
        
        # 5. التذييل
        pdf.set_y(-30)
        pdf.set_font_size(10)
        pdf.set_text_color(100, 100, 100)
        
        footer = "شكراً لتعاملكم معنا"
        pdf.cell(0, 10, text=t(footer, "Thank You"), align='C')

        pdf.output(filename)
        return True
    except Exception as e:
        print(f"PDF Error: {e}")
        return False

# -----------------------------------------------------------------------------
# الوظائف الخلفية
# -----------------------------------------------------------------------------
async def bio_loop():
    print("✅ بدء خدمة البايو التلقائي...")
    while True:
        if settings["auto_bio"]:
            if user_client:
                try:
                    now = datetime.datetime.now().strftime("%I:%M %p")
                    bio_text = settings["bio_template"].replace("%TIME%", now)
                    await user_client(UpdateProfileRequest(about=bio_text))
                except Exception:
                    pass
        
        await asyncio.sleep(60)

async def get_log_channel():
    if not settings["log_channel"]:
        return None
    
    if not user_client:
        return None
        
    try:
        entity = await user_client.get_entity(settings["log_channel"])
        return entity
    except:
        return None

# -----------------------------------------------------------------------------
# الهاندلرز (التفصيل)
# -----------------------------------------------------------------------------

# كاشف التعديل
async def message_edited_handler(event):
    if not settings["spy_mode"]:
        return
    
    if not event.is_private:
        return 
    
    try:
        log_ch = await get_log_channel()
        if not log_ch:
            return

        sender = await event.get_sender()
        name = getattr(sender, 'first_name', 'Unknown')
        link = f"tg://user?id={event.chat_id}"
        
        msg = (
            f"✏️ **تم رصد تعديل (في الخاص)**\n"
            f"👤 **بواسطة:** {name}\n"
            f"🔗 **الرابط:** [اضغط هنا]({link})\n"
            f"📝 **النص الجديد:**\n`{event.raw_text}`"
        )
        await user_client.send_message(log_ch, msg, link_preview=False)
    except:
        pass

# كاشف الحذف
async def message_deleted_handler(event):
    if not settings["spy_mode"]:
        return
    
    try:
        log_ch = await get_log_channel()
        if not log_ch:
            return

        for msg_id in event.deleted_ids:
            if msg_id in message_cache:
                data = message_cache[msg_id]
                
                if data.get('is_private'):
                    msg = (
                        f"🗑️ **تم رصد حذف (من الخاص)**\n"
                        f"👤 **المرسل:** {data['sender']}\n"
                        f"📝 **النص المحذوف:**\n`{data['text']}`"
                    )
                    await user_client.send_message(log_ch, msg)
    except:
        pass

# المراقب الرئيسي
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
            
            # تنظيف الذاكرة
            if len(message_cache) > 2000:
                keys_list = list(message_cache.keys())
                oldest_keys = keys_list[:500]
                for k in oldest_keys:
                    del message_cache[k]

        # الشبح
        if settings["ghost_mode"]:
            if not event.out:
                if event.is_private:
                    if settings["log_channel"]:
                        await event.forward_to(settings["log_channel"])
                        sender_n = message_cache.get(event.id, {}).get('sender', 'Unknown')
                        await user_client.send_message(settings["log_channel"], f"👻 **شبح: من {sender_n}**")

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
            if ttl:
                if ttl > 0:
                    if not event.out:
                        if event.media:
                            try:
                                path = await event.download_media()
                                caption = f"💣 **تدمير ذاتي** ({ttl}ث)"
                                
                                await user_client.send_file("me", path, caption=caption)
                                
                                if settings["log_channel"]:
                                    await user_client.send_file(settings["log_channel"], path, caption=caption)
                                
                                os.remove(path)
                            except:
                                pass

        # الرد التلقائي
        if settings["running"]:
            if is_working_hour():
                if not event.out:
                    text = event.raw_text.strip()
                    
                    if any(k in text for k in settings["keywords"]):
                        last_t = user_cooldowns.get(event.sender_id, 0)
                        
                        if time.time() - last_t > 600:
                            async with user_client.action(event.chat_id, 'typing'):
                                await asyncio.sleep(settings["typing_delay"])
                                reply = random.choice(settings["replies"])
                                await event.reply(reply)
                            
                            user_cooldowns[event.sender_id] = time.time()

        # منع الروابط
        if settings["anti_link_group"]:
            if event.is_group or event.is_channel:
                if not event.out:
                    txt = event.raw_text.lower()
                    if "http" in txt or "t.me" in txt or ".com" in txt:
                        try:
                            await event.delete()
                        except:
                            pass

    except Exception as e:
        print(f"Main Error: {e}")

# التحديثات
@bot.on(events.UserUpdate)
async def user_update_handler(event):
    if not user_client:
        return
    
    try:
        # الأونلاين
        if event.user_id in settings["stalk_list"]:
            if event.online:
                await user_client.send_message("me", f"🚨 **المراقب {event.user_id} متصل الآن!**")
        
        # الكتابة
        if event.user_id in settings["typing_watch_list"]:
            if event.typing:
                await user_client.send_message("me", f"✍️ **المراقب {event.user_id} يكتب...**")
    except:
        pass

# -----------------------------------------------------------------------------
# الواجهة
# -----------------------------------------------------------------------------
async def safe_edit(event, text, buttons):
    try:
        await event.edit(text, buttons=buttons)
    except MessageIdInvalidError:
        await event.respond(text, buttons=buttons)
    except Exception:
        pass

async def show_main_panel(event, edit=False):
    st = "🟢" if settings["running"] else "🔴"
    
    msg = (
        f"🎛️ **لوحة التحكم السحابية (الكاملة)**\n"
        f"ـــــــــــــــــــــــــــــــــــــــــــــــــ\n"
        f"📡 **الحالة:** {st}\n"
        f"👮 **تجسس:** {'✅' if settings['spy_mode'] else '❌'}\n"
        f"👻 **شبح:** {'✅' if settings['ghost_mode'] else '❌'}\n"
        f"🧾 **متجر:** {'✅' if settings['store_name'] else '⚠️'}\n"
        f"ـــــــــــــــــــــــــــــــــــــــــــــــــ"
    )
    
    btns = [
        [
            Button.inline("🕵️ التجسس والمراقبة", data=b"menu_spy"),
            Button.inline("👻 الشبح والإخفاء", data=b"menu_ghost")
        ],
        [
            Button.inline("🏪 المتجر والفواتير", data=b"menu_store"),
            Button.inline("🛠️ الأدوات والخدمات", data=b"menu_tools")
        ],
        [
            Button.inline("🎤 الوسيط الصوتي", data=b"menu_voice"),
            Button.inline("🛡️ إدارة المجموعات", data=b"menu_group")
        ],
        [
            Button.inline(f"تشغيل/إيقاف {st}", data=b"toggle_run"),
            Button.inline("📢 قناة السجل", data=b"log_settings")
        ],
        [
            Button.inline("🔄 تحديث", data=b"refresh_panel"),
            Button.inline("❌ إغلاق", data=b"close_panel")
        ]
    ]
    
    if edit:
        await safe_edit(event, msg, btns)
    else:
        await event.respond(msg, buttons=btns)

# القوائم الفرعية
async def show_store_menu(event):
    btns = [
        [
            Button.inline("➕ فاتورة جديدة", data=b"start_fast_invoice"),
            Button.inline("🔎 بحث (PDF)", data=b"search_invoice")
        ],
        [
            Button.inline("⏰ تذكير سداد", data=b"tool_payment_remind"),
            Button.inline("⚙️ إعدادات", data=b"store_settings")
        ],
        [
            Button.inline("🔙 رجوع", data=b"refresh_panel")
        ]
    ]
    await safe_edit(event, "🏪 **المتجر:**", btns)

async def show_spy_menu(event):
    btns = [
        [
            Button.inline(f"تجسس (خاص) {'✅' if settings['spy_mode'] else '❌'}", data=b"toggle_spy"),
            Button.inline(f"حفظ الموقوت {'✅' if settings['auto_save_destruct'] else '❌'}", data=b"toggle_destruct")
        ],
        [
            Button.inline("👁️ راصد الأونلاين", data=b"tool_stalk"),
            Button.inline("✍️ كاشف الكتابة", data=b"tool_watch_type")
        ],
        [
            Button.inline("🔙 رجوع", data=b"refresh_panel")
        ]
    ]
    await safe_edit(event, "🕵️ **التجسس:**", btns)

async def show_ghost_menu(event):
    btns = [
        [
            Button.inline(f"شبح تام {'✅' if settings['ghost_mode'] else '❌'}", data=b"toggle_ghost"),
            Button.inline(f"وهم الأوفلاين {'✅' if settings['fake_offline'] else '❌'}", data=b"toggle_fake_off")
        ],
        [
            Button.inline(f"لا تكتب {'✅' if settings['anti_typing'] else '❌'}", data=b"toggle_anti_type"),
            Button.inline("❄️ تجميد الظهور", data=b"tool_freeze_last")
        ],
        [
            Button.inline("🔙 رجوع", data=b"refresh_panel")
        ]
    ]
    await safe_edit(event, "👻 **الشبح:**", btns)

async def show_tools_menu(event):
    btns = [
        [
            Button.inline("📦 ضغط Zip", data=b"tool_zip"),
            Button.inline("📄 صنع PDF", data=b"tool_pdf")
        ],
        [
            Button.inline("📥 تحميل", data=b"tool_download"),
            Button.inline("🌐 فحص IP", data=b"tool_ip")
        ],
        [
            Button.inline("📶 Ping", data=b"tool_ping"),
            Button.inline("🔗 اختصار", data=b"tool_short")
        ],
        [
            Button.inline("📟 تيرمينال", data=b"tool_shell"),
            Button.inline("🔙 رجوع", data=b"refresh_panel")
        ]
    ]
    await safe_edit(event, "🛠️ **الأدوات:**", btns)

async def show_voice_menu(event):
    btns = [
        [
            Button.inline("🔇 عادي", data=b"voice_mode_none")
        ],
        [
            Button.inline("🚗 سيارة", data=b"voice_mode_car"),
            Button.inline("🌧️ مطر", data=b"voice_mode_rain")
        ],
        [
            Button.inline("🔙 رجوع", data=b"refresh_panel")
        ]
    ]
    await safe_edit(event, "🎤 **الوسيط الصوتي:**", btns)

async def show_group_menu(event):
    btns = [
        [
            Button.inline("🧹 تنظيف المحذوفين", data=b"group_mass_clean"),
            Button.inline("🔁 تنظيف رسائلي", data=b"group_purge_me")
        ],
        [
            Button.inline("👥 استنساخ (صادق)", data=b"group_clone"),
            Button.inline("👮 مشرفين", data=b"group_admins")
        ],
        [
            Button.inline(f"منع الروابط {'✅' if settings['anti_link_group'] else '❌'}", data=b"toggle_anti_link"),
            Button.inline("🔙 رجوع", data=b"refresh_panel")
        ]
    ]
    await safe_edit(event, "🛡️ **إدارة المجموعات:**", btns)

# -----------------------------------------------------------------------------
# Callback Handler
# -----------------------------------------------------------------------------
@bot.on(events.CallbackQuery)
async def callback_handler(event):
    try:
        data = event.data.decode()
        sender_id = event.sender_id
        
        # التنقل
        if data == "refresh_panel":
            await show_main_panel(event, edit=True)
        elif data == "close_panel":
            await event.delete()
        elif data == "menu_spy":
            await show_spy_menu(event)
        elif data == "menu_ghost":
            await show_ghost_menu(event)
        elif data == "menu_store":
            await show_store_menu(event)
        elif data == "menu_tools":
            await show_tools_menu(event)
        elif data == "menu_voice":
            await show_voice_menu(event)
        elif data == "menu_group":
            await show_group_menu(event)

        # التبديل
        elif data == "toggle_run":
            settings["running"] = not settings["running"]
            save_data()
            await show_main_panel(event, edit=True)
        elif data == "toggle_spy":
            settings["spy_mode"] = not settings["spy_mode"]
            save_data()
            await show_spy_menu(event)
        elif data == "toggle_ghost":
            settings["ghost_mode"] = not settings["ghost_mode"]
            save_data()
            await show_ghost_menu(event)
        elif data == "toggle_fake_off":
            settings["fake_offline"] = not settings["fake_offline"]
            save_data()
            await show_ghost_menu(event)
        elif data == "toggle_anti_type":
            settings["anti_typing"] = not settings["anti_typing"]
            save_data()
            await show_ghost_menu(event)
        elif data == "toggle_destruct":
            settings["auto_save_destruct"] = not settings["auto_save_destruct"]
            save_data()
            await show_spy_menu(event)
        elif data == "toggle_anti_link":
            settings["anti_link_group"] = not settings["anti_link_group"]
            save_data()
            await show_group_menu(event)

        # الأوامر
        elif data == "tool_stalk":
            user_state[sender_id] = "wait_stalk_id"
            await event.respond("👁️ أرسل اليوزر:")
            await event.delete()
        elif data == "tool_watch_type":
            user_state[sender_id] = "wait_type_id"
            await event.respond("✍️ أرسل اليوزر:")
            await event.delete()
        elif data == "tool_freeze_last":
            if user_client:
                await user_client(UpdateStatusRequest(offline=True))
                await event.answer("تم التجميد")
        elif data == "store_settings":
            user_state[sender_id] = "set_store_name"
            await event.respond("🏪 أرسل الاسم:")
            await event.delete()
        elif data == "start_fast_invoice":
            invoice_drafts[sender_id] = {}
            user_state[sender_id] = "inv_client"
            await event.respond("👤 اسم العميل:")
            await event.delete()
        elif data == "search_invoice":
            user_state[sender_id] = "wait_search_inv"
            await event.respond("🔎 الكود:")
            await event.delete()
        elif data == "tool_payment_remind":
            user_state[sender_id] = "wait_remind_user"
            await event.respond("⏰ اليوزر:")
            await event.delete()
        
        elif data == "tool_ping":
            s = time.time()
            await user_client.send_message("me", "Pong")
            e = time.time()
            await event.answer(f"{round((e-s)*1000)}ms", alert=True)
        elif data == "tool_ip":
            user_state[sender_id] = "wait_ip"
            await event.respond("🌐 IP:")
            await event.delete()
        elif data == "tool_short":
            user_state[sender_id] = "wait_short_link"
            await event.respond("🔗 الرابط:")
            await event.delete()
        elif data == "tool_download":
            user_state[sender_id] = "wait_dl_link"
            await event.respond("📥 الرابط:")
            await event.delete()
        elif data == "tool_shell":
            user_state[sender_id] = "wait_shell"
            await event.respond("📟 الأمر:")
            await event.delete()
        elif data == "tool_zip":
            user_state[sender_id] = "wait_zip_files"
            temp_data[sender_id] = []
            await event.respond("📦 الملفات:")
            await event.delete()
        elif data == "tool_pdf":
            user_state[sender_id] = "wait_pdf_imgs"
            temp_data[sender_id] = []
            await event.respond("📄 الصور:")
            await event.delete()
        elif data.startswith("voice_mode_"):
            user_state[sender_id] = "voice_wait_user"
            temp_data[sender_id] = {"noise": data.split("_")[2]}
            await event.respond("1️⃣ الضحية:")
            await event.delete()
        
        elif data == "group_mass_clean":
            await event.respond("⏳")
            asyncio.create_task(clean_deleted_accounts(event.chat_id))
        elif data == "group_purge_me":
            await event.respond("⏳")
            asyncio.create_task(purge_my_msgs(event.chat_id))
        elif data == "group_clone":
            user_state[sender_id] = "wait_clone_src"
            await event.respond("👥 المصدر:")
            await event.delete()
        elif data == "group_admins":
            await list_admins(event)
        
        elif data == "log_settings":
            await event.respond(f"السجل: {settings.get('log_channel')}", buttons=[[Button.inline("تعيين تلقائي", b"set_log_auto")]])
        elif data == "set_log_auto":
            try:
                ch = await user_client(CreateChannelRequest("Logs", "Logs", megagroup=False))
                settings["log_channel"] = int(f"-100{ch.chats[0].id}")
                save_data()
                await event.answer("✅")
            except:
                await event.answer("❌", alert=True)
        
        elif data == "login":
            user_state[sender_id] = "waiting_session"
            await event.respond("📩 السيزون:")
            await event.delete()
        elif data == "logout":
            settings["session"] = None
            save_data()
            await event.edit("✅")
            await show_login_button(event)

    except:
        traceback.print_exc()

# -----------------------------------------------------------------------------
# Input Handler
# -----------------------------------------------------------------------------
@bot.on(events.NewMessage)
async def input_handler(event):
    if event.sender_id == (await bot.get_me()).id:
        return
    
    sender_id = event.sender_id
    state = user_state.get(sender_id)
    text = event.text.strip()

    # 1. Login
    if state == "waiting_session":
        try:
            c = TelegramClient(StringSession(text), API_ID, API_HASH)
            await c.connect()
            if await c.is_user_authorized():
                settings["session"] = text
                save_data()
                await c.disconnect()
                await event.reply("✅")
                await start_user_bot()
                await show_main_panel(event)
            else:
                await event.reply("❌")
        except:
            await event.reply("❌")
        user_state[sender_id] = None

    # 2. Store
    elif state == "set_store_name":
        settings["store_name"] = text
        save_data()
        await event.reply("✅")
        user_state[sender_id] = None
    elif state == "inv_client":
        invoice_drafts[sender_id]['client_name'] = text
        user_state[sender_id] = "inv_prod"
        await event.reply("🛍️ المنتج:")
    elif state == "inv_prod":
        invoice_drafts[sender_id]['product'] = text
        user_state[sender_id] = "inv_count"
        await event.reply("🔢 العدد:")
    elif state == "inv_count":
        invoice_drafts[sender_id]['count'] = text
        user_state[sender_id] = "inv_price"
        await event.reply("💰 السعر:")
    elif state == "inv_price":
        invoice_drafts[sender_id]['price'] = text
        user_state[sender_id] = "inv_warranty"
        await event.reply("🛡️ الضمان:")
    elif state == "inv_warranty":
        invoice_drafts[sender_id]['warranty'] = text
        code = ''.join([str(random.randint(0,9)) for _ in range(16)])
        settings["invoices_archive"][code] = invoice_drafts[sender_id]
        save_data()
        
        fn = f"Invoice_{code}.pdf"
        if create_invoice_pdf(invoice_drafts[sender_id], code, fn):
            await event.client.send_file(event.chat_id, fn, caption=f"🧾 **تم**\n🔐 `{code}`")
            os.remove(fn)
        else:
            await event.reply("❌ PDF Error")
        
        user_state[sender_id] = None
        await show_store_menu(event)

    # 3. Search
    elif state == "wait_search_inv":
        d = settings["invoices_archive"].get(text)
        if d:
            fn = f"Copy_{text}.pdf"
            if create_invoice_pdf(d, text, fn):
                await event.client.send_file(event.chat_id, fn, caption="📂 Copy")
                os.remove(fn)
            else:
                await event.reply("❌")
        else:
            await event.reply("❌")
        user_state[sender_id] = None

    # 4. Reminder
    elif state == "wait_remind_user":
        try:
            await user_client.send_message(text, "👋 Payment Reminder.")
            await event.reply("✅")
        except:
            await event.reply("❌")
        user_state[sender_id] = None

    # 5. Voice
    elif state == "voice_wait_user":
        try:
            ent = await user_client.get_entity(text)
            temp_data[sender_id]['target'] = ent.id
            user_state[sender_id] = "voice_wait_record"
            await event.reply("2️⃣ Voice:")
        except:
            await event.reply("❌")
    elif state == "voice_wait_record":
        if event.voice or event.audio:
            tgt = temp_data[sender_id]['target']
            async with user_client.action(tgt, 'record-audio'):
                await asyncio.sleep(3)
            p = await event.download_media()
            await user_client.send_file(tgt, p, voice_note=True)
            os.remove(p)
            await event.reply("✅")
            user_state[sender_id] = None
        else:
            await event.reply("⚠️")

    # 6. Tools
    elif state == "wait_stalk_id":
        try:
            ent = await user_client.get_input_entity(text)
            settings["stalk_list"].append(ent.user_id)
            save_data()
            await event.reply("✅")
        except:
            await event.reply("❌")
        user_state[sender_id] = None
    elif state == "wait_type_id":
        try:
            ent = await user_client.get_input_entity(text)
            settings["typing_watch_list"].append(ent.user_id)
            await event.reply("✅")
        except:
            await event.reply("❌")
        user_state[sender_id] = None

    elif state == "wait_ip":
        try:
            r = requests.get(f"http://ip-api.com/json/{text}").json()
            await event.reply(f"🌍 {r['country']}")
        except:
            await event.reply("❌")
        user_state[sender_id] = None
    elif state == "wait_short_link":
        try:
            res = requests.get(f"https://tinyurl.com/api-create.php?url={text}").text
            await event.reply(f"🔗 {res}")
        except:
            await event.reply("❌")
        user_state[sender_id] = None
    elif state == "wait_shell":
        try:
            res = os.popen(text).read()
            await event.reply(f"Output:\n`{res[:4000]}`")
        except:
            await event.reply("❌")
        user_state[sender_id] = None
    elif state == "wait_zip_files":
        if text == "تم":
            if temp_data.get(sender_id):
                zname = "archive.zip"
                zf = zipfile.ZipFile(zname, 'w')
                for f in temp_data[sender_id]:
                    zf.write(f)
                    os.remove(f)
                zf.close()
                await user_client.send_file("me", zname)
                os.remove(zname)
                await event.reply("✅")
            user_state[sender_id] = None
        elif event.media:
            p = await event.download_media()
            if sender_id not in temp_data:
                temp_data[sender_id] = []
            temp_data[sender_id].append(p)
            await event.reply("📥")

    # 7. Clone (Real Adder)
    elif state == "wait_clone_src":
        if not user_client:
            await event.reply("⚠️")
            return
        msg = await event.reply("⏳...")
        try:
            if "t.me" in text:
                try:
                    await user_client(functions.channels.JoinChannelRequest(text))
                except:
                    pass
            src = await user_client.get_entity(text)
            parts = await user_client.get_participants(src, aggressive=True)
            valid = [u for u in parts if not u.bot and not u.deleted]
            if not valid:
                await msg.edit("❌ 0")
                user_state[sender_id] = None
                return
            temp_data[sender_id] = {'scraped': valid}
            await msg.edit(f"✅ {len(valid)}. Count?")
            user_state[sender_id] = "wait_clone_count"
        except Exception as e:
            await msg.edit(f"❌ {e}")
            user_state[sender_id] = None

    elif state == "wait_clone_count":
        try:
            temp_data[sender_id]['limit'] = int(text)
            await event.reply("3️⃣ Target:")
            user_state[sender_id] = "wait_clone_dest"
        except:
            await event.reply("❌")

    elif state == "wait_clone_dest":
        users = temp_data[sender_id]['scraped']
        limit = temp_data[sender_id]['limit']
        msg = await event.reply(f"🚀 Adding {limit} (Verified)...")
        asyncio.create_task(add_members_task(user_client, text, users, limit, msg))
        user_state[sender_id] = None

# ==============================================================================
# دالة النقل الصادق (Real Adder)
# ==============================================================================
async def add_members_task(client, dest, users, limit, msg):
    try:
        dest_ent = await client.get_entity(dest)
        success = 0
        tried = 0
        
        print(f"--- ADDING: {limit} ---")
        
        while success < limit and tried < len(users):
            u = users[tried]
            tried += 1
            
            if u.bot or u.deleted:
                continue

            try:
                print(f"Try {u.id}", end=" ")
                # 1. الإضافة
                await client(InviteToChannelRequest(dest_ent, [u]))
                
                # 2. التحقق
                await asyncio.sleep(2)
                try:
                    await client.get_permissions(dest_ent, u)
                    success += 1
                    print("✅ OK")
                except UserNotParticipantError:
                    print("❌ Privacy")
                    continue
                
                if success % 3 == 0:
                    await msg.edit(f"🔄 {success}/{limit}")
                
                await asyncio.sleep(random.randint(6, 12))
                
            except FloodWaitError as e:
                print(f"⚠️ {e.seconds}s")
                await asyncio.sleep(e.seconds)
            except Exception as e:
                if "maximum number" in str(e):
                    await msg.edit("🛑 Limit")
                    break
                print(f"❌ {e}")
        
        await msg.edit(f"🏁 Done: {success}")
        
    except Exception as e:
        await msg.edit(f"❌ {e}")

# ==============================================================================
# أدوات المجموعات
# ==============================================================================
async def clean_deleted_accounts(chat_id):
    if not user_client:
        return
    users = await user_client.get_participants(chat_id)
    c = 0
    for u in users:
        if u.deleted:
            try:
                await user_client(EditBannedRequest(chat_id, u.id, ChatBannedRights(until_date=None, view_messages=True)))
                c += 1
            except:
                pass
    await user_client.send_message(chat_id, f"🧹 {c}")

async def purge_my_msgs(chat_id):
    if not user_client:
        return
    me = await user_client.get_me()
    msgs = []
    async for m in user_client.iter_messages(chat_id, from_user=me, limit=100):
        msgs.append(m.id)
    await user_client.delete_messages(chat_id, msgs)

async def list_admins(event):
    if not user_client:
        return
    ads = await user_client.get_participants(event.chat_id, filter=ChannelParticipantsAdmins)
    text = "👮\n" + "\n".join([f"- {a.first_name}" for a in ads])
    await event.reply(text)

# ==============================================================================
# ☁️ إعدادات السيرفر الوهمي (Render Keep-Alive)
# ==============================================================================
async def web_page(request):
    return web.Response(text="Bot Running on Cloud!")

async def start_web_server():
    app = web.Application()
    app.add_routes([web.get('/', web_page)])
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"✅ Web Server running on {port}")

# ==============================================================================
# البداية
# ==============================================================================
@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    load_data()
    if settings["session"]:
        await start_user_bot()
        await show_main_panel(event)
    else:
        await show_login_button(event)

async def show_login_button(event):
    await event.respond("👋", buttons=[[Button.inline("➕ Login", b"login")]])

async def start_user_bot():
    global user_client, bio_task
    if not settings["session"]:
        return
    try:
        if user_client:
            await user_client.disconnect()
        user_client = TelegramClient(StringSession(settings["session"]), API_ID, API_HASH)
        await user_client.connect()
        
        user_client.add_event_handler(main_watcher_handler, events.NewMessage())
        user_client.add_event_handler(message_edited_handler, events.MessageEdited())
        user_client.add_event_handler(message_deleted_handler, events.MessageDeleted())
        user_client.add_event_handler(user_update_handler, events.UserUpdate())
        
        if bio_task:
            bio_task.cancel()
        bio_task = asyncio.create_task(bio_loop())
        print("✅ Started")
    except:
        pass

print("Bot Running (FULL CLOUD + SERVER)...")
loop = asyncio.get_event_loop()
loop.create_task(start_web_server())
bot.run_until_disconnected()