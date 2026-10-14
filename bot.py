# -*- coding: utf-8 -*-
import sqlite3, threading, time, math
from datetime import datetime, date
import telebot
from telebot import types
import config

DB = "/data/flower.db"

def db(q, p=(), fetch=None):
    con = sqlite3.connect(DB); cur = con.cursor(); cur.execute(q, p)
    if fetch == "one": r = cur.fetchone()
    elif fetch == "all": r = cur.fetchall()
    else: con.commit(); r = cur.lastrowid
    con.close(); return r

def now(): return datetime.now().strftime("%d.%m.%Y %H:%M")
def today(): return date.today().strftime("%Y-%m-%d")

def db_init():
    con = sqlite3.connect(DB); c = con.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS shops (id INTEGER PRIMARY KEY AUTOINCREMENT, tg_id INTEGER UNIQUE, name TEXT, address TEXT, phone TEXT, telegram TEXT, vk TEXT, owner_name TEXT, status TEXT DEFAULT 'pending', rating REAL DEFAULT 0, created_at TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS couriers (id INTEGER PRIMARY KEY AUTOINCREMENT, tg_id INTEGER UNIQUE, name TEXT, phone TEXT, city TEXT, transport TEXT, card TEXT, balance REAL DEFAULT 0, status TEXT DEFAULT 'pending', rating REAL DEFAULT 0, lat REAL, lon REAL, loc_time TEXT, created_at TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY AUTOINCREMENT, shop_id INTEGER, courier_id INTEGER, shop_name TEXT, address_from TEXT, address_to TEXT, client_name TEXT, client_phone TEXT, client_tg_id INTEGER, delivery_time TEXT, order_price REAL, delivery_price REAL, commission REAL, courier_fee REAL, comment TEXT, status TEXT DEFAULT 'new', payment_status TEXT DEFAULT 'pending', created_at TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS shifts (id INTEGER PRIMARY KEY AUTOINCREMENT, courier_id INTEGER, date TEXT, slot TEXT, status TEXT DEFAULT 'booked', checked_in TEXT, penalty REAL DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS withdrawals (id INTEGER PRIMARY KEY AUTOINCREMENT, courier_id INTEGER, amount REAL, card TEXT, status TEXT DEFAULT 'pending', created_at TEXT)")
    con.commit(); con.close()

bot_client = telebot.TeleBot(config.CLIENT_TOKEN)
bot_shop = telebot.TeleBot(config.SHOP_TOKEN)
bot_courier = telebot.TeleBot(config.COURIER_TOKEN)
bot_admin = telebot.TeleBot(config.ADMIN_TOKEN)

shop_reg, cour_reg, order_reg, withdraw_reg = {}, {}, {}, {}

def kb_shop():
    k = types.ReplyKeyboardMarkup(resize_keyboard=True)
    k.row("🆕 Создать заявку"); k.row("📋 Мои заявки", "📊 Статистика"); k.row("⚙️ Настройки")
    return k

def kb_courier():
    k = types.ReplyKeyboardMarkup(resize_keyboard=True)
    k.row("📋 Свободные заявки"); k.row("🚗 Мои заказы", "💰 Заработок"); k.row("📅 Смены", "📍 Гео"); k.row("📊 Статистика")
    return k

def kb_admin():
    k = types.ReplyKeyboardMarkup(resize_keyboard=True)
    k.row("📝 Запросы"); k.row("🏪 Магазины", "🚚 Курьеры"); k.row("💰 Финансы", "💳 Выплаты"); k.row("📅 Смены")
    return k

def kb_admin_req():
    k = types.ReplyKeyboardMarkup(resize_keyboard=True)
    k.row("🏪 Заявки магазинов"); k.row("🚚 Заявки курьеров"); k.row("📅 Заявки смен")
    k.row("💳 Заявки выплат"); k.row("❌ Отмены заявок"); k.row("⬅️ Назад")
    return k

def kb_client():
    k = types.ReplyKeyboardMarkup(resize_keyboard=True)
    k.row("🏪 Магазины"); k.row("ℹ️ О сервисе")
    return k

def kb_cancel():
    k = types.ReplyKeyboardMarkup(resize_keyboard=True); k.row("❌ Отмена")
    return k

def kb_shift_slots():
    k = types.ReplyKeyboardMarkup(resize_keyboard=True)
    k.row("🌅 Утренняя 7–15"); k.row("☀️ Дневная 9–18"); k.row("🌆 Вечерняя 15–23")
    k.row("🌙 Ночная 18–00"); k.row("📋 Мои смены"); k.row("⬅️ Назад")
    return k

def is_cancel(m): return m.text == "❌ Отмена"
def geo_link(lat, lon): return f"https://yandex.ru/maps/?pt={lon},{lat}&z=17&l=map"
    # ========== КЛИЕНТ ==========
@bot_client.message_handler(commands=['start'])
def client_start(m):
    bot_client.send_message(m.chat.id,
        f"🌸 Добро пожаловать в {config.SERVICE_NAME}!\n\n"
        f"🚚 Доставка цветов по городу {config.CITY}\n"
        f"🕐 Работаем: {config.WORK_HOURS}\n\nВыберите действие:",
        reply_markup=kb_client())

@bot_client.message_handler(func=lambda m: m.text=="🏪 Магазины")
def client_shops(m):
    shops = db("SELECT id, name, address, phone, telegram, vk, rating FROM shops WHERE status='active'", fetch="all")
    if not shops:
        bot_client.send_message(m.chat.id, "🏪 Магазины\n━━━━━━━━━━━━━━━\n\n😔 Пока нет активных магазинов.\n\nСкоро появятся!")
        return
    bot_client.send_message(m.chat.id, f"🏪 Доступно магазинов: {len(shops)}")
    for s in shops:
        sid, name, addr, phone, tg, vk, rating = s
        txt = f"🌸 {name}\n━━━━━━━━━━━━━━━\n📍 {addr}\n📞 {phone}\n"
        if tg: txt += f"✈️ {tg}\n"
        if vk: txt += f"📱 {vk}\n"
        if rating: txt += f"⭐ {rating:.1f}\n"
        bot_client.send_message(m.chat.id, txt)

@bot_client.message_handler(func=lambda m: m.text=="ℹ️ О сервисе")
def client_about(m):
    bot_client.send_message(m.chat.id,
        f"🌸 {config.SERVICE_NAME}\n━━━━━━━━━━━━━━━\n\n"
        f"🚚 Доставка цветов\n📍 {config.CITY}\n🕐 {config.WORK_HOURS}\n📅 {config.WORK_DAYS}\n\n"
        f"━━━━━━━━━━━━━━━\n📞 {config.SUPPORT_PHONE}\n✈️ {config.SERVICE_VK_TG}\n📱 {config.SERVICE_VK}\n"
        f"━━━━━━━━━━━━━━━\n\nРаботаем ежедневно с 7:00 до 24:00.")

# ========== МАГАЗИН ==========
@bot_shop.message_handler(commands=['start'])
def shop_start(m):
    s = db("SELECT * FROM shops WHERE tg_id=?", (m.from_user.id,), "one")
    if not s:
        bot_shop.send_message(m.chat.id, "👋 Привет!\n\n🌸 Хотите стать магазином в SLIPI?\n\nОтправьте /register")
        return
    if s[8]=="pending": bot_shop.send_message(m.chat.id, "⏳ Заявка на рассмотрении.")
    elif s[8]=="blocked": bot_shop.send_message(m.chat.id, "🚫 Доступ закрыт.")
    else: bot_shop.send_message(m.chat.id, f"🌸 {s[2]}\n\nМагазин активен ✅", reply_markup=kb_shop())

@bot_shop.message_handler(commands=['register'])
def shop_reg_start(m):
    if db("SELECT id FROM shops WHERE tg_id=?", (m.from_user.id,), "one"):
        bot_shop.send_message(m.chat.id, "Вы уже зарегистрированы."); return
    shop_reg[m.from_user.id] = {"step":"name","d":{}}
    bot_shop.send_message(m.chat.id, "📝 Шаг 1/6: Название магазина", reply_markup=kb_cancel())

@bot_shop.message_handler(func=lambda m: m.from_user.id in shop_reg)
def shop_reg_step(m):
    if is_cancel(m):
        del shop_reg[m.from_user.id]
        bot_shop.send_message(m.chat.id, "Отменено.", reply_markup=kb_shop()); return
    st = shop_reg[m.from_user.id]; s = st["step"]; d = st["d"]
    if s == "phone":
        t = m.text.replace(" ","").replace("-","").replace("(","").replace(")","")
        if t.startswith("+7"): t = "8" + t[2:]
        elif t.startswith("7") and len(t) == 11: t = "8" + t[1:]
        if not t.isdigit() or len(t) != 11 or not t.startswith("8"):
            bot_shop.send_message(m.chat.id, "❌ Неверный номер.\nФормат: 8XXXXXXXXXX (11 цифр)\nПример: 89917929251"); return
        d[s] = t; st["step"] = "telegram"
        bot_shop.send_message(m.chat.id, "✅ Телефон принят\n\nШаг 4/6: Ваш Telegram\n\nОтправьте @username\nИли /skip — возьмём из профиля"); return
    if s == "telegram":
        if m.text.startswith("/skip"): tg = f"@{m.from_user.username}" if m.from_user.username else "нет"
        else: tg = m.text if m.text.startswith("@") else "@" + m.text
        d[s] = tg; st["step"] = "vk"
        bot_shop.send_message(m.chat.id, "Шаг 5/6: Ваш ВКонтакте (ссылка или @ник)"); return
    d[s] = m.text
    if s == "name":
        st["step"] = "address"; bot_shop.send_message(m.chat.id, "Шаг 2/6: Адрес магазина")
    elif s == "address":
        st["step"] = "phone"; bot_shop.send_message(m.chat.id, "Шаг 3/6: Телефон\n\nФормат: 8XXXXXXXXXX (11 цифр)")
    elif s == "vk":
        st["step"] = "owner_name"; bot_shop.send_message(m.chat.id, "Шаг 6/6: Ваше имя")
    elif s == "owner_name":
        db("INSERT INTO shops (tg_id,name,address,phone,telegram,vk,owner_name,created_at) VALUES (?,?,?,?,?,?,?,?)",
           (m.from_user.id, d["name"], d["address"], d["phone"], d["telegram"], d["vk"], d["owner_name"], now()))
        sid = db("SELECT id FROM shops WHERE tg_id=?", (m.from_user.id,), "one")[0]
        del shop_reg[m.from_user.id]
        bot_shop.send_message(m.chat.id,
            f"✅ Заявка отправлена!\n\n🏪 {d['name']}\n📍 {d['address']}\n📞 {d['phone']}\n"
            f"✈️ {d['telegram']}\n📱 {d['vk']}\n👤 {d['owner_name']}\n\nЖдём одобрения админа.",
            reply_markup=kb_shop())
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("✅ Одобрить", callback_data=f"shop_ok_{sid}"),
               types.InlineKeyboardButton("❌ Отклонить", callback_data=f"shop_no_{sid}"))
        bot_admin.send_message(config.ADMIN_ID,
            f"🏪 НОВЫЙ МАГАЗИН\n━━━━━━━━━━━━━━━\n{d['name']}\n📍 {d['address']}\n"
            f"📞 {d['phone']}\n✈️ {d['telegram']}\n📱 {d['vk']}\n👤 {d['owner_name']}",
            reply_markup=kb)
        # ========== ЗАЯВКА МАГАЗИНА ==========
@bot_shop.message_handler(func=lambda m: m.text=="🆕 Создать заявку")
def order_start(m):
    s = db("SELECT * FROM shops WHERE tg_id=?", (m.from_user.id,), "one")
    if not s or s[8]!="active":
        bot_shop.send_message(m.chat.id, "Доступ закрыт."); return
    order_reg[m.from_user.id] = {"step":"shop_name","d":{"shop_id":s[0]}}
    bot_shop.send_message(m.chat.id, "📦 Шаг 1/10: Название магазина", reply_markup=kb_cancel())

@bot_shop.message_handler(func=lambda m: m.from_user.id in order_reg)
def order_step(m):
    if is_cancel(m):
        del order_reg[m.from_user.id]
        bot_shop.send_message(m.chat.id, "Отменено.", reply_markup=kb_shop()); return
    st = order_reg[m.from_user.id]; s = st["step"]; d = st["d"]
    prompts = {"address_from":"Шаг 2/10: Откуда забрать","address_to":"Шаг 3/10: Куда отвезти",
               "client_name":"Шаг 4/10: Имя клиента","client_phone":"Шаг 5/10: Телефон клиента",
               "client_tg":"Шаг 6/10: TG ID клиента (цифры)","delivery_time":"Шаг 7/10: Ко скольким доставить",
               "order_price":"Шаг 8/10: Сумма заказа ₽","delivery_price":f"Шаг 9/10: Доставка ₽ (мин {config.MIN_DELIVERY})",
               "comment":"Шаг 10/10: Комментарий для курьера"}
    steps = ["shop_name","address_from","address_to","client_name","client_phone","client_tg","delivery_time","order_price","delivery_price","comment"]
    if s == "client_tg":
        if not m.text.strip().isdigit(): bot_shop.send_message(m.chat.id, "❌ Только цифры."); return
        d[s] = int(m.text.strip())
    elif s in ("order_price","delivery_price"):
        try: v = float(m.text.replace(",","."))
        except: bot_shop.send_message(m.chat.id, "❌ Введите число."); return
        if s == "delivery_price" and v < config.MIN_DELIVERY:
            bot_shop.send_message(m.chat.id, f"❌ Минимум {config.MIN_DELIVERY} ₽\nКурьеру: {v*0.85:.2f} ₽"); return
        d[s] = v
    else: d[s] = m.text
    i = steps.index(s)
    if i+1 < len(steps):
        st["step"] = steps[i+1]; bot_shop.send_message(m.chat.id, prompts[st["step"]])
    else:
        d["commission"] = round(d["delivery_price"]*config.COMMISSION_PERCENT/100, 2)
        d["courier_fee"] = round(d["delivery_price"]-d["commission"], 2)
        oid = db("INSERT INTO orders (shop_id,shop_name,address_from,address_to,client_name,client_phone,client_tg_id,delivery_time,order_price,delivery_price,commission,courier_fee,comment,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 (d["shop_id"], d["shop_name"], d["address_from"], d["address_to"], d["client_name"], d["client_phone"], d["client_tg"], d["delivery_time"], d["order_price"], d["delivery_price"], d["commission"], d["courier_fee"], d["comment"], now()))
        del order_reg[m.from_user.id]
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("💳 Я оплатил", callback_data=f"paid_{oid}"))
        bot_shop.send_message(m.chat.id,
            f"✅ Заявка #{oid} создана!\n━━━━━━━━━━━━━━━\n🎯 Куда: {d['address_to']}\n💰 Заказ: {d['order_price']:.2f} ₽\n🚚 Доставка: {d['delivery_price']:.2f} ₽\n━━━━━━━━━━━━━━━\n\n💳 ОПЛАТА\nКарта: {config.CARD_NUMBER}\n{config.CARD_HOLDER}\n{config.BANK_NAME}\nСБП: {config.SBP_PHONE}\n\nПосле оплаты нажмите кнопку:", reply_markup=kb)

@bot_shop.message_handler(func=lambda m: m.text=="📋 Мои заявки")
def shop_orders(m):
    s = db("SELECT * FROM shops WHERE tg_id=?", (m.from_user.id,), "one")
    if not s: return
    orders = db("SELECT * FROM orders WHERE shop_id=? ORDER BY id DESC LIMIT 15", (s[0],), "all")
    if not orders: bot_shop.send_message(m.chat.id, "📋 Заявок нет."); return
    for o in orders:
        em = config.STATUS_EMOJI.get(o[16], "❓"); st_txt = config.STATUS_TEXT.get(o[16], o[16])
        txt = f"{em} Заказ #{o[0]}\n━━━━━━━━━━━━━━━\n🎯 {o[5][:50]}\n💰 {o[11]:.2f} ₽\n🚚 Доставка: {o[12]:.2f} ₽\nСтатус: {st_txt}"
        if o[2]:
            cr = db("SELECT name, phone FROM couriers WHERE id=?", (o[2],), "one")
            if cr: txt += f"\n🚚 {cr[0]}\n📞 {cr[1]}"
        kb = types.InlineKeyboardMarkup()
        if o[16] not in ("done","cancel"):
            kb.add(types.InlineKeyboardButton("❌ Отменить заявку", callback_data=f"cancel_{o[0]}"))
        if kb.keyboard: bot_shop.send_message(m.chat.id, txt, reply_markup=kb)
        else: bot_shop.send_message(m.chat.id, txt)

@bot_shop.message_handler(func=lambda m: m.text=="📊 Статистика")
def shop_stats(m):
    s = db("SELECT * FROM shops WHERE tg_id=?", (m.from_user.id,), "one")
    if not s: return
    orders = db("SELECT * FROM orders WHERE shop_id=?", (s[0],), "all")
    total = len(orders); done = sum(1 for o in orders if o[16]=="done"); cancel = sum(1 for o in orders if o[16]=="cancel")
    summ = sum(o[11] for o in orders if o[11]); comm = sum(o[12] for o in orders if o[12])
    bot_shop.send_message(m.chat.id, f"📊 Статистика\n━━━━━━━━━━━━━━━\n\n📦 Заявок: {total}\n✅ Доставлено: {done}\n❌ Отменено: {cancel}\n\n💰 Оборот: {summ:.2f} ₽\n💵 Комиссия: {comm:.2f} ₽")

@bot_shop.message_handler(func=lambda m: m.text=="⚙️ Настройки")
def shop_settings(m): bot_shop.send_message(m.chat.id, "⚙️ В разработке")

@bot_shop.callback_query_handler(func=lambda c: c.data.startswith("paid_"))
def cb_paid(c):
    oid = int(c.data.split("_")[1])
    db("UPDATE orders SET payment_status='confirmed', status='wait' WHERE id=?", (oid,))
    bot_shop.edit_message_text(f"✅ Оплата #{oid} подтверждена!\nИщем курьера...", c.message.chat.id, c.message.message_id)
    o = db("SELECT * FROM orders WHERE id=?", (oid,), "one")
    bot_admin.send_message(config.ADMIN_ID, f"💰 Оплата по заявке #{oid}\nМагазин: {o[3]}\nСумма: {o[11]:.2f} ₽")

@bot_shop.callback_query_handler(func=lambda c: c.data.startswith("cancel_"))
def cb_cancel_order(c):
    oid = int(c.data.split("_")[1]); o = db("SELECT * FROM orders WHERE id=?", (oid,), "one")
    if not o: bot_shop.answer_callback_query(c.id, "Заявка не найдена"); return
    if o[16] in ("done","cancel"): bot_shop.answer_callback_query(c.id, "Уже закрыта"); return
    s = db("SELECT tg_id FROM shops WHERE id=?", (o[1],), "one")
    if not s or s[0] != c.from_user.id: bot_shop.answer_callback_query(c.id, "Не ваша заявка"); return
    db("UPDATE orders SET status='cancel' WHERE id=?", (oid,))
    bot_shop.edit_message_text(f"❌ Заявка #{oid} отменена", c.message.chat.id, c.message.message_id)
    if o[2]:
        cr = db("SELECT tg_id FROM couriers WHERE id=?", (o[2],), "one")
        if cr:
            try: bot_courier.send_message(cr[0], f"❌ Заказ #{oid} отменён магазином «{o[3]}»")
            except: pass
    if o[8]:
        try: bot_client.send_message(o[8], f"❌ Заказ #{oid} отменён")
        except: pass
    bot_admin.send_message(config.ADMIN_ID, f"❌ Отмена #{oid}\nМагазин: {o[3]}")
    bot_shop.answer_callback_query(c.id, "Отменено")

# ========== КУРЬЕР ==========
@bot_courier.message_handler(commands=['start'])
def cour_start(m):
    c = db("SELECT * FROM couriers WHERE tg_id=?", (m.from_user.id,), "one")
    if not c: bot_courier.send_message(m.chat.id, "👋 Привет!\n\n🚚 Хотите стать курьером SLIPI?\n\nОтправьте /register"); return
    if c[8]=="pending": bot_courier.send_message(m.chat.id, "⏳ Заявка на рассмотрении.")
    elif c[8]=="blocked": bot_courier.send_message(m.chat.id, "🚫 Доступ закрыт.")
    else: bot_courier.send_message(m.chat.id, f"🚚 Меню курьера\n━━━━━━━━━━━━━━━\n👤 {c[2]}\n💰 Баланс: {c[7]:.2f} ₽", reply_markup=kb_courier())

@bot_courier.message_handler(commands=['register'])
def cour_reg_start(m):
    if db("SELECT id FROM couriers WHERE tg_id=?", (m.from_user.id,), "one"):
        bot_courier.send_message(m.chat.id, "Уже зарегистрированы."); return
    cour_reg[m.from_user.id] = {"step":"name","d":{}}
    bot_courier.send_message(m.chat.id, "📝 Шаг 1/5: Ваше имя", reply_markup=kb_cancel())

@bot_courier.message_handler(func=lambda m: m.from_user.id in cour_reg)
def cour_reg_step(m):
    if is_cancel(m):
        del cour_reg[m.from_user.id]
        bot_courier.send_message(m.chat.id, "Отменено.", reply_markup=kb_courier()); return
    st = cour_reg[m.from_user.id]; s = st["step"]; d = st["d"]
    steps = ["name","phone","city","transport","card"]
    prompts = {"phone":"Шаг 2/5: Телефон (8XXXXXXXXXX)","city":"Шаг 3/5: Город / район","transport":"Шаг 4/5: Транспорт (Авто / Мото / Велик / Пешком)","card":"Шаг 5/5: Карта для вывода"}
    if s == "phone":
        t = m.text.replace(" ","").replace("-","").replace("(","").replace(")","")
        if t.startswith("+7"): t = "8" + t[2:]
        elif t.startswith("7") and len(t) == 11: t = "8" + t[1:]
        if not t.isdigit() or len(t) != 11 or not t.startswith("8"):
            bot_courier.send_message(m.chat.id, "❌ Неверный номер.\nФормат: 8XXXXXXXXXX (11 цифр)"); return
        d[s] = t; st["step"] = "city"; bot_courier.send_message(m.chat.id, prompts["city"]); return
    d[s] = m.text
    i = steps.index(s)
    if i+1 < len(steps):
        st["step"] = steps[i+1]; bot_courier.send_message(m.chat.id, prompts[st["step"]])
    else:
        db("INSERT INTO couriers (tg_id,name,phone,city,transport,card,created_at) VALUES (?,?,?,?,?,?,?)",
           (m.from_user.id, d["name"], d["phone"], d["city"], d["transport"], d["card"], now()))
        cid = db("SELECT id FROM couriers WHERE tg_id=?", (m.from_user.id,), "one")[0]
        del cour_reg[m.from_user.id]
        bot_courier.send_message(m.chat.id, "✅ Заявка отправлена! Ждём одобрения.", reply_markup=kb_courier())
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("✅ Одобрить", callback_data=f"cour_ok_{cid}"),
               types.InlineKeyboardButton("❌ Отклонить", callback_data=f"cour_no_{cid}"))
        bot_admin.send_message(config.ADMIN_ID,
            f"🚚 НОВЫЙ КУРЬЕР\n━━━━━━━━━━━━━━━\n👤 {d['name']}\n📞 {d['phone']}\n📍 {d['city']}\n🚗 {d['transport']}\n💳 {d['card']}", reply_markup=kb)

@bot_courier.message_handler(func=lambda m: m.text=="📋 Свободные заявки")
def cour_free(m):
    orders = db("SELECT * FROM orders WHERE status='wait' AND payment_status='confirmed' ORDER BY id ASC", fetch="all")
    if not orders:
        bot_courier.send_message(m.chat.id, "📋 Свободные заявки\n━━━━━━━━━━━━━━━\n\n😔 Сейчас свободных нет.\n\nЗаглядывайте позже.")
        return
    bot_courier.send_message(m.chat.id, f"📋 Свободных заявок: {len(orders)}")
    for o in orders[:10]:
        txt = f"📦 Заказ #{o[0]}\n━━━━━━━━━━━━━━━\n🏪 {o[3]}\n📍 Откуда: {o[4]}\n🎯 Куда: {o[5]}\n🕐 {o[9]}\n💰 {o[13]:.2f} ₽\n━━━━━━━━━━━━━━━"
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("✅ Взять заказ", callback_data=f"take_{o[0]}"))
        bot_courier.send_message(m.chat.id, txt, reply_markup=kb)

