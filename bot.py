# ------------------------------------------------------------------------------
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
    await event.edit("🛡️ **المجموعات:**", buttons=btns)v# ------------------------------------------------------------------------------
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
    bot.run_until_disconnected()# ------------------------------------------------------------------------------
# معالج الأزرار (Callbacks) - (تم إصلاح خطأ الاسم)
# ------------------------------------------------------------------------------
@bot.on(events.CallbackQuery)
async def callback_handler(event):
    try:
        # هنا كان الخطأ: تم توحيد الاسم ليصبح data
        data = event.data.decode()
        sid = event.sender_id
        
        # التنقل
        if data == "refresh_panel": 
            try: await show_main_panel(event, edit=True)
            except MessageNotModifiedError: await event.answer("✅ اللوحة محدثة بالفعل")
        
        elif data == "close_panel": await event.delete()
        elif data == "menu_reply": await show_reply_menu(event)
        elif data == "menu_spy": await show_spy_menu(event) # تم الإصلاح هنا
        elif data == "menu_ghost": await show_ghost_menu(event)
        elif data == "menu_store": await show_store_menu(event)
        elif data == "menu_tools": await show_tools_menu(event)
        elif data == "menu_group": await show_group_menu(event)
        elif data == "menu_voice": await show_voice_menu(event)
        
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
            user_state[sid] = "wait_stalk_id"
            await event.respond("👁️ **أرسل المعرف (User/ID) للمراقبة:**")
            await event.delete()
        elif data == "tool_watch_type": 
            user_state[sid] = "wait_type_id"
            await event.respond("✍️ **أرسل المعرف لمراقبة الكتابة:**")
            await event.delete()
        elif data == "tool_freeze_last": 
            if user_client: await user_client(UpdateStatusRequest(offline=True)); await event.answer("❄️ تم تجميد الظهور")
        
        elif data == "store_settings": 
            user_state[sid] = "set_store_name"
            await event.respond("🏪 **أرسل اسم المتجر الجديد:**")
            await event.delete()
        elif data == "start_fast_invoice": 
            invoice_drafts[sid] = {}
            user_state[sid] = "inv_client"
            await event.respond("👤 **أرسل اسم العميل:**")
            await event.delete()
        elif data == "search_invoice": 
            user_state[sid] = "wait_search_inv"
            await event.respond("🔎 **أرسل كود الفاتورة:**")
            await event.delete()
        elif data == "tool_payment_remind": 
            user_state[sid] = "wait_remind_user"
            await event.respond("⏰ **أرسل معرف العميل للتذكير:**")
            await event.delete()
        
        elif data == "tool_ping": 
            s=time.time()
            await user_client.send_message("me", "Pong")
            await event.answer(f"⚡ {round((time.time()-s)*1000)}ms", alert=True)
        
        elif data == "tool_ip": 
            user_state[sid] = "wait_ip"
            await event.respond("🌐 **أرسل الـ IP:**")
            await event.delete()
        elif data == "tool_short": 
            user_state[sid] = "wait_short_link"
            await event.respond("🔗 **أرسل الرابط لاختصاره:**")
            await event.delete()
        elif data == "tool_download": 
            user_state[sid] = "wait_dl_link"
            await event.respond("📥 **أرسل رابط التحميل:**")
            await event.delete()
        elif data == "tool_shell": 
            user_state[sid] = "wait_shell"
            await event.respond("📟 **أرسل الأمر (Terminal):**")
            await event.delete()
        elif data == "tool_zip": 
            user_state[sid] = "wait_zip_files"
            temp_data[sid] = []
            await event.respond("📦 **أرسل الملفات، ثم اكتب 'تم':**")
            await event.delete()
        elif data == "tool_pdf": 
            user_state[sid] = "wait_pdf_imgs"
            temp_data[sid] = []
            await event.respond("📄 **أرسل الصور، ثم اكتب 'تم':**")
            await event.delete()
        
        elif data.startswith("voice_mode_"):
            mode = data.split("_")[2]
            user_state[sid] = "voice_wait_user"
            temp_data[sid] = {"noise": mode}
            await event.respond(f"🎤 **الوضع: {mode}**\n1️⃣ أرسل معرف الضحية:")
            await event.delete()
        
        elif data == "group_mass_clean": 
            await event.respond("⏳ جاري تنظيف الحسابات المحذوفة...")
            asyncio.create_task(clean_deleted_accounts(event.chat_id))
        elif data == "group_purge_me": 
            await event.respond("⏳ جاري حذف رسائلك...")
            asyncio.create_task(purge_my_msgs(event.chat_id))
        elif data == "group_clone": 
            user_state[sid] = "wait_clone_src"
            await event.respond("👥 **أرسل رابط المجموعة المصدر:**")
            await event.delete()
        elif data == "group_admins": 
            await list_admins(event)
        
        elif data == "log_settings": 
            await event.respond(f"السجل الحالي: {settings.get('log_channel')}", buttons=[[Button.inline("إنشاء قناة تلقائياً", b"set_log_auto")]])
        elif data == "set_log_auto": 
            try: 
                ch = await user_client(CreateChannelRequest("Userbot Logs", "Logs", megagroup=False))
                settings["log_channel"] = int(f"-100{ch.chats[0].id}")
                save_data()
                await event.answer("✅ تم الإنشاء والتعيين!")
            except: await event.answer("❌ حدث خطأ", alert=True)
        
        elif data == "login": 
            user_state[sid] = "login"
            await event.respond("📩 **أرسل كود الجلسة (String Session):**")
            await event.delete()
        elif data == "logout": 
            settings["session"] = None
            save_data()
            await event.edit("✅ تم تسجيل الخروج")
            await show_login_button(event)
        
        # أوامر الردود الجديدة
        elif data == "add_kw":
            user_state[sid] = "add_keyword"
            await event.respond("🔑 **أرسل الكلمة المفتاحية:**")
            await event.delete()
        elif data == "add_rep":
            user_state[sid] = "add_reply"
            await event.respond("🗣️ **أرسل الرد:**")
            await event.delete()
        elif data == "clr_rep":
            settings["keywords"] = []
            settings["replies"] = []
            save_data()
            await event.answer("🗑️ تم الحذف", alert=True)
            await show_reply_menu(event)

    except MessageNotModifiedError:
        pass # تجاهل خطأ عدم التغيير
    except Exception:
        traceback.print_exc()