@bot_courier.callback_query_handler(func=lambda c: c.data.startswith("take_"))
def cb_take(c):
    oid = int(c.data.split("_")[1]); o = db("SELECT * FROM orders WHERE id=?", (oid,), "one")
    if not o: bot_courier.answer_callback_query(c.id, "Не найдена"); return
    if o[16] != "wait": bot_courier.answer_callback_query(c.id, "Уже занята"); return
    cr = db("SELECT * FROM couriers WHERE tg_id=?", (c.from_user.id,), "one")
    db("UPDATE orders SET courier_id=?, status='going' WHERE id=?", (cr[0], oid))
    txt = f"✅ Вы взяли заказ #{oid}\n━━━━━━━━━━━━━━━\n🏪 {o[3]}\n📍 Откуда: {o[4]}\n🎯 Куда: {o[5]}\n👤 {o[6]}, {o[7]}\n🕐 {o[9]}\n💰 {o[13]:.2f} ₽\n💬 {o[14] or '—'}"
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📦 Забрал в магазине", callback_data=f"picked_{oid}"))
    kb.add(types.InlineKeyboardButton("🗺 Карта откуда", url=f"https://yandex.ru/maps/?text={o[4].replace(' ','+')}"))
    kb.add(types.InlineKeyboardButton("❌ Отказаться", callback_data=f"refuse_{oid}"))
    bot_courier.send_message(c.from_user.id, txt, reply_markup=kb)
    s = db("SELECT tg_id FROM shops WHERE id=?", (o[1],), "one")
    try: bot_shop.send_message(s[0], f"🚚 Курьер {cr[2]} взял заказ #{oid}\n📞 {cr[3]}")
    except: pass
    bot_courier.answer_callback_query(c.id)

@bot_courier.callback_query_handler(func=lambda c: c.data.startswith("picked_"))
def cb_picked(c):
    oid = int(c.data.split("_")[1]); db("UPDATE orders SET status='delivering' WHERE id=?", (oid,))
    o = db("SELECT * FROM orders WHERE id=?", (oid,), "one")
    txt = f"📦 Заказ #{oid} забран\n━━━━━━━━━━━━━━━\n🎯 Куда: {o[5]}\n👤 {o[6]}, {o[7]}\n💰 {o[13]:.2f} ₽\n💬 {o[14] or '—'}"
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📍 Я у клиента", callback_data=f"atcli_{oid}"),
           types.InlineKeyboardButton("✅ Доставлено", callback_data=f"done_{oid}"))
    kb.add(types.InlineKeyboardButton("🗺 Карта куда", url=f"https://yandex.ru/maps/?text={o[5].replace(' ','+')}"))
    kb.add(types.InlineKeyboardButton("📞 Позвонить клиенту", url=f"tel:{o[7]}"))
    bot_courier.send_message(c.from_user.id, txt, reply_markup=kb)
    s = db("SELECT tg_id FROM shops WHERE id=?", (o[1],), "one")
    try: bot_shop.send_message(s[0], f"📦 Курьер забрал заказ #{oid}, везёт клиенту")
    except: pass
    if o[8]:
        try: bot_client.send_message(o[8], f"🚚 Курьер везёт ваш заказ #{oid}\n🎯 {o[5]}")
        except: pass
    bot_courier.answer_callback_query(c.id)