# ------------------------------------------------------------------------------
# معالج النصوص (Input Handler)
# ------------------------------------------------------------------------------
@bot.on(events.NewMessage)
async def input_handler(event):
    if event.sender_id == (await bot.get_me()).id: return
    sid = event.sender_id; state = user_state.get(sid); text = event.text.strip()

    # 1. تسجيل الدخول
    if state == "login":
        try:
            c = TelegramClient(StringSession(text), API_ID, API_HASH); await c.connect()
            if await c.is_user_authorized(): 
                settings["session"] = text; save_data(); await c.disconnect()
                await event.reply("✅ تم الدخول بنجاح!"); await start_user_bot(); await show_main_panel(event)
            else: await event.reply("❌ الكود غير صالح")
        except: await event.reply("❌ خطأ في الاتصال")
        user_state[sid] = None

    # 2. الردود
    elif state == "add_keyword":
        settings["keywords"].append(text); save_data(); await event.reply(f"✅ تمت إضافة الكلمة: `{text}`"); user_state[sid] = None
    elif state == "add_reply":
        settings["replies"].append(text); save_data(); await event.reply(f"✅ تمت إضافة الرد: `{text}`"); user_state[sid] = None

    # 3. المتجر
    elif state == "set_store_name": settings["store_name"] = text; save_data(); await event.reply("✅ تم حفظ الاسم"); user_state[sid] = None
    elif state == "inv_client": invoice_drafts[sid]['client_name'] = text; user_state[sid] = "inv_prod"; await event.reply("🛍️ اسم المنتج:")
    elif state == "inv_prod": invoice_drafts[sid]['product'] = text; user_state[sid] = "inv_count"; await event.reply("🔢 العدد:")
    elif state == "inv_count": invoice_drafts[sid]['count'] = text; user_state[sid] = "inv_price"; await event.reply("💰 السعر الإجمالي:")
    elif state == "inv_price": invoice_drafts[sid]['price'] = text; user_state[sid] = "inv_warranty"; await event.reply("🛡️ مدة الضمان:")
    elif state == "inv_warranty":
        invoice_drafts[sid]['warranty'] = text
        code = ''.join([str(random.randint(0,9)) for _ in range(16)])
        settings["invoices_archive"][code] = invoice_drafts[sid]; save_data()
        fn = f"Invoice_{code}.pdf"
        if create_invoice_pdf(invoice_drafts[sid], code, fn): await event.client.send_file(event.chat_id, fn, caption=f"🧾 **تم الإنشاء**\n🔐 المرجع: `{code}`"); os.remove(fn)
        else: await event.reply("❌ خطأ في الملف")
        user_state[sid] = None; await show_store_menu(event)

    # 4. باقي الأدوات
    elif state == "wait_search_inv":
        d = settings["invoices_archive"].get(text)
        if d:
            fn = f"Copy_{text}.pdf"
            if create_invoice_pdf(d, text, fn): await event.client.send_file(event.chat_id, fn, caption="📂 نسخة أرشيف"); os.remove(fn)
            else: await event.reply("❌ خطأ")
        else: await event.reply("❌ غير موجود")
        user_state[sid] = None

    elif state == "wait_remind_user":
        try: await user_client.send_message(text, "👋 **تذكير:** يرجى مراجعة الدفعات المستحقة."); await event.reply("✅ تم الإرسال")
        except: await event.reply("❌ المستخدم غير موجود")
        user_state[sid] = None

    elif state == "voice_wait_user":
        try: ent = await user_client.get_entity(text); temp_data[sid]['target'] = ent.id; user_state[sid] = "voice_wait_record"; await event.reply("2️⃣ أرسل الفويس الآن:")
        except: await event.reply("❌ خطأ في المعرف")
    elif state == "voice_wait_record":
        if event.voice or event.audio:
            tgt = temp_data[sid]['target']; async with user_client.action(tgt, 'record-audio'): await asyncio.sleep(3)
            p = await event.download_media(); await user_client.send_file(tgt, p, voice_note=True); os.remove(p); await event.reply("✅ تم الإرسال"); user_state[sid] = None
        else: await event.reply("⚠️ أرسل ملف صوتي فقط")

    elif state == "wait_stalk_id":
        try: ent = await user_client.get_input_entity(text); settings["stalk_list"].append(ent.user_id); save_data(); await event.reply("✅ تمت الإضافة للمراقبة")
        except: await event.reply("❌ خطأ")
        user_state[sid] = None
    elif state == "wait_type_id":
        try: ent = await user_client.get_input_entity(text); settings["typing_watch_list"].append(ent.user_id); await event.reply("✅ تمت الإضافة")
        except: await event.reply("❌ خطأ")
        user_state[sid] = None

    elif state == "wait_ip":
        try: r = requests.get(f"http://ip-api.com/json/{text}").json(); await event.reply(f"🌍 **IP Info:**\nCountry: {r.get('country')}\nCity: {r.get('city')}\nISP: {r.get('isp')}")
        except: await event.reply("❌ خطأ")
        user_state[sid] = None
    elif state == "wait_short_link":
        try: await event.reply(requests.get(f"https://tinyurl.com/api-create.php?url={text}").text)
        except: await event.reply("❌ خطأ")
        user_state[sid] = None
    elif state == "wait_shell":
        try: await event.reply(f"📟 **Output:**\n`{os.popen(text).read()[:4000]}`")
        except: await event.reply("❌ خطأ")
        user_state[sid] = None
    elif state == "wait_zip_files":
        if text == "تم":
            if temp_data.get(sid):
                zname = "archive.zip"
                with zipfile.ZipFile(zname, 'w') as zf:
                    for f in temp_data[sid]: zf.write(f)
                await user_client.send_file("me", zname); [os.remove(f) for f in temp_data[sid]]; os.remove(zname); await event.reply("✅ تم الضغط والإرسال للمحفوظات")
            user_state[sid] = None
        elif event.media:
            p = await event.download_media(); 
            if sid not in temp_data: temp_data[sid] = []
            temp_data[sid].append(p); await event.reply("📥 استلمت. أرسل المزيد أو اكتب 'تم'")

    elif state == "wait_clone_src":
        if not user_client: await event.reply("⚠️ اليوزربوت غير يعمل"); return
        msg = await event.reply("⏳ جاري سحب الأعضاء...")
        try:
            if "t.me" in text: 
                try: await user_client(functions.channels.JoinChannelRequest(text))
                except: pass
            src = await user_client.get_entity(text); parts = await user_client.get_participants(src, aggressive=True)
            valid = [u for u in parts if not u.bot and not u.deleted]
            if not valid: await msg.edit("❌ لا يوجد أعضاء"); user_state[sid] = None; return
            temp_data[sid] = {'scraped': valid}; await msg.edit(f"✅ وجدنا {len(valid)} عضو.\n2️⃣ كم عدد الإضافة؟"); user_state[sid] = "wait_clone_count"
        except Exception as e: await msg.edit(f"❌ خطأ: {e}"); user_state[sid] = None

    elif state == "wait_clone_count":
        try: temp_data[sid]['limit'] = int(text); await event.reply("3️⃣ أرسل رابط المجموعة الهدف:"); user_state[sid] = "wait_clone_dest"
        except: await event.reply("❌ أرسل رقماً")

    elif state == "wait_clone_dest":
        users = temp_data[sid]['scraped']; limit = temp_data[sid]['limit']
        msg = await event.reply(f"🚀 بدء النقل ({limit} عضو)...")
        asyncio.create_task(add_members_task(user_client, text, users, limit, msg)); user_state[sid] = None

    elif state == "wait_dl_link":
        try:
            await event.reply("⏳ جاري التحميل...")
            # Placeholder for download logic
            await event.reply("📥 الميزة قيد التطوير.")
        except: pass
        user_state[sid] = None

# ------------------------------------------------------------------------------
# السيرفر والتشغيل
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

async def show_login_button(event): await event.respond("👋 مرحباً بك في بوت الخدمات السحابي", buttons=[[Button.inline("➕ تسجيل الدخول", b"login")]])

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