@bot_courier.callback_query_handler(func=lambda c: c.data.startswith("atcli_"))
def cb_atcli(c):
    oid = int(c.data.split("_")[1]); db("UPDATE orders SET status='at_client' WHERE id=?", (oid,))
    o = db("SELECT * FROM orders WHERE id=?", (oid,), "one")
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("✅ Доставлено", callback_data=f"done_{oid}"))
    kb.add(types.InlineKeyboardButton("📞 Позвонить клиенту", url=f"tel:{o[7]}"))
    bot_courier.send_message(c.from_user.id, f"📍 Заказ #{oid} — вы у клиента\n\n👤 {o[6]}\n📞 {o[7]}\n🎯 {o[5]}", reply_markup=kb)
    if o[8]:
        try: bot_client.send_message(o[8], f"📍 Курьер у вашего подъезда! Заказ #{oid}")
        except: pass
    bot_courier.answer_callback_query(c.id)

@bot_courier.callback_query_handler(func=lambda c: c.data.startswith("done_"))
def cb_done(c):
    oid = int(c.data.split("_")[1]); o = db("SELECT * FROM orders WHERE id=?", (oid,), "one")
    cr = db("SELECT * FROM couriers WHERE tg_id=?", (c.from_user.id,), "one")
    db("UPDATE orders SET status='done' WHERE id=?", (oid,))
    db("UPDATE couriers SET balance=balance+? WHERE id=?", (o[13], cr[0]))
    new_bal = db("SELECT balance FROM couriers WHERE id=?", (cr[0],), "one")[0]
    bot_courier.send_message(c.from_user.id, f"✅ Заказ #{oid} доставлен!\n━━━━━━━━━━━━━━━\n💰 Заработано: +{o[13]:.2f} ₽\n💵 Баланс: {new_bal:.2f} ₽")
    s = db("SELECT tg_id FROM shops WHERE id=?", (o[1],), "one")
    try: bot_shop.send_message(s[0], f"✅ Заказ #{oid} доставлен!")
    except: pass
    if o[8]:
        try: bot_client.send_message(o[8], f"✅ Ваш заказ #{oid} доставлен! Спасибо 🌸")
        except: pass
    bot_courier.answer_callback_query(c.id)

@bot_courier.callback_query_handler(func=lambda c: c.data.startswith("refuse_"))
def cb_refuse(c):
    oid = int(c.data.split("_")[1]); o = db("SELECT * FROM orders WHERE id=?", (oid,), "one")
    db("UPDATE orders SET courier_id=NULL, status='wait' WHERE id=?", (oid,))
    bot_courier.send_message(c.from_user.id, f"↩️ Заказ #{oid} возвращён в общий список.")
    s = db("SELECT tg_id FROM shops WHERE id=?", (o[1],), "one")
    try: bot_shop.send_message(s[0], f"↩️ Курьер отказался от заказа #{oid}")
    except: pass
    bot_courier.answer_callback_query(c.id)

@bot_courier.message_handler(func=lambda m: m.text=="🚗 Мои заказы")
def cour_my(m):
    cr = db("SELECT * FROM couriers WHERE tg_id=?", (m.from_user.id,), "one")
    if not cr: return
    orders = db("SELECT * FROM orders WHERE courier_id=? AND status IN ('going','delivering','at_client') ORDER BY id DESC", (cr[0],), "all")
    if not orders:
        bot_courier.send_message(m.chat.id, "🚗 Мои заказы\n━━━━━━━━━━━━━━━\n\nСейчас активных заказов нет.\n\nВозьмите в «📋 Свободные заявки».")
        return
    bot_courier.send_message(m.chat.id, f"🚗 Активных заказов: {len(orders)}")
    for o in orders:
        em = config.STATUS_EMOJI.get(o[16], "❓"); st_txt = config.STATUS_TEXT.get(o[16], o[16])
        txt = f"{em} Заказ #{o[0]}\n━━━━━━━━━━━━━━━\n🏪 {o[3]}\n📍 Откуда: {o[4]}\n🎯 Куда: {o[5]}\n👤 {o[6]}, {o[7]}\n🕐 {o[9]}\n💰 {o[13]:.2f} ₽\n💬 {o[14] or '—'}\n━━━━━━━━━━━━━━━\nСтатус: {st_txt}"
        kb = types.InlineKeyboardMarkup()
        if o[16] == "going": kb.add(types.InlineKeyboardButton("📦 Забрал", callback_data=f"picked_{o[0]}"))
        elif o[16] == "delivering":
            kb.add(types.InlineKeyboardButton("📍 У клиента", callback_data=f"atcli_{o[0]}"), types.InlineKeyboardButton("✅ Доставлено", callback_data=f"done_{o[0]}"))
        elif o[16] == "at_client": kb.add(types.InlineKeyboardButton("✅ Доставлено", callback_data=f"done_{o[0]}"))
        kb.add(types.InlineKeyboardButton("🗺 Карта", url=f"https://yandex.ru/maps/?text={o[5].replace(' ','+')}"))
        kb.add(types.InlineKeyboardButton("📞 Клиент", url=f"tel:{o[7]}"))
        bot_courier.send_message(m.chat.id, txt, reply_markup=kb)

@bot_courier.message_handler(func=lambda m: m.text=="💰 Заработок")
def cour_money(m):
    cr = db("SELECT * FROM couriers WHERE tg_id=?", (m.from_user.id,), "one")
    if not cr: return
    done = db("SELECT COUNT(*) FROM orders WHERE courier_id=? AND status='done'", (cr[0],), "one")[0]
    earned = db("SELECT COALESCE(SUM(courier_fee),0) FROM orders WHERE courier_id=? AND status='done'", (cr[0],), "one")[0]
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("💳 Вывести деньги", callback_data="withdraw"))
    bot_courier.send_message(m.chat.id, f"💰 Мой заработок\n━━━━━━━━━━━━━━━\n\n💵 Баланс: {cr[7]:.2f} ₽\n✅ Доставок: {done}\n💸 Заработал всего: {earned:.2f} ₽", reply_markup=kb)

@bot_courier.callback_query_handler(func=lambda c: c.data=="withdraw")
def cb_withdraw(c):
    cr = db("SELECT * FROM couriers WHERE tg_id=?", (c.from_user.id,), "one")
    if not cr: bot_courier.answer_callback_query(c.id); return
    if cr[7] < 100: bot_courier.answer_callback_query(c.id, f"Минимум 100 ₽. Баланс: {cr[7]:.2f} ₽", show_alert=True); return
    withdraw_reg[c.from_user.id] = True
    bot_courier.send_message(c.from_user.id, f"💳 Вывод средств\n\nДоступно: {cr[7]:.2f} ₽\n\nВведите сумму:", reply_markup=kb_cancel())
    bot_courier.answer_callback_query(c.id)

@bot_courier.message_handler(func=lambda m: m.from_user.id in withdraw_reg)
def cour_wd(m):
    if is_cancel(m):
        del withdraw_reg[m.from_user.id]
        bot_courier.send_message(m.chat.id, "Отменено.", reply_markup=kb_courier()); return
    try: amt = float(m.text.replace(",","."))
    except: bot_courier.send_message(m.chat.id, "❌ Введите число."); return
    cr = db("SELECT * FROM couriers WHERE tg_id=?", (m.from_user.id,), "one")
    if amt < 100: bot_courier.send_message(m.chat.id, "❌ Минимум 100 ₽"); return
    if amt > cr[7]: bot_courier.send_message(m.chat.id, f"❌ Недостаточно. Баланс: {cr[7]:.2f} ₽"); return
    db("INSERT INTO withdrawals (courier_id,amount,card,created_at) VALUES (?,?,?,?)", (cr[0], amt, cr[6], now()))
    del withdraw_reg[m.from_user.id]
    bot_courier.send_message(m.chat.id, f"⏳ Заявка на вывод {amt:.2f} ₽ отправлена.\n\nЖдём подтверждения админа.", reply_markup=kb_courier())
    wid = db("SELECT id FROM withdrawals ORDER BY id DESC LIMIT 1", fetch="one")[0]
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("✅ Подтвердить", callback_data=f"wok_{wid}"), types.InlineKeyboardButton("❌ Отклонить", callback_data=f"wno_{wid}"))
    bot_admin.send_message(config.ADMIN_ID, f"💳 ЗАЯВКА НА ВЫВОД\n━━━━━━━━━━━━━━━\n🚚 {cr[2]}\n📞 {cr[3]}\n💰 {amt:.2f} ₽\n💳 {cr[6]}", reply_markup=kb)

@bot_courier.message_handler(func=lambda m: m.text=="📍 Гео")
def cour_loc(m):
    cr = db("SELECT * FROM couriers WHERE tg_id=?", (m.from_user.id,), "one")
    if not cr: return
    info = "нет данных"
    if cr[10]:
        link = geo_link(cr[10], cr[11])
        info = f"📍 {cr[10]:.5f}, {cr[11]:.5f}\n🕐 {cr[12]}\n🗺 [Открыть]({link})"
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("📍 Делиться 8 часов", request_location=True))
    kb.row("🛑 Стоп гео"); kb.row("⬅️ Назад")
    bot_courier.send_message(m.chat.id, f"📍 Моя геолокация\n━━━━━━━━━━━━━━━\n\n{info}\n\nНажмите «📍 Делиться 8 часов».\nTelegram предложит выбрать время —\nвыберите 8 часов.", reply_markup=kb, parse_mode="Markdown")

@bot_courier.message_handler(func=lambda m: m.text=="🛑 Стоп гео")
def cour_loc_stop(m):
    db("UPDATE couriers SET lat=NULL, lon=NULL, loc_time=NULL WHERE tg_id=?", (m.from_user.id,))
    bot_courier.send_message(m.chat.id, "🛑 Геолокация остановлена.", reply_markup=kb_courier())

@bot_courier.message_handler(func=lambda m: m.text=="⬅️ Назад")
def cour_loc_back(m): bot_courier.send_message(m.chat.id, "Главное меню", reply_markup=kb_courier())

@bot_courier.message_handler(content_types=['location'])
def cour_loc_got(m):
    lat, lon = m.location.latitude, m.location.longitude
    live = getattr(m.location, "live_period", None)
    db("UPDATE couriers SET lat=?, lon=?, loc_time=? WHERE tg_id=?", (lat, lon, now(), m.from_user.id))
    link = geo_link(lat, lon)
    if live and live > 60:
        bot_courier.send_message(m.chat.id, f"✅ Трансляция активна на {live/3600:.1f} ч\n📍 {lat:.5f}, {lon:.5f}\n\n[🗺 Карта]({link})", parse_mode="Markdown", reply_markup=kb_courier())
    else:
        bot_courier.send_message(m.chat.id, f"✅ Гео сохранено\n📍 {lat:.5f}, {lon:.5f}\n\n[🗺 Карта]({link})", parse_mode="Markdown", reply_markup=kb_courier())

@bot_courier.message_handler(func=lambda m: m.text=="📅 Смены")
def cour_shifts(m):
    cr = db("SELECT * FROM couriers WHERE tg_id=?", (m.from_user.id,), "one")
    if not cr: return
    txt = "📅 Смены на сегодня\n━━━━━━━━━━━━━━━\n\n"
    for k, v in config.SHIFT_SLOTS.items():
        cnt = db("SELECT COUNT(*) FROM shifts WHERE date=? AND slot=?", (today(), k), "one")[0]
        free = v["limit"] - cnt
        already = db("SELECT id FROM shifts WHERE date=? AND slot=? AND courier_id=?", (today(), k, cr[0]), "one")
        if already: mark = "✅ вы записаны"
        elif free > 0: mark = f"свободно {free}"
        else: mark = "❌ заполнено"
        txt += f"{v['name']} ({v['start']}–{v['end']})\n   {cnt}/{v['limit']} — {mark}\n\n"
    txt += f"━━━━━━━━━━━━━━━\n⚠️ Не вышли — штраф {config.SHIFT_PENALTY} ₽"
    bot_courier.send_message(m.chat.id, txt, reply_markup=kb_shift_slots())

@bot_courier.message_handler(func=lambda m: m.text in ["🌅 Утренняя 7–15","☀️ Дневная 9–18","🌆 Вечерняя 15–23","🌙 Ночная 18–00"])
def cour_shift_book(m):
    cr = db("SELECT * FROM couriers WHERE tg_id=?", (m.from_user.id,), "one")
    if not cr: return
    slot_map = {"🌅 Утренняя 7–15":"morning","☀️ Дневная 9–18":"day","🌆 Вечерняя 15–23":"evening","🌙 Ночная 18–00":"night"}
    slot = slot_map.get(m.text)
    if not slot: return
    v = config.SHIFT_SLOTS[slot]
    cnt = db("SELECT COUNT(*) FROM shifts WHERE date=? AND slot=?", (today(), slot), "one")[0]
    if cnt >= v["limit"]: bot_courier.send_message(m.chat.id, f"❌ {v['name']} — уже заполнено.", reply_markup=kb_shift_slots()); return
    already = db("SELECT id FROM shifts WHERE date=? AND slot=? AND courier_id=?", (today(), slot, cr[0]), "one")
    if already: bot_courier.send_message(m.chat.id, f"✅ Вы уже записаны на {v['name']}.", reply_markup=kb_shift_slots()); return
    db("INSERT INTO shifts (courier_id,date,slot,status) VALUES (?,?,?,'booked')", (cr[0], today(), slot))
    bot_courier.send_message(m.chat.id, f"✅ Вы записаны!\n━━━━━━━━━━━━━━━\n📅 {v['name']}\n🕐 {v['start']}–{v['end']}\n\n⚠️ Если не выйдете — штраф {config.SHIFT_PENALTY} ₽", reply_markup=kb_shift_slots())
    bot_admin.send_message(config.ADMIN_ID, f"📅 Новая заявка на смену\n\n🚚 {cr[2]}\n📅 {v['name']}\n🕐 {v['start']}–{v['end']}")

@bot_courier.message_handler(func=lambda m: m.text=="📋 Мои смены")
def cour_my_shifts(m):
    cr = db("SELECT * FROM couriers WHERE tg_id=?", (m.from_user.id,), "one")
    if not cr: return
    shifts = db("SELECT * FROM shifts WHERE courier_id=? AND date>=? ORDER BY date ASC, slot ASC LIMIT 20", (cr[0], today()), "all")
    if not shifts: bot_courier.send_message(m.chat.id, "📋 У вас нет записанных смен.", reply_markup=kb_shift_slots()); return
    txt = "📋 Мои смены\n━━━━━━━━━━━━━━━\n\n"
    for sh in shifts:
        v = config.SHIFT_SLOTS.get(sh[3], {})
        st_txt = config.SHIFT_STATUS.get(sh[4], sh[4])
        txt += f"📅 {sh[2]}\n{v.get('name','?')} ({v.get('start','?')}–{v.get('end','?')})\n{st_txt}\n\n"
    bot_courier.send_message(m.chat.id, txt, reply_markup=kb_shift_slots())

@bot_courier.message_handler(func=lambda m: m.text=="📊 Статистика")
def cour_stats(m):
    cr = db("SELECT * FROM couriers WHERE tg_id=?", (m.from_user.id,), "one")
    if not cr: return
    done = db("SELECT COUNT(*) FROM orders WHERE courier_id=? AND status='done'", (cr[0],), "one")[0]
    active = db("SELECT COUNT(*) FROM orders WHERE courier_id=? AND status IN ('going','delivering','at_client')", (cr[0],), "one")[0]
    sd = db("SELECT COUNT(*) FROM shifts WHERE courier_id=? AND status='done'", (cr[0],), "one")[0]
    sm = db("SELECT COUNT(*) FROM shifts WHERE courier_id=? AND status='missed'", (cr[0],), "one")[0]
    bot_courier.send_message(m.chat.id, f"📊 Моя статистика\n━━━━━━━━━━━━━━━\n\n⭐ Рейтинг: {cr[9]:.1f}\n✅ Доставок: {done}\n🚗 Активных: {active}\n💰 Баланс: {cr[7]:.2f} ₽\n\n📅 Смен: {sd}\n⚠️ Пропущено: {sm}")
    # ========== АДМИН ==========
@bot_admin.message_handler(commands=['start'])
def admin_start(m):
    if m.from_user.id != config.ADMIN_ID: bot_admin.send_message(m.chat.id, "⛔ Доступ запрещён."); return
    bot_admin.send_message(m.chat.id, f"👑 Админ-панель {config.SERVICE_NAME}\n━━━━━━━━━━━━━━━\n\n{config.ADMIN_NAME}, добро пожаловать!\n📍 {config.CITY}\n🕐 {config.WORK_HOURS}", reply_markup=kb_admin())

@bot_admin.message_handler(func=lambda m: m.text=="📝 Запросы" and m.from_user.id==config.ADMIN_ID)
def admin_requests_menu(m):
    sc = len(db("SELECT id FROM shops WHERE status='pending'", fetch="all"))
    cc = len(db("SELECT id FROM couriers WHERE status='pending'", fetch="all"))
    sh = len(db("SELECT id FROM shifts WHERE date=? AND status='booked'", (today(),), fetch="all"))
    wd = len(db("SELECT id FROM withdrawals WHERE status='pending'", fetch="all"))
    cn = len(db("SELECT id FROM orders WHERE status='cancel'", fetch="all"))
    bot_admin.send_message(m.chat.id, f"📝 ЗАПРОСЫ НА ОДОБРЕНИЕ\n━━━━━━━━━━━━━━━\n\n🏪 Магазины: {sc if sc else 'нет'}\n🚚 Курьеры: {cc if cc else 'нет'}\n📅 Смены: {sh if sh else 'нет'}\n💳 Выплаты: {wd if wd else 'нет'}\n❌ Отмены: {cn if cn else 'нет'}\n\nВыберите категорию:", reply_markup=kb_admin_req())

@bot_admin.message_handler(func=lambda m: m.text=="⬅️ Назад" and m.from_user.id==config.ADMIN_ID)
def admin_back(m): bot_admin.send_message(m.chat.id, "Главное меню:", reply_markup=kb_admin())

@bot_admin.message_handler(func=lambda m: m.text=="🏪 Заявки магазинов" and m.from_user.id==config.ADMIN_ID)
def admin_req_shops(m):
    shops = db("SELECT * FROM shops WHERE status='pending'", fetch="all")
    if not shops: bot_admin.send_message(m.chat.id, "🏪 Заявки магазинов\n━━━━━━━━━━━━━━━\n\n✅ Сейчас заявок НЕТ.", reply_markup=kb_admin_req()); return
    bot_admin.send_message(m.chat.id, f"🏪 Заявок: {len(shops)}")
    for s in shops:
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("✅ Одобрить", callback_data=f"shop_ok_{s[0]}"), types.InlineKeyboardButton("❌ Отклонить", callback_data=f"shop_no_{s[0]}"))
        bot_admin.send_message(m.chat.id, f"🏪 МАГАЗИН\n━━━━━━━━━━━━━━━\nНазвание: {s[2]}\n📍 {s[3]}\n📞 {s[4]}\n✈️ {s[5]}\n📱 {s[6]}\n👤 {s[7]}", reply_markup=kb)

@bot_admin.message_handler(func=lambda m: m.text=="🚚 Заявки курьеров" and m.from_user.id==config.ADMIN_ID)
def admin_req_cour(m):
    crs = db("SELECT * FROM couriers WHERE status='pending'", fetch="all")
    if not crs: bot_admin.send_message(m.chat.id, "🚚 Заявки курьеров\n━━━━━━━━━━━━━━━\n\n✅ Сейчас заявок НЕТ.", reply_markup=kb_admin_req()); return
    bot_admin.send_message(m.chat.id, f"🚚 Заявок: {len(crs)}")
    for c in crs:
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("✅ Одобрить", callback_data=f"cour_ok_{c[0]}"), types.InlineKeyboardButton("❌ Отклонить", callback_data=f"cour_no_{c[0]}"))
        bot_admin.send_message(m.chat.id, f"🚚 КУРЬЕР\n━━━━━━━━━━━━━━━\n👤 {c[2]}\n📞 {c[3]}\n📍 {c[4]}\n🚗 {c[5]}\n💳 {c[6]}", reply_markup=kb)

@bot_admin.message_handler(func=lambda m: m.text=="📅 Заявки смен" and m.from_user.id==config.ADMIN_ID)
def admin_req_shifts(m):
    shifts = db("SELECT s.*, c.name FROM shifts s JOIN couriers c ON c.id=s.courier_id WHERE s.date=? AND s.status='booked'", (today(),), fetch="all")
    if not shifts: bot_admin.send_message(m.chat.id, "📅 Заявки смен\n━━━━━━━━━━━━━━━\n\n✅ На сегодня заявок НЕТ.", reply_markup=kb_admin_req()); return
    bot_admin.send_message(m.chat.id, f"📅 Заявок на смену: {len(shifts)}")
    for s in shifts:
        v = config.SHIFT_SLOTS.get(s[3], {})
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("✅ Подтвердить", callback_data=f"shift_ok_{s[0]}"), types.InlineKeyboardButton("❌ Отменить", callback_data=f"shift_no_{s[0]}"))
        bot_admin.send_message(m.chat.id, f"📅 СМЕНА\n━━━━━━━━━━━━━━━\n🚚 {s[5]}\n{v.get('name','?')} ({v.get('start','?')}–{v.get('end','?')})", reply_markup=kb)

@bot_admin.message_handler(func=lambda m: m.text=="💳 Заявки выплат" and m.from_user.id==config.ADMIN_ID)
def admin_req_wd(m):
    ws = db("SELECT w.*, c.name, c.phone, c.card FROM withdrawals w JOIN couriers c ON c.id=w.courier_id WHERE w.status='pending'", fetch="all")
    if not ws: bot_admin.send_message(m.chat.id, "💳 Заявки выплат\n━━━━━━━━━━━━━━━\n\n✅ Сейчас заявок НЕТ.", reply_markup=kb_admin_req()); return
    bot_admin.send_message(m.chat.id, f"💳 Заявок: {len(ws)}")
    for w in ws:
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("✅ Подтвердить", callback_data=f"wok_{w[0]}"), types.InlineKeyboardButton("❌ Отклонить", callback_data=f"wno_{w[0]}"))
        bot_admin.send_message(m.chat.id, f"💳 ЗАЯВКА #{w[0]}\n━━━━━━━━━━━━━━━\n🚚 {w[5]}\n📞 {w[6]}\n💰 {w[2]:.2f} ₽\n💳 {w[3]}", reply_markup=kb)

@bot_admin.message_handler(func=lambda m: m.text=="❌ Отмены заявок" and m.from_user.id==config.ADMIN_ID)
def admin_req_cancel(m):
    cancels = db("SELECT * FROM orders WHERE status='cancel' ORDER BY id DESC LIMIT 20", fetch="all")
    if not cancels: bot_admin.send_message(m.chat.id, "❌ Отмены заявок\n━━━━━━━━━━━━━━━\n\n✅ Отменённых НЕТ.", reply_markup=kb_admin_req()); return
    txt = f"❌ Отменённые заявки: {len(cancels)}\n━━━━━━━━━━━━━━━\n\n"
    for o in cancels[:10]: txt += f"#{o[0]} — {o[3]}\n🎯 {o[5][:40]}\n💰 {o[11]:.2f} ₽\n\n"
    bot_admin.send_message(m.chat.id, txt, reply_markup=kb_admin_req())

@bot_admin.message_handler(func=lambda m: m.text=="🏪 Магазины" and m.from_user.id==config.ADMIN_ID)
def admin_shops(m):
    shops = db("SELECT * FROM shops WHERE status='active'", fetch="all")
    if not shops: bot_admin.send_message(m.chat.id, "🏪 Магазины\n━━━━━━━━━━━━━━━\n\n😔 Активных НЕТ."); return
    tot=0; rev=0.0; cm=0.0
    for s in shops:
        orders = db("SELECT * FROM orders WHERE shop_id=?", (s[0],), "all")
        r = sum(o[11] for o in orders if o[11]); c = sum(o[12] for o in orders if o[12])
        tot += len(orders); rev += r; cm += c
        bot_admin.send_message(m.chat.id, f"🏪 {s[2]}\n━━━━━━━━━━━━━━━\n📍 {s[3]}\n📞 {s[4]}\n👤 {s[7]}\n\n📦 Заявок: {len(orders)}\n💰 Оборот: {r:.2f} ₽\n💵 Комиссия: {c:.2f} ₽")
    bot_admin.send_message(m.chat.id, f"📊 ИТОГО ПО МАГАЗИНАМ\n━━━━━━━━━━━━━━━\n🏪 {len(shops)}\n📦 {tot}\n💰 {rev:.2f} ₽\n💵 {cm:.2f} ₽")

@bot_admin.message_handler(func=lambda m: m.text=="🚚 Курьеры" and m.from_user.id==config.ADMIN_ID)
def admin_cour(m):
    crs = db("SELECT * FROM couriers WHERE status='active'", fetch="all")
    if not crs: bot_admin.send_message(m.chat.id, "🚚 Курьеры\n━━━━━━━━━━━━━━━\n\n😔 Активных НЕТ."); return
    td=0; te=0.0; tb=0.0
    for c in crs:
        d = db("SELECT COUNT(*) FROM orders WHERE courier_id=? AND status='done'", (c[0],), "one")[0]
        e = db("SELECT COALESCE(SUM(courier_fee),0) FROM orders WHERE courier_id=? AND status='done'", (c[0],), "one")[0]
        td+=d; te+=e; tb+=c[7]
        sd = db("SELECT COUNT(*) FROM shifts WHERE courier_id=? AND status='done'", (c[0],), "one")[0]
        sm = db("SELECT COUNT(*) FROM shifts WHERE courier_id=? AND status='missed'", (c[0],), "one")[0]
        loc_txt = "📍 нет гео"; map_btn = None
        if c[10]: loc_txt = f"📍 {c[10]:.5f}, {c[11]:.5f}\n🕐 {c[12]}"; map_btn = geo_link(c[10], c[11])
        txt = f"🚚 {c[2]}\n━━━━━━━━━━━━━━━\n📞 {c[3]}\n📍 {c[4]}\n🚗 {c[5]}\n\n✅ Доставок: {d}\n💰 Заработал: {e:.2f} ₽\n💵 Баланс: {c[7]:.2f} ₽\n\n📅 Смен: {sd} | ⚠️ Пропущено: {sm}\n\n{loc_txt}"
        if map_btn:
            kb = types.InlineKeyboardMarkup(); kb.add(types.InlineKeyboardButton("🗺 Открыть на карте", url=map_btn))
            bot_admin.send_message(m.chat.id, txt, reply_markup=kb)
        else: bot_admin.send_message(m.chat.id, txt)
    bot_admin.send_message(m.chat.id, f"📊 ИТОГО ПО КУРЬЕРАМ\n━━━━━━━━━━━━━━━\n🚚 {len(crs)}\n✅ {td}\n💰 {te:.2f} ₽\n💵 {tb:.2f} ₽")

@bot_admin.message_handler(func=lambda m: m.text=="💰 Финансы" and m.from_user.id==config.ADMIN_ID)
def admin_fin(m):
    oa = db("SELECT COUNT(*) FROM orders", fetch="one")[0]
    sc = db("SELECT COUNT(*) FROM shops WHERE status='active'", fetch="one")[0]
    cc = db("SELECT COUNT(*) FROM couriers WHERE status='active'", fetch="one")[0]
    if oa == 0 and sc == 0 and cc == 0: bot_admin.send_message(m.chat.id, "💰 Финансы\n━━━━━━━━━━━━━━━\n\n📊 Пока нет данных."); return
    r = db("SELECT COUNT(*), COALESCE(SUM(delivery_price),0), COALESCE(SUM(commission),0), COALESCE(SUM(courier_fee),0) FROM orders WHERE payment_status='confirmed'", fetch="one")
    od = db("SELECT COUNT(*) FROM orders WHERE status='done'", fetch="one")[0]
    oact = db("SELECT COUNT(*) FROM orders WHERE status IN ('going','delivering','at_client')", fetch="one")[0]
    po = db("SELECT COALESCE(SUM(amount),0) FROM withdrawals WHERE status='approved'", fetch="one")[0]
    cb = db("SELECT COALESCE(SUM(balance),0) FROM couriers", fetch="one")[0]
    pen = db("SELECT COALESCE(SUM(penalty),0) FROM shifts", fetch="one")[0]
    txt = "💰 Финансы\n━━━━━━━━━━━━━━━\n\n📦 ЗАКАЗЫ\n"
    if oa == 0: txt += "НЕТ заказов\n"
    else: txt += f"Всего: {oa}\n✅ Доставлено: {od}\n🚚 В работе: {oact}\n"
    txt += f"\n━━━━━━━━━━━━━━━\n🏪 Магазины: {sc if sc else 'НЕТ'}\n🚚 Курьеры: {cc if cc else 'НЕТ'}\n"
    txt += "\n━━━━━━━━━━━━━━━\n💵 МОИ ДОХОДЫ\n"
    if r[2] > 0: txt += f"Комиссия: {r[2]:.2f} ₽\nОт магазинов: {r[1]:.2f} ₽\n"
    else: txt += "НЕТ доходов\n"
    if pen > 0: txt += f"⚠️ Штрафы: {pen:.2f} ₽\n"
    txt += "\n━━━━━━━━━━━━━━━\n🚚 КУРЬЕРАМ\n"
    if cb > 0 or po > 0 or r[3] > 0: txt += f"Должен: {cb:.2f} ₽\nВыплачено: {po:.2f} ₽\nВсего: {r[3]:.2f} ₽\n"
    else: txt += "Выплат НЕТ\n"
    txt += f"\n━━━━━━━━━━━━━━━\n💳 КАРТА\n{config.CARD_NUMBER}\n{config.CARD_HOLDER}\n{config.BANK_NAME}"
    bot_admin.send_message(m.chat.id, txt)

@bot_admin.message_handler(func=lambda m: m.text=="💳 Выплаты" and m.from_user.id==config.ADMIN_ID)
def admin_wd(m):
    ws = db("SELECT w.*, c.name, c.phone, c.card FROM withdrawals w JOIN couriers c ON c.id=w.courier_id WHERE w.status='pending'", fetch="all")
    bl = db("SELECT name, balance, card FROM couriers WHERE status='active' AND balance>0 ORDER BY balance DESC", fetch="all")
    if not ws and not bl: bot_admin.send_message(m.chat.id, "💳 Выплаты\n━━━━━━━━━━━━━━━\n\n✅ Заявок НЕТ.\n💰 Балансы пусты."); return
    txt = "💳 Выплаты курьерам\n━━━━━━━━━━━━━━━\n\n"
    if ws: txt += f"📤 Заявок: {len(ws)}\n"
    else: txt += "📤 Заявок: НЕТ\n"
    if bl:
        tb = sum(b[1] for b in bl)
        txt += f"\n💰 Всего должен: {tb:.2f} ₽\n\n"
        for b in bl: txt += f"• {b[0]} — {b[1]:.2f} ₽\n  💳 {b[2]}\n"
    else: txt += "\n💰 Никому не должен.\n"
    bot_admin.send_message(m.chat.id, txt)
    for w in ws:
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("✅ Подтвердить", callback_data=f"wok_{w[0]}"), types.InlineKeyboardButton("❌ Отклонить", callback_data=f"wno_{w[0]}"))
        bot_admin.send_message(m.chat.id, f"📤 ВЫВОД #{w[0]}\n━━━━━━━━━━━━━━━\n🚚 {w[5]}\n📞 {w[6]}\n💰 {w[2]:.2f} ₽\n💳 {w[3]}", reply_markup=kb)

@bot_admin.message_handler(func=lambda m: m.text=="📅 Смены" and m.from_user.id==config.ADMIN_ID)
def admin_shifts(m):
    crs = db("SELECT COUNT(*) FROM couriers WHERE status='active'", fetch="one")[0]
    if crs == 0: bot_admin.send_message(m.chat.id, "📅 Смены\n━━━━━━━━━━━━━━━\n\n😔 Нет активных курьеров."); return
    txt = f"📅 Смены на {today()}\n━━━━━━━━━━━━━━━\n\n"
    total = 0; has_any = False
    for k, v in config.SHIFT_SLOTS.items():
        cnt = db("SELECT COUNT(*) FROM shifts WHERE date=? AND slot=?", (today(), k), "one")[0]
        free = v["limit"] - cnt; total += cnt
        if cnt > 0: has_any = True
        txt += f"{v['name']} ({v['start']}–{v['end']})\n   Записано: {cnt}/{v['limit']} — "
        txt += f"✅ {free}\n\n" if free > 0 else "❌ заполнено\n\n"
    if not has_any: txt += "👥 На смену никто не записан."
    else: txt += f"👥 Всего на смене: {total}"
    bot_admin.send_message(m.chat.id, txt)

@bot_admin.callback_query_handler(func=lambda c: c.data.startswith("shop_ok_"))
def cb_shop_ok(c):
    if c.from_user.id != config.ADMIN_ID: return
    sid = int(c.data.split("_")[2]); db("UPDATE shops SET status='active' WHERE id=?", (sid,))
    s = db("SELECT tg_id,name FROM shops WHERE id=?", (sid,), "one")
    bot_admin.edit_message_text(f"✅ Магазин «{s[1]}» ОДОБРЕН", c.message.chat.id, c.message.message_id)
    try: bot_shop.send_message(s[0], "✅ Ваш магазин одобрен!\n\nОтправьте /start")
    except: pass

@bot_admin.callback_query_handler(func=lambda c: c.data.startswith("shop_no_"))
def cb_shop_no(c):
    if c.from_user.id != config.ADMIN_ID: return
    sid = int(c.data.split("_")[2]); db("UPDATE shops SET status='blocked' WHERE id=?", (sid,))
    s = db("SELECT tg_id,name FROM shops WHERE id=?", (sid,), "one")
    bot_admin.edit_message_text(f"❌ Магазин «{s[1]}» ОТКЛОНЁН", c.message.chat.id, c.message.message_id)
    try: bot_shop.send_message(s[0], "❌ Ваш магазин отклонён.")
    except: pass

@bot_admin.callback_query_handler(func=lambda c: c.data.startswith("cour_ok_"))
def cb_cour_ok(c):
    if c.from_user.id != config.ADMIN_ID: return
    cid = int(c.data.split("_")[2]); db("UPDATE couriers SET status='active' WHERE id=?", (cid,))
    cc = db("SELECT tg_id,name FROM couriers WHERE id=?", (cid,), "one")
    bot_admin.edit_message_text(f"✅ Курьер «{cc[1]}» ОДОБРЕН", c.message.chat.id, c.message.message_id)
    try: bot_courier.send_message(cc[0], "✅ Вы одобрены!\n\nОтправьте /start")
    except: pass

@bot_admin.callback_query_handler(func=lambda c: c.data.startswith("cour_no_"))
def cb_cour_no(c):
    if c.from_user.id != config.ADMIN_ID: return
    cid = int(c.data.split("_")[2]); db("UPDATE couriers SET status='blocked' WHERE id=?", (cid,))
    cc = db("SELECT tg_id,name FROM couriers WHERE id=?", (cid,), "one")
    bot_admin.edit_message_text(f"❌ Курьер «{cc[1]}» ОТКЛОНЁН", c.message.chat.id, c.message.message_id)
    try: bot_courier.send_message(cc[0], "❌ Вас отклонили.")
    except: pass

@bot_admin.callback_query_handler(func=lambda c: c.data.startswith("shift_ok_"))
def cb_shift_ok(c):
    if c.from_user.id != config.ADMIN_ID: return
    sid = int(c.data.split("_")[2])
    sh = db("SELECT s.*, c.tg_id, c.name FROM shifts s JOIN couriers c ON c.id=s.courier_id WHERE s.id=?", (sid,), "one")
    if not sh: bot_admin.answer_callback_query(c.id, "Не найдено"); return
    v = config.SHIFT_SLOTS.get(sh[3], {})
    bot_admin.edit_message_text(f"✅ Смена подтверждена\n🚚 {sh[7]}\n{v.get('name','?')}", c.message.chat.id, c.message.message_id)
    try: bot_courier.send_message(sh[6], f"✅ Ваша смена подтверждена\n\n📅 {v.get('name','?')}\n🕐 {v.get('start','?')}–{v.get('end','?')}")
    except: pass
    bot_admin.answer_callback_query(c.id)

@bot_admin.callback_query_handler(func=lambda c: c.data.startswith("shift_no_"))
def cb_shift_no(c):
    if c.from_user.id != config.ADMIN_ID: return
    sid = int(c.data.split("_")[2])
    sh = db("SELECT s.*, c.tg_id FROM shifts s JOIN couriers c ON c.id=s.courier_id WHERE s.id=?", (sid,), "one")
    if not sh: bot_admin.answer_callback_query(c.id); return
    db("DELETE FROM shifts WHERE id=?", (sid,))
    bot_admin.edit_message_text("❌ Смена отменена", c.message.chat.id, c.message.message_id)
    try: bot_courier.send_message(sh[6], "❌ Ваша заявка на смену отклонена админом.")
    except: pass
    bot_admin.answer_callback_query(c.id)

@bot_admin.callback_query_handler(func=lambda c: c.data.startswith("wok_"))
def cb_wok(c):
    if c.from_user.id != config.ADMIN_ID: return
    wid = int(c.data.split("_")[1]); w = db("SELECT * FROM withdrawals WHERE id=?", (wid,), "one")
    if not w: bot_admin.answer_callback_query(c.id); return
    db("UPDATE withdrawals SET status='approved' WHERE id=?", (wid,))
    db("UPDATE couriers SET balance=balance-? WHERE id=?", (w[2], w[1]))
    ci = db("SELECT tg_id FROM couriers WHERE id=?", (w[1],), "one")
    bot_admin.edit_message_text(f"✅ Выплачено {w[2]:.2f} ₽", c.message.chat.id, c.message.message_id)
    try: bot_courier.send_message(ci[0], f"✅ Вывод подтверждён!\n\n💰 {w[2]:.2f} ₽\n💳 {w[3]}\n\nПридёт в течение 24 часов.")
    except: pass
    bot_admin.answer_callback_query(c.id)

@bot_admin.callback_query_handler(func=lambda c: c.data.startswith("wno_"))
def cb_wno(c):
    if c.from_user.id != config.ADMIN_ID: return
    wid = int(c.data.split("_")[1]); w = db("SELECT * FROM withdrawals WHERE id=?", (wid,), "one")
    db("UPDATE withdrawals SET status='rejected' WHERE id=?", (wid,))
    bot_admin.edit_message_text(f"❌ Вывод #{wid} ОТКЛОНЁН", c.message.chat.id, c.message.message_id)
    if w:
        ci = db("SELECT tg_id FROM couriers WHERE id=?", (w[1],), "one")
        try: bot_courier.send_message(ci[0], f"❌ Заявка на вывод {w[2]:.2f} ₽ отклонена.")
        except: pass
    bot_admin.answer_callback_query(c.id)

# ========== АВТОШТРАФ ==========
def check_shifts():
    while True:
        try:
            time.sleep(60)
            shifts = db("SELECT s.*, c.tg_id, c.name, c.balance FROM shifts s JOIN couriers c ON c.id=s.courier_id WHERE s.date=? AND s.status='booked'", (today(),), fetch="all")
            for sh in shifts:
                slot = config.SHIFT_SLOTS.get(sh[3])
                if not slot: continue
                start_h, start_m = map(int, slot["start"].split(":"))
                now_dt = datetime.now()
                start_dt = now_dt.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
                delta = (now_dt - start_dt).total_seconds() / 60
                if delta > config.SHIFT_GRACE_MIN:
                    db("UPDATE shifts SET status='missed', penalty=? WHERE id=?", (config.SHIFT_PENALTY, sh[0]))
                    db("UPDATE couriers SET balance=balance-? WHERE id=?", (config.SHIFT_PENALTY, sh[1]))
                    try: bot_courier.send_message(sh[5], f"⚠️ ШТРАФ за невыход\n━━━━━━━━━━━━━━━\n📅 {slot['name']}\n🕐 {slot['start']}–{slot['end']}\n\n💰 Списано: {config.SHIFT_PENALTY} ₽\n💵 Баланс: {sh[7] - config.SHIFT_PENALTY:.2f} ₽")
                    except: pass
                    try: bot_admin.send_message(config.ADMIN_ID, f"⚠️ АВТОШТРАФ\n━━━━━━━━━━━━━━━\n🚚 {sh[6]}\n📅 {slot['name']}\n💰 {config.SHIFT_PENALTY} ₽")
                    except: pass
        except Exception as e: print(f"❌ check_shifts: {e}")

# ========== ЗАПУСК ==========
def run_bot(bot, name):
    print(f"🚀 {name}")
    while True:
        try: bot.infinity_polling(timeout=30, long_polling_timeout=20)
        except Exception as e:
            print(f"❌ {name}: {e}"); time.sleep(5)
            # ========== ГЛОБАЛЬНАЯ ОТМЕНА ==========
@bot_shop.message_handler(func=lambda m: m.text=="❌ Отмена")
def shop_cancel_global(m):
    if m.from_user.id in shop_reg: del shop_reg[m.from_user.id]
    if m.from_user.id in order_reg: del order_reg[m.from_user.id]
    bot_shop.send_message(m.chat.id, "Отменено.", reply_markup=kb_shop())

@bot_courier.message_handler(func=lambda m: m.text=="❌ Отмена")
def cour_cancel_global(m):
    if m.from_user.id in cour_reg: del cour_reg[m.from_user.id]
    if m.from_user.id in withdraw_reg: del withdraw_reg[m.from_user.id]
    bot_courier.send_message(m.chat.id, "Отменено.", reply_markup=kb_courier())


if __name__ == "__main__":
    print("📦 Инициализация БД...")
    db_init()
    print("✅ База готова")
    for b, n in [(bot_shop,"Магазин"),(bot_courier,"Курьер"),(bot_admin,"Админ"),(bot_client,"Клиент")]:
        threading.Thread(target=run_bot, args=(b, n), daemon=True).start()
    threading.Thread(target=check_shifts, daemon=True).start()
    print("⏰ Автоштраф запущен")
    print("🎉 4 бота запущены!")
    while True: time.sleep(60)
        
    
