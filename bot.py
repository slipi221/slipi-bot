# -*- coding: utf-8 -*-
import sqlite3, threading, time
from datetime import datetime, date
import telebot
from telebot import types
import config

DB = "/app/data/flower.db"

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
    c.execute("CREATE TABLE IF NOT EXISTS shops (id INTEGER PRIMARY KEY AUTOINCREMENT, tg_id INTEGER UNIQUE, name TEXT, address TEXT, phone TEXT, telegram TEXT, vk TEXT, owner_name TEXT, status TEXT DEFAULT 'pending', rating REAL DEFAULT 0, reviews_count INTEGER DEFAULT 0, created_at TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS couriers (id INTEGER PRIMARY KEY AUTOINCREMENT, tg_id INTEGER UNIQUE, name TEXT, phone TEXT, city TEXT, transport TEXT, card TEXT, balance REAL DEFAULT 0, status TEXT DEFAULT 'pending', courier_state TEXT DEFAULT 'off', rating REAL DEFAULT 0, reviews_count INTEGER DEFAULT 0, lat REAL, lon REAL, loc_time TEXT, created_at TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY AUTOINCREMENT, shop_id INTEGER, courier_id INTEGER, shop_name TEXT, address_from TEXT, address_to TEXT, client_name TEXT, client_phone TEXT, client_tg_id INTEGER, delivery_time TEXT, order_price REAL, delivery_price REAL, commission REAL, courier_fee REAL, comment TEXT, status TEXT DEFAULT 'new', payment_status TEXT DEFAULT 'pending', created_at TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS shifts (id INTEGER PRIMARY KEY AUTOINCREMENT, courier_id INTEGER, date TEXT, slot TEXT, status TEXT DEFAULT 'booked', checked_in TEXT, penalty REAL DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS withdrawals (id INTEGER PRIMARY KEY AUTOINCREMENT, courier_id INTEGER, amount REAL, card TEXT, status TEXT DEFAULT 'pending', created_at TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS reviews (id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER, from_tg_id INTEGER, from_role TEXT, target_type TEXT, target_id INTEGER, rating INTEGER, comment TEXT, created_at TEXT)")
    con.commit(); con.close()

bot_client = telebot.TeleBot(config.CLIENT_TOKEN)
bot_shop = telebot.TeleBot(config.SHOP_TOKEN)
bot_courier = telebot.TeleBot(config.COURIER_TOKEN)
bot_admin = telebot.TeleBot(config.ADMIN_TOKEN)

shop_reg, cour_reg, order_reg, withdraw_reg = {}, {}, {}, {}
review_reg = {}
shop_preview = {}

def kb_shop():
    k = types.ReplyKeyboardMarkup(resize_keyboard=True)
    k.row("🆕 Создать заявку")
    k.row("📋 Мои заявки", "📊 Статистика")
    k.row("⭐ Отзывы", "⚙️ Настройки")
    return k

def kb_courier():
    k = types.ReplyKeyboardMarkup(resize_keyboard=True)
    k.row("📋 Свободные заявки")
    k.row("🚗 Мои заказы", "💰 Заработок")
    k.row("🟢 Статус", "📅 Смены")
    k.row("📍 Гео", "📊 Статистика")
    return k

def kb_courier_status():
    k = types.ReplyKeyboardMarkup(resize_keyboard=True)
    k.row("🟢 На смене", "☕ Перерыв")
    k.row("⚪ Не на смене", "⬅️ Назад")
    return k

def kb_admin():
    k = types.ReplyKeyboardMarkup(resize_keyboard=True)
    k.row("📝 Запросы")
    k.row("🏪 Магазины", "🚚 Курьеры")
    k.row("💰 Финансы", "💳 Выплаты")
    k.row("📅 Смены", "⭐ Отзывы")
    k.row("🔒 Доступ", "📜 Логи")
    return k

def kb_admin_req():
    k = types.ReplyKeyboardMarkup(resize_keyboard=True)
    k.row("🏪 Заявки магазинов")
    k.row("🚚 Заявки курьеров")
    k.row("📅 Заявки смен")
    k.row("💳 Заявки выплат")
    k.row("❌ Отмены заявок")
    k.row("⬅️ Назад")
    return k

def kb_client():
    k = types.ReplyKeyboardMarkup(resize_keyboard=True)
    k.row("🏪 Магазины")
    k.row("ℹ️ О сервисе")
    return k

def kb_cancel():
    k = types.ReplyKeyboardMarkup(resize_keyboard=True)
    k.row("❌ Отмена")
    return k

def kb_shift_slots():
    k = types.ReplyKeyboardMarkup(resize_keyboard=True)
    k.row("🌅 Утренняя 7-15")
    k.row("☀️ Дневная 9-18")
    k.row("🌆 Вечерняя 15-23")
    k.row("🌙 Ночная 18-00")
    k.row("📋 Мои смены")
    k.row("⬅️ Назад")
    return k

def kb_rating(target, order_id):
    k = types.InlineKeyboardMarkup()
    k.add(types.InlineKeyboardButton("1⭐", callback_data=f"rate_{target}_{order_id}_1"),
          types.InlineKeyboardButton("2⭐", callback_data=f"rate_{target}_{order_id}_2"),
          types.InlineKeyboardButton("3⭐", callback_data=f"rate_{target}_{order_id}_3"),
          types.InlineKeyboardButton("4⭐", callback_data=f"rate_{target}_{order_id}_4"),
          types.InlineKeyboardButton("5⭐", callback_data=f"rate_{target}_{order_id}_5"))
    return k

def is_cancel(m): return m.text == "❌ Отмена"
def geo_link(lat, lon): return f"https://yandex.ru/maps/?pt={lon},{lat}&z=17&l=map"

def log(msg):
    try: bot_admin.send_message(config.ADMIN_ID, f"📜 {msg}")
    except: pass

def add_review(order_id, from_tg_id, from_role, target_type, target_id, rating, comment=""):
    db("INSERT INTO reviews (order_id, from_tg_id, from_role, target_type, target_id, rating, comment, created_at) VALUES (?,?,?,?,?,?,?,?)",
       (order_id, from_tg_id, from_role, target_type, target_id, rating, comment, now()))
    if target_type == "shop":
        r = db("SELECT AVG(rating), COUNT(*) FROM reviews WHERE target_type='shop' AND target_id=?", (target_id,), "one")
        db("UPDATE shops SET rating=?, reviews_count=? WHERE id=?", (round(r[0], 2), r[1], target_id))
    elif target_type == "courier":
        r = db("SELECT AVG(rating), COUNT(*) FROM reviews WHERE target_type='courier' AND target_id=?", (target_id,), "one")
        db("UPDATE couriers SET rating=?, reviews_count=? WHERE id=?", (round(r[0], 2), r[1], target_id))

# ===== КЛИЕНТ =====
@bot_client.message_handler(commands=['start'])
def client_start(m):
    bot_client.send_message(m.chat.id,
        "🌸 Добро пожаловать в SLIPI\n"
        "━━━━━━━━━━━━━━━\n\n"
        "✨ Живые цветы с доставкой\n"
        f"📍 Город: {config.CITY}\n"
        f"🕐 Работаем: {config.WORK_HOURS}\n\n"
        "Выберите действие 👇",
        reply_markup=kb_client())

@bot_client.message_handler(func=lambda m: m.text=="🏪 Магазины")
def client_shops(m):
    shops = db("SELECT id, name, address, phone, telegram, vk, rating, reviews_count FROM shops WHERE status='active'", fetch="all")
    if not shops:
        bot_client.send_message(m.chat.id, "😔 Пока нет активных магазинов.")
        return
    bot_client.send_message(m.chat.id, f"🏪 Доступно магазинов: {len(shops)}")
    for s in shops:
        sid, name, addr, phone, tg, vk, rating, cnt = s
        txt = f"🌸 {name}\n━━━━━━━━━━━━━━━\n📍 {addr}\n📞 {phone}\n"
        if tg: txt += f"✈️ {tg}\n"
        if vk: txt += f"📱 {vk}\n"
        if rating and cnt:
            stars = "⭐" * int(rating)
            txt += f"\n{stars} {rating} ({cnt})\n"
        bot_client.send_message(m.chat.id, txt)

@bot_client.message_handler(func=lambda m: m.text=="ℹ️ О сервисе")
def client_about(m):
    bot_client.send_message(m.chat.id,
        f"🌸 {config.SERVICE_NAME}\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"🚚 Доставка цветов\n"
        f"📍 {config.CITY}\n"
        f"🕐 {config.WORK_HOURS}\n"
        f"📅 {config.WORK_DAYS}\n\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📞 {config.SUPPORT_PHONE}\n"
        f"✈️ {config.SERVICE_VK_TG}\n"
        f"📱 {config.SERVICE_VK}")

@bot_client.callback_query_handler(func=lambda c: c.data.startswith("rate_"))
def cb_rate_client(c):
    parts = c.data.split("_")
    target = parts[1]; order_id = int(parts[2]); rating = int(parts[3])
    uid = c.from_user.id
    if uid not in review_reg:
        bot_client.answer_callback_query(c.id, "Время истекло"); return
    o = db("SELECT * FROM orders WHERE id=?", (order_id,), "one")
    if not o: bot_client.answer_callback_query(c.id); return
    if target == "shop":
        add_review(order_id, uid, "client", "shop", o[1], rating)
        review_reg[uid]["shop"] = rating; review_reg[uid]["step"] = "courier"
        bot_client.edit_message_text(f"🌸 Магазин: {rating}⭐", c.message.chat.id, c.message.message_id)
        if o[2]:
            bot_client.send_message(uid, "🚚 Оцените курьера:", reply_markup=kb_rating("courier", order_id))
        else:
            review_reg[uid]["step"] = "service"
            bot_client.send_message(uid, "✨ Оцените сервис:", reply_markup=kb_rating("service", order_id))
    elif target == "courier":
        if o[2]: add_review(order_id, uid, "client", "courier", o[2], rating)
        review_reg[uid]["courier"] = rating; review_reg[uid]["step"] = "service"
        bot_client.edit_message_text(f"🚚 Курьер: {rating}⭐", c.message.chat.id, c.message.message_id)
        bot_client.send_message(uid, "✨ Оцените сервис:", reply_markup=kb_rating("service", order_id))
    elif target == "service":
        add_review(order_id, uid, "client", "service", 0, rating)
        review_reg[uid]["service"] = rating; review_reg[uid]["step"] = "comment"
        bot_client.edit_message_text(f"✨ Сервис: {rating}⭐", c.message.chat.id, c.message.message_id)
        bot_client.send_message(uid, "💬 Напишите комментарий или /skip", reply_markup=kb_cancel())
    bot_client.answer_callback_query(c.id, f"Оценка {rating}")

@bot_client.message_handler(func=lambda m: m.from_user.id in review_reg and review_reg[m.from_user.id].get("step") == "comment")
def cb_review_comment(m):
    uid = m.from_user.id
    text = "" if (is_cancel(m) or m.text.startswith("/skip")) else m.text
    order_id = review_reg[uid].get("order_id")
    if text and order_id:
        o = db("SELECT * FROM orders WHERE id=?", (order_id,), "one")
        if o:
            if o[1]: add_review(order_id, uid, "client", "shop", o[1], review_reg[uid].get("shop", 5), text)
            if o[2]: add_review(order_id, uid, "client", "courier", o[2], review_reg[uid].get("courier", 5), text)
    del review_reg[uid]
    bot_client.send_message(m.chat.id, "🙏 Спасибо за отзыв!", reply_markup=kb_client())
# ===== МАГАЗИН =====
@bot_shop.message_handler(commands=['start'])
def shop_start(m):
    s = db("SELECT * FROM shops WHERE tg_id=?", (m.from_user.id,), "one")
    if not s:
        bot_shop.send_message(m.chat.id,
            "👋 Привет!\n\n"
            "🌸 Станьте партнёром сети SLIPI!\n\n"
            "Отправьте /register")
        return
    if s[8]=="pending": bot_shop.send_message(m.chat.id, "⏳ Заявка на рассмотрении.")
    elif s[8]=="blocked": bot_shop.send_message(m.chat.id, "🚫 Доступ закрыт. Обратитесь к админу.")
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
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("📝 Зарегистрироваться", callback_data="start_register"))
        bot_shop.send_message(m.chat.id, "Отменено. Чтобы начать работу - зарегистрируйтесь.", reply_markup=kb)
        return
    st = shop_reg[m.from_user.id]; s = st["step"]; d = st["d"]
    if s == "phone":
        t = m.text.replace(" ", "").replace("-", "").replace("(", "").replace(")", "").replace("+", "")
        if not t.isdigit() or len(t) < 10 or len(t) > 15:
            bot_shop.send_message(m.chat.id, "❌ Неверный номер. Введите 10-15 цифр. Пример: 89917929251")
            return
        d[s] = m.text.strip(); st["step"] = "telegram"
        bot_shop.send_message(m.chat.id, "✅ Телефон принят\n\nШаг 4/6: Ваш Telegram. Отправьте @username или /skip")
        return
    if s == "telegram":
        if m.text.startswith("/skip"): tg = f"@{m.from_user.username}" if m.from_user.username else "нет"
        else: tg = m.text if m.text.startswith("@") else "@" + m.text
        d[s] = tg; st["step"] = "vk"
        bot_shop.send_message(m.chat.id, "Шаг 5/6: Ваш ВКонтакте")
        return
    d[s] = m.text
    if s == "name":
        st["step"] = "address"; bot_shop.send_message(m.chat.id, "Шаг 2/6: Адрес магазина")
    elif s == "address":
        st["step"] = "phone"; bot_shop.send_message(m.chat.id, "Шаг 3/6: Телефон. Формат: 8XXXXXXXXXX (11 цифр)")
    elif s == "vk":
        st["step"] = "owner_name"; bot_shop.send_message(m.chat.id, "Шаг 6/6: Ваше имя")
    elif s == "owner_name":
        shop_preview[m.from_user.id] = d
        del shop_reg[m.from_user.id]
        show_shop_preview(m.chat.id, m.from_user.id)

def show_shop_preview(chat_id, uid):
    d = shop_preview.get(uid)
    if not d: return
    txt = (
        f"🏪 Проверьте данные:\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"📝 {d.get('name','-')}\n"
        f"📍 {d.get('address','-')}\n"
        f"📞 {d.get('phone','-')}\n"
        f"✈️ {d.get('telegram','-')}\n"
        f"📱 {d.get('vk','-')}\n"
        f"👤 {d.get('owner_name','-')}\n\n"
        f"Нажмите на поле, чтобы изменить:"
    )
    kb = types.InlineKeyboardMarkup()
    kb.row(types.InlineKeyboardButton("📝 Название", callback_data="edit_name"),
           types.InlineKeyboardButton("📍 Адрес", callback_data="edit_address"))
    kb.row(types.InlineKeyboardButton("📞 Телефон", callback_data="edit_phone"),
           types.InlineKeyboardButton("✈️ Telegram", callback_data="edit_telegram"))
    kb.row(types.InlineKeyboardButton("📱 ВК", callback_data="edit_vk"),
           types.InlineKeyboardButton("👤 Имя", callback_data="edit_owner_name"))
    kb.row(types.InlineKeyboardButton("✅ Отправить", callback_data="submit_shop"),
           types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_shop"))
    bot_shop.send_message(chat_id, txt, reply_markup=kb)

@bot_shop.callback_query_handler(func=lambda c: c.data.startswith("edit_"))
def cb_edit_field(c):
    field = c.data.split("_", 1)[1]
    uid = c.from_user.id
    if uid not in shop_preview:
        bot_shop.answer_callback_query(c.id, "Время истекло"); return
    shop_reg[uid] = {"step": field, "d": shop_preview[uid]}
    bot_shop.send_message(uid, "Введите новое значение:", reply_markup=kb_cancel())
    bot_shop.answer_callback_query(c.id)

@bot_shop.callback_query_handler(func=lambda c: c.data == "submit_shop")
def cb_submit_shop(c):
    uid = c.from_user.id
    d = shop_preview.get(uid)
    if not d:
        bot_shop.answer_callback_query(c.id, "Время истекло"); return
    db("INSERT INTO shops (tg_id,name,address,phone,telegram,vk,owner_name,created_at) VALUES (?,?,?,?,?,?,?,?)",
       (uid, d["name"], d["address"], d["phone"], d["telegram"], d["vk"], d["owner_name"], now()))
    sid = db("SELECT id FROM shops WHERE tg_id=?", (uid,), "one")[0]
    del shop_preview[uid]
    bot_shop.edit_message_text("✅ Заявка отправлена. Ждём одобрения админа.", c.message.chat.id, c.message.message_id)
    bot_shop.send_message(uid, "Меню:", reply_markup=kb_shop())
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("✅ Одобрить", callback_data=f"shop_ok_{sid}"),
           types.InlineKeyboardButton("❌ Отклонить", callback_data=f"shop_no_{sid}"))
    bot_admin.send_message(config.ADMIN_ID,
        f"🏪 НОВЫЙ МАГАЗИН\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📝 {d['name']}\n"
        f"📍 {d['address']}\n"
        f"📞 {d['phone']}\n"
        f"✈️ {d['telegram']}\n"
        f"📱 {d['vk']}\n"
        f"👤 {d['owner_name']}",
        reply_markup=kb)
    log(f"Новый магазин: {d['name']}")
    bot_shop.answer_callback_query(c.id, "Отправлено")

@bot_shop.callback_query_handler(func=lambda c: c.data == "cancel_shop")
def cb_cancel_shop(c):
    uid = c.from_user.id
    if uid in shop_preview: del shop_preview[uid]
    bot_shop.edit_message_text("❌ Отменено.", c.message.chat.id, c.message.message_id)
    bot_shop.answer_callback_query(c.id)

@bot_shop.callback_query_handler(func=lambda c: c.data == "start_register")
def cb_start_register(c):
    if db("SELECT id FROM shops WHERE tg_id=?", (c.from_user.id,), "one"):
        bot_shop.answer_callback_query(c.id, "Вы уже зарегистрированы"); return
    shop_reg[c.from_user.id] = {"step":"name","d":{}}
    bot_shop.send_message(c.from_user.id, "📝 Шаг 1/6: Название магазина", reply_markup=kb_cancel())
    bot_shop.answer_callback_query(c.id)

# ===== ЗАЯВКА МАГАЗИНА =====
@bot_shop.message_handler(func=lambda m: m.text=="🆕 Создать заявку")
def order_start(m):
    s = db("SELECT * FROM shops WHERE tg_id=?", (m.from_user.id,), "one")
    if not s or s[8]!="active":
        bot_shop.send_message(m.chat.id, "Доступ закрыт."); return
    order_reg[m.from_user.id] = {
        "step": "address_to",
        "d": {"shop_id": s[0], "shop_name": s[2], "address_from": s[3]}
    }
    bot_shop.send_message(m.chat.id,
        "📦 Создание заявки\n"
        "━━━━━━━━━━━━━━━\n\n"
        f"🏪 {s[2]}\n"
        f"📍 {s[3]}\n\n"
        "━━━━━━━━━━━━━━━\n"
        "📝 Шаг 1/8: Куда отвезти\n\n"
        "Введите адрес получателя:\n"
        "Улица, дом, подъезд, квартира, этаж\n\n"
        "Пример: ул. Гагарина 10, подъезд 3, кв. 45",
        reply_markup=kb_cancel())

@bot_shop.message_handler(func=lambda m: m.from_user.id in order_reg)
def order_step(m):
    if is_cancel(m):
        del order_reg[m.from_user.id]
        bot_shop.send_message(m.chat.id, "❌ Отменено.", reply_markup=kb_shop()); return
    st = order_reg[m.from_user.id]; s = st["step"]; d = st["d"]

    if s == "delivery_zone":
        zone_key = None
        for key, zone in config.DELIVERY_ZONES.items():
            if zone["name"] in m.text:
                zone_key = key; break
        if not zone_key:
            bot_shop.send_message(m.chat.id, "❌ Выберите зону из кнопок ниже."); return
        d["delivery_price"] = config.DELIVERY_ZONES[zone_key]["price"]
        d["delivery_zone"] = config.DELIVERY_ZONES[zone_key]["name"]
        st["step"] = "order_price"
        bot_shop.send_message(m.chat.id,
            f"✅ Зона: {d['delivery_zone']}\n"
            f"💰 Доставка: {d['delivery_price']} ₽\n\n"
            "━━━━━━━━━━━━━━━\n"
            "📝 Шаг 7/8: Сумма заказа\n"
            "━━━━━━━━━━━━━━━\n\n"
            "Введите стоимость букета:\n"
            "Например: 2500",
            reply_markup=kb_cancel())
        return
        
    prompts = {
    "client_name": ("📝 Шаг 2/8: Имя получателя\n"
                    "━━━━━━━━━━━━━━━\n\n"
                    "👤 Как зовут человека,\nкоторый получит букет?"),
    "client_phone": ("📝 Шаг 3/8: Телефон получателя\n"
                     "━━━━━━━━━━━━━━━\n\n"
                     "📞 Формат: 8XXXXXXXXXX или +7XXXXXXXXXX\n"
                     "Пример: 89001234567"),
    "client_tg": ("📝 Шаг 4/8: Telegram ID клиента\n"
                  "━━━━━━━━━━━━━━━\n\n"
                  "🔍 Это ID, а НЕ телефон!\n\n"
                  "1. Попросите клиента написать @userinfobot\n"
                  "2. Бот пришлёт число (например 123456789)\n"
                  "3. Пришлите это число сюда\n\n"
                  "⚠️ Если ID нет — отправьте -"),
    "delivery_time": ("📝 Шаг 5/8: Время доставки\n"
                      "━━━━━━━━━━━━━━━\n\n"
                      "🕐 Например: Сегодня до 18:00"),
    "order_price": ("📝 Шаг 7/8: Сумма заказа\n"
                    "━━━━━━━━━━━━━━━\n\n"
                    "💰 Стоимость букета в рублях\n"
                    "Например: 2500"),
    "comment": ("📝 Шаг 8/8: Комментарий\n"
                "━━━━━━━━━━━━━━━\n\n"
                "💬 Код домофона, особенности адреса\n\n"
                "Если нечего — отправьте -"),
    }
    steps = ["address_to","client_name","client_phone","client_tg","delivery_time","delivery_zone","order_price","comment"]

    if s == "client_phone":
        t = m.text.replace(" ", "").replace("-", "").replace("(", "").replace(")", "").replace("+", "")
        if not t.isdigit() or len(t) < 10 or len(t) > 15:
            bot_shop.send_message(m.chat.id, "❌ Неверный номер. Введите 10-15 цифр. Пример: 89001234567")
            return
        d[s] = m.text.strip()
    elif s == "client_tg":
        d[s] = m.text.strip() if m.text.strip() else "-"
    elif s == "order_price":
        try: v = float(m.text.replace(",","."))
        except:
            bot_shop.send_message(m.chat.id, "❌ Введите число. Например: 2500"); return
        if v <= 0:
            bot_shop.send_message(m.chat.id, "❌ Сумма должна быть больше 0"); return
        d[s] = v
    else:
        d[s] = m.text

    i = steps.index(s)
    if i+1 < len(steps):
        st["step"] = steps[i+1]
        if st["step"] == "delivery_zone":
            kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
            for zone in config.DELIVERY_ZONES.values():
                kb.row(f"{zone['name']} — {zone['price']}₽")
            kb.row("❌ Отмена")
            bot_shop.send_message(m.chat.id,
                "📝 Шаг 6/8: Зона доставки\n"
                "━━━━━━━━━━━━━━━\n\n"
                "📍 Выберите зону:",
                reply_markup=kb)
        else:
            bot_shop.send_message(m.chat.id, prompts[st["step"]])
    else:
        d["commission"] = round(d["delivery_price"] * config.COMMISSION_PERCENT / 100, 2)
        d["courier_fee"] = round(d["delivery_price"] - d["commission"], 2)
        try: client_tg_int = int(d["client_tg"].strip())
        except: client_tg_int = None
        oid = db("INSERT INTO orders (shop_id,shop_name,address_from,address_to,client_name,client_phone,client_tg_id,delivery_time,order_price,delivery_price,commission,courier_fee,comment,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 (d["shop_id"], d["shop_name"], d["address_from"], d["address_to"], d["client_name"], d["client_phone"], client_tg_int, d["delivery_time"], d["order_price"], d["delivery_price"], d["commission"], d["courier_fee"], d["comment"], now()))
        del order_reg[m.from_user.id]
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("💳 Я оплатил", callback_data=f"paid_{oid}"))
        bot_shop.send_message(m.chat.id,
            f"✅ Заявка #{oid} создана!\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"🏪 {d['shop_name']}\n"
            f"📍 Откуда: {d['address_from']}\n"
            f"🎯 Куда: {d['address_to']}\n"
            f"👤 {d['client_name']}\n"
            f"📞 {d['client_phone']}\n"
            f"🕐 {d['delivery_time']}\n"
            f"📍 {d.get('delivery_zone','-')}\n"
            f"💰 Заказ: {d['order_price']:.2f} ₽\n"
            f"🚚 Доставка: {d['delivery_price']:.2f} ₽\n\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💳 Оплата на карту:\n"
            f"{config.CARD_NUMBER}\n"
            f"{config.CARD_HOLDER}\n"
            f"{config.BANK_NAME}\n\n"
            f"После оплаты нажмите кнопку:",
            reply_markup=kb)

@bot_shop.message_handler(func=lambda m: m.text=="📋 Мои заявки")
def shop_orders(m):
    s = db("SELECT * FROM shops WHERE tg_id=?", (m.from_user.id,), "one")
    if not s: return
    orders = db("SELECT * FROM orders WHERE shop_id=? ORDER BY id DESC LIMIT 15", (s[0],), "all")
    if not orders:
        bot_shop.send_message(m.chat.id, "📋 Заявок нет."); return
    for o in orders:
        em = config.STATUS_EMOJI.get(o[16], "❓")
        st_txt = config.STATUS_TEXT.get(o[16], o[16])
        txt = (f"{em} Заказ #{o[0]}\n"
               f"━━━━━━━━━━━━━━━\n"
               f"🎯 {o[5][:50]}\n"
               f"💰 {o[11]:.2f} ₽\n"
               f"🚚 Доставка: {o[12]:.2f} ₽\n"
               f"Статус: {st_txt}")
        if o[2]:
            cr = db("SELECT name, phone FROM couriers WHERE id=?", (o[2],), "one")
            if cr: txt += f"\n🚚 {cr[0]}\n📞 {cr[1]}"
        kb = types.InlineKeyboardMarkup()
        if o[16] not in ("done","cancel"):
            kb.add(types.InlineKeyboardButton("✏️ Изменить", callback_data=f"edit_order_{o[0]}"))
            kb.add(types.InlineKeyboardButton("❌ Отменить", callback_data=f"cancel_{o[0]}"))
        if kb.keyboard: bot_shop.send_message(m.chat.id, txt, reply_markup=kb)
        else: bot_shop.send_message(m.chat.id, txt)

@bot_shop.message_handler(func=lambda m: m.text=="📊 Статистика")
def shop_stats(m):
    s = db("SELECT * FROM shops WHERE tg_id=?", (m.from_user.id,), "one")
    if not s: return
    orders = db("SELECT * FROM orders WHERE shop_id=?", (s[0],), "all")
    total = len(orders)
    done = sum(1 for o in orders if o[16]=="done")
    cancel = sum(1 for o in orders if o[16]=="cancel")
    summ = sum(o[11] for o in orders if o[11])
    comm = sum(o[12] for o in orders if o[12])
    rating = s[9] if len(s) > 9 else 0
    cnt = s[10] if len(s) > 10 else 0
    txt = (f"📊 Статистика\n"
           f"━━━━━━━━━━━━━━━\n\n"
           f"📦 Заявок: {total}\n"
           f"✅ Доставлено: {done}\n"
           f"❌ Отменено: {cancel}\n\n"
           f"💰 Оборот: {summ:.2f} ₽\n"
           f"💵 Комиссия: {comm:.2f} ₽")
    if rating and cnt: txt += f"\n\n⭐ Рейтинг: {rating} ({cnt})"
    bot_shop.send_message(m.chat.id, txt)

@bot_shop.message_handler(func=lambda m: m.text=="⭐ Отзывы")
def shop_reviews(m):
    s = db("SELECT * FROM shops WHERE tg_id=?", (m.from_user.id,), "one")
    if not s: return
    rating = s[9] if len(s) > 9 else 0
    cnt = s[10] if len(s) > 10 else 0
    txt = "⭐ Мои отзывы\n━━━━━━━━━━━━━━━\n\n"
    if rating and cnt:
        txt += f"📊 Средняя: {rating} ⭐\n📝 Всего: {cnt}\n\n"
        for stars in [5,4,3,2,1]:
            c = db("SELECT COUNT(*) FROM reviews WHERE target_type='shop' AND target_id=? AND rating=?", (s[0], stars), "one")[0]
            if c: txt += f"{'⭐'*stars} — {c}\n"
        reviews = db("SELECT rating, comment, created_at FROM reviews WHERE target_type='shop' AND target_id=? ORDER BY id DESC LIMIT 5", (s[0],), "all")
        if reviews:
            txt += "\n━━━━━━━━━━━━━━━\n\n"
            for r in reviews:
                txt += f"{'⭐'*r[0]}\n"
                if r[1]: txt += f"💬 {r[1][:100]}\n"
                txt += f"🕐 {r[2]}\n\n"
    else:
        txt += "😔 Отзывов пока нет."
    bot_shop.send_message(m.chat.id, txt)

@bot_shop.message_handler(func=lambda m: m.text=="⚙️ Настройки")
def shop_settings(m):
    bot_shop.send_message(m.chat.id, "⚙️ В разработке")

@bot_shop.callback_query_handler(func=lambda c: c.data.startswith("paid_"))
def cb_paid(c):
    oid = int(c.data.split("_")[1])
    db("UPDATE orders SET payment_status='confirmed', status='wait' WHERE id=?", (oid,))
    bot_shop.edit_message_text(f"✅ Оплата #{oid} подтверждена. Ищем курьера...", c.message.chat.id, c.message.message_id)
    o = db("SELECT * FROM orders WHERE id=?", (oid,), "one")
    bot_admin.send_message(config.ADMIN_ID, f"💰 Оплата #{oid}\n{o[3]}\n{o[11]:.2f}")
    log(f"Оплата #{oid} на {o[11]:.2f}")

@bot_shop.callback_query_handler(func=lambda c: c.data.startswith("cancel_"))
def cb_cancel_order(c):
    oid = int(c.data.split("_")[1]); o = db("SELECT * FROM orders WHERE id=?", (oid,), "one")
    if not o: bot_shop.answer_callback_query(c.id, "Не найдена"); return
    if o[16] in ("done","cancel"): bot_shop.answer_callback_query(c.id, "Уже закрыта"); return
    s = db("SELECT tg_id FROM shops WHERE id=?", (o[1],), "one")
    if not s or s[0] != c.from_user.id: bot_shop.answer_callback_query(c.id, "Не ваша"); return
    db("UPDATE orders SET status='cancel' WHERE id=?", (oid,))
    bot_shop.edit_message_text(f"❌ Заявка #{oid} отменена", c.message.chat.id, c.message.message_id)
    if o[2]:
        cr = db("SELECT tg_id FROM couriers WHERE id=?", (o[2],), "one")
        if cr:
            try: bot_courier.send_message(cr[0], f"❌ Заказ #{oid} отменён магазином")
            except: pass
    if o[8]:
        try: bot_client.send_message(o[8], f"❌ Заказ #{oid} отменён")
        except: pass
    log(f"Отмена #{oid}")
    bot_shop.answer_callback_query(c.id, "Отменено")

@bot_shop.callback_query_handler(func=lambda c: c.data.startswith("edit_order_"))
def cb_edit_order_menu(c):
    oid = int(c.data.split("_")[2])
    o = db("SELECT * FROM orders WHERE id=?", (oid,), "one")
    if not o: bot_shop.answer_callback_query(c.id); return
    s = db("SELECT tg_id FROM shops WHERE id=?", (o[1],), "one")
    if not s or s[0] != c.from_user.id: bot_shop.answer_callback_query(c.id, "Не ваша"); return
    if o[16] in ("done","cancel"): bot_shop.answer_callback_query(c.id, "Уже закрыта"); return
    kb = types.InlineKeyboardMarkup()
    kb.row(types.InlineKeyboardButton("📍 Адрес", callback_data=f"eo_addr_{oid}"))
    kb.row(types.InlineKeyboardButton("📞 Телефон", callback_data=f"eo_phone_{oid}"))
    kb.row(types.InlineKeyboardButton("👤 Имя", callback_data=f"eo_name_{oid}"))
    kb.row(types.InlineKeyboardButton("🕐 Время", callback_data=f"eo_time_{oid}"))
    kb.row(types.InlineKeyboardButton("💬 Комментарий", callback_data=f"eo_comm_{oid}"))
    kb.row(types.InlineKeyboardButton("⬅️ Назад", callback_data=f"eo_back_{oid}"))
    bot_shop.send_message(c.from_user.id, f"✏️ Что изменить в заказе #{oid}?", reply_markup=kb)
    bot_shop.answer_callback_query(c.id)

@bot_shop.callback_query_handler(func=lambda c: c.data.startswith("eo_"))
def cb_edit_order_field(c):
    parts = c.data.split("_")
    action = parts[1]; oid = int(parts[2])
    fields = {"addr": "address_to", "phone": "client_phone", "name": "client_name", "time": "delivery_time", "comm": "comment"}
    if action == "back":
        bot_shop.edit_message_text("Отменено.", c.message.chat.id, c.message.message_id)
        bot_shop.answer_callback_query(c.id); return
    field = fields.get(action)
    if not field: bot_shop.answer_callback_query(c.id); return
    order_reg[c.from_user.id] = {"step": "edit_" + field, "d": {"order_id": oid}}
    bot_shop.send_message(c.from_user.id, f"Введите новое значение:", reply_markup=kb_cancel())
    bot_shop.answer_callback_query(c.id)

@bot_shop.message_handler(func=lambda m: m.from_user.id in order_reg and order_reg[m.from_user.id]["step"].startswith("edit_"))
def cb_edit_order_save(m):
    if is_cancel(m):
        del order_reg[m.from_user.id]
        bot_shop.send_message(m.chat.id, "Отменено.", reply_markup=kb_shop()); return
    st = order_reg[m.from_user.id]
    field = st["step"][5:]
    oid = st["d"]["order_id"]
    db(f"UPDATE orders SET {field}=? WHERE id=?", (m.text, oid))
    del order_reg[m.from_user.id]
    bot_shop.send_message(m.chat.id, f"✅ Обновлено!", reply_markup=kb_shop())
    o = db("SELECT * FROM orders WHERE id=?", (oid,), "one")
    if o[2]:
        cr = db("SELECT tg_id FROM couriers WHERE id=?", (o[2],), "one")
        if cr:
            try: bot_courier.send_message(cr[0], f"⚠️ Магазин изменил заказ #{oid}\nПроверьте детали.")
            except: pass
    log(f"Магазин изменил #{oid} поле {field}")
# ===== КУРЬЕР =====
@bot_courier.message_handler(commands=['start'])
def cour_start(m):
    c = db("SELECT * FROM couriers WHERE tg_id=?", (m.from_user.id,), "one")
    if not c:
        bot_courier.send_message(m.chat.id,
            "👋 Привет!\n\n"
            "🚚 Станьте частью команды курьеров SLIPI!\n\n"
            "Отправьте /register")
        return
    if c[8]=="pending": bot_courier.send_message(m.chat.id, "⏳ Заявка на рассмотрении.")
    elif c[8]=="blocked": bot_courier.send_message(m.chat.id, "🚫 Доступ закрыт.")
    else: bot_courier.send_message(m.chat.id, f"🚚 Меню курьера\n👤 {c[2]}\n💰 Баланс: {c[7]:.2f}", reply_markup=kb_courier())

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
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("📝 Зарегистрироваться", callback_data="start_register_cour"))
        bot_courier.send_message(m.chat.id, "Отменено. Чтобы стать курьером - зарегистрируйтесь.", reply_markup=kb)
        return
    st = cour_reg[m.from_user.id]; s = st["step"]; d = st["d"]
    steps = ["name","phone","city","transport","card"]
    prompts = {"phone":"Шаг 2/5: Телефон (8XXXXXXXXXX)","city":"Шаг 3/5: Город / район","transport":"Шаг 4/5: Транспорт (Авто / Мото / Велик / Пешком)","card":"Шаг 5/5: Номер карты для вывода"}
    if s == "phone":
        t = m.text.replace(" ", "").replace("-", "").replace("(", "").replace(")", "").replace("+", "")
        if not t.isdigit() or len(t) < 10 or len(t) > 15:
            bot_courier.send_message(m.chat.id, "❌ Неверный номер. Введите 10-15 цифр."); return
        d[s] = m.text.strip(); st["step"] = "city"; bot_courier.send_message(m.chat.id, prompts["city"]); return
    d[s] = m.text
    i = steps.index(s)
    if i+1 < len(steps):
        st["step"] = steps[i+1]; bot_courier.send_message(m.chat.id, prompts[st["step"]])
    else:
        db("INSERT INTO couriers (tg_id,name,phone,city,transport,card,created_at) VALUES (?,?,?,?,?,?,?)",
           (m.from_user.id, d["name"], d["phone"], d["city"], d["transport"], d["card"], now()))
        cid = db("SELECT id FROM couriers WHERE tg_id=?", (m.from_user.id,), "one")[0]
        del cour_reg[m.from_user.id]
        bot_courier.send_message(m.chat.id, "✅ Заявка отправлена!", reply_markup=kb_courier())
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("✅ Одобрить", callback_data=f"cour_ok_{cid}"),
               types.InlineKeyboardButton("❌ Отклонить", callback_data=f"cour_no_{cid}"))
        bot_admin.send_message(config.ADMIN_ID,
            f"🚚 НОВЫЙ КУРЬЕР\n"
            f"━━━━━━━━━━━━━━━\n"
            f"👤 {d['name']}\n"
            f"📞 {d['phone']}\n"
            f"📍 {d['city']}\n"
            f"🚗 {d['transport']}\n"
            f"💳 {d['card']}",
            reply_markup=kb)
        log(f"Новый курьер: {d['name']}")

@bot_courier.callback_query_handler(func=lambda c: c.data == "start_register_cour")
def cb_start_register_cour(c):
    if db("SELECT id FROM couriers WHERE tg_id=?", (c.from_user.id,), "one"):
        bot_courier.answer_callback_query(c.id, "Вы уже зарегистрированы"); return
    cour_reg[c.from_user.id] = {"step":"name","d":{}}
    bot_courier.send_message(c.from_user.id, "📝 Шаг 1/5: Ваше имя", reply_markup=kb_cancel())
    bot_courier.answer_callback_query(c.id)

# ===== СТАТУС КУРЬЕРА =====
@bot_courier.message_handler(func=lambda m: m.text=="🟢 Статус")
def cour_status_menu(m):
    c = db("SELECT * FROM couriers WHERE tg_id=?", (m.from_user.id,), "one")
    if not c: return
    state = c[9] if len(c) > 9 else "off"
    states = {"off": "⚪ Не на смене", "on": "🟢 На смене", "break": "☕ Перерыв", "busy": "🚚 На заказе"}
    bot_courier.send_message(m.chat.id,
        f"🟢 Ваш статус\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"Сейчас: {states.get(state, '⚪ Не на смене')}\n\n"
        "Выберите новое состояние:",
        reply_markup=kb_courier_status())

@bot_courier.message_handler(func=lambda m: m.text=="🟢 На смене")
def cour_status_on(m):
    db("UPDATE couriers SET courier_state='on' WHERE tg_id=?", (m.from_user.id,))
    bot_courier.send_message(m.chat.id,
        "🟢 Вы на смене\n\n"
        "Готовы принимать заказы.\n"
        "Не забудьте взять смену в разделе 📅 Смены.",
        reply_markup=kb_courier())

@bot_courier.message_handler(func=lambda m: m.text=="☕ Перерыв")
def cour_status_break(m):
    db("UPDATE couriers SET courier_state='break' WHERE tg_id=?", (m.from_user.id,))
    bot_courier.send_message(m.chat.id,
        "☕ Перерыв\n\n"
        "Заказы временно не приходят.\n"
        "Когда вернётесь — нажмите 🟢 На смене.",
        reply_markup=kb_courier())

@bot_courier.message_handler(func=lambda m: m.text=="⚪ Не на смене")
def cour_status_off(m):
    db("UPDATE couriers SET courier_state='off' WHERE tg_id=?", (m.from_user.id,))
    bot_courier.send_message(m.chat.id,
        "⚪ Вы не на смене\n\n"
        "Заказы не приходят.\n"
        "Чтобы начать — выберите 🟢 На смене.",
        reply_markup=kb_courier())

@bot_courier.message_handler(func=lambda m: m.text=="⬅️ Назад")
def cour_status_back(m):
    bot_courier.send_message(m.chat.id, "Меню", reply_markup=kb_courier())

# ===== СВОБОДНЫЕ ЗАЯВКИ =====
@bot_courier.message_handler(func=lambda m: m.text=="📋 Свободные заявки")
def cour_free(m):
    cr = db("SELECT * FROM couriers WHERE tg_id=?", (m.from_user.id,), "one")
    if not cr: return
    state = cr[9] if len(cr) > 9 else "off"
    if state not in ("on","busy"):
        bot_courier.send_message(m.chat.id,
            "⚠️ Вы не на смене.\n\nНажмите 🟢 Статус → 🟢 На смене",
            reply_markup=kb_courier())
        return
    orders = db("""SELECT * FROM orders
                   WHERE status='wait'
                   AND payment_status='confirmed'
                   AND (courier_id IS NULL OR courier_id=0)
                   ORDER BY id ASC""", fetch="all")
    if not orders:
        bot_courier.send_message(m.chat.id,
            "📋 Свободные заявки\n"
            "━━━━━━━━━━━━━━━\n\n"
            "😔 Сейчас свободных нет.\n\n"
            "Заглядывайте позже.")
        return
    bot_courier.send_message(m.chat.id, f"📋 Свободных заявок: {len(orders)}")
    for o in orders[:10]:
        txt = (f"📦 Заказ #{o[0]}\n"
               f"━━━━━━━━━━━━━━━\n"
               f"🏪 {o[3]}\n"
               f"📍 {o[4]}\n"
               f"🎯 {o[5]}\n"
               f"🕐 {o[9]}\n"
               f"💰 {o[13]:.2f} ₽")
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("✅ Взять заказ", callback_data=f"take_{o[0]}"))
        bot_courier.send_message(m.chat.id, txt, reply_markup=kb)

@bot_courier.callback_query_handler(func=lambda c: c.data.startswith("take_"))
def cb_take(c):
    oid = int(c.data.split("_")[1])
    o = db("SELECT * FROM orders WHERE id=?", (oid,), "one")
    if not o: bot_courier.answer_callback_query(c.id, "Не найдена"); return
    if o[16] != "wait" or o[2]:
        bot_courier.answer_callback_query(c.id, "Заказ уже занят"); return
    cr = db("SELECT * FROM couriers WHERE tg_id=?", (c.from_user.id,), "one")
    if o[2] == cr[0]:
        bot_courier.answer_callback_query(c.id, "Это ваш заказ"); return
    db("UPDATE orders SET courier_id=?, status='going' WHERE id=?", (cr[0], oid))
    db("UPDATE couriers SET courier_state='busy' WHERE id=?", (cr[0],))
    txt = (f"✅ Вы взяли заказ #{oid}\n"
           f"━━━━━━━━━━━━━━━\n"
           f"🏪 {o[3]}\n"
           f"📍 Откуда: {o[4]}\n"
           f"🎯 Куда: {o[5]}\n"
           f"👤 {o[6]}\n"
           f"📞 {o[7]}\n"
           f"💰 {o[13]:.2f} ₽")
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📦 Забрал", callback_data=f"picked_{oid}"))
    kb.add(types.InlineKeyboardButton("🗺 Карта", url=f"https://yandex.ru/maps/?text={o[4].replace(' ','+')}"))
    kb.add(types.InlineKeyboardButton("❌ Отказаться", callback_data=f"refuse_{oid}"))
    bot_courier.send_message(c.from_user.id, txt, reply_markup=kb)
    s = db("SELECT tg_id FROM shops WHERE id=?", (o[1],), "one")
    try: bot_shop.send_message(s[0], f"🚚 Курьер {cr[2]} взял заказ #{oid}\n📞 {cr[3]}")
    except: pass
    log(f"Курьер {cr[2]} взял #{oid}")
    bot_courier.answer_callback_query(c.id)

@bot_courier.callback_query_handler(func=lambda c: c.data.startswith("picked_"))
def cb_picked(c):
    oid = int(c.data.split("_")[1])
    db("UPDATE orders SET status='delivering' WHERE id=?", (oid,))
    o = db("SELECT * FROM orders WHERE id=?", (oid,), "one")
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📍 У клиента", callback_data=f"atcli_{oid}"))
    kb.add(types.InlineKeyboardButton("✅ Доставлено", callback_data=f"done_{oid}"))
    kb.add(types.InlineKeyboardButton("🗺 Карта", url=f"https://yandex.ru/maps/?text={o[5].replace(' ','+')}"))
    kb.add(types.InlineKeyboardButton("📞 Позвонить", url=f"tel:{o[7]}"))
    bot_courier.send_message(c.from_user.id, f"📦 Заказ #{oid} забран. Везёте клиенту.", reply_markup=kb)
    s = db("SELECT tg_id FROM shops WHERE id=?", (o[1],), "one")
    try: bot_shop.send_message(s[0], f"📦 Курьер забрал #{oid}")
    except: pass
    if o[8]:
        try: bot_client.send_message(o[8], f"🚚 Курьер везёт ваш заказ #{oid}")
        except: pass
    bot_courier.answer_callback_query(c.id)

@bot_courier.callback_query_handler(func=lambda c: c.data.startswith("atcli_"))
def cb_atcli(c):
    oid = int(c.data.split("_")[1])
    db("UPDATE orders SET status='at_client' WHERE id=?", (oid,))
    o = db("SELECT * FROM orders WHERE id=?", (oid,), "one")
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("✅ Доставлено", callback_data=f"done_{oid}"))
    kb.add(types.InlineKeyboardButton("📞 Позвонить", url=f"tel:{o[7]}"))
    bot_courier.send_message(c.from_user.id, f"📍 Заказ #{oid} — вы у клиента.", reply_markup=kb)
    if o[8]:
        try: bot_client.send_message(o[8], f"📍 Курьер у вашего подъезда! Заказ #{oid}")
        except: pass
    bot_courier.answer_callback_query(c.id)

@bot_courier.callback_query_handler(func=lambda c: c.data.startswith("done_"))
def cb_done(c):
    oid = int(c.data.split("_")[1])
    o = db("SELECT * FROM orders WHERE id=?", (oid,), "one")
    cr = db("SELECT * FROM couriers WHERE tg_id=?", (c.from_user.id,), "one")
    db("UPDATE orders SET status='done' WHERE id=?", (oid,))
    db("UPDATE couriers SET balance=balance+?, courier_state='on' WHERE id=?", (o[13], cr[0]))
    new_bal = db("SELECT balance FROM couriers WHERE id=?", (cr[0],), "one")[0]
    bot_courier.send_message(c.from_user.id,
        f"✅ Заказ #{oid} доставлен!\n"
        f"💰 +{o[13]:.2f} ₽\n"
        f"💵 Баланс: {new_bal:.2f}")
    s = db("SELECT tg_id FROM shops WHERE id=?", (o[1],), "one")
    try: bot_shop.send_message(s[0], f"✅ Заказ #{oid} доставлен!")
    except: pass
    if o[8]:
        try:
            bot_client.send_message(o[8],
                f"✅ Заказ #{oid} доставлен! Спасибо 🌸\n\nОцените магазин:",
                reply_markup=kb_rating("shop", oid))
            review_reg[o[8]] = {"order_id": oid, "step": "shop", "shop": 0, "courier": 0, "service": 0}
        except: pass
    log(f"Курьер {cr[2]} доставил #{oid}")
    bot_courier.answer_callback_query(c.id)

@bot_courier.callback_query_handler(func=lambda c: c.data.startswith("refuse_"))
def cb_refuse(c):
    oid = int(c.data.split("_")[1])
    o = db("SELECT * FROM orders WHERE id=?", (oid,), "one")
    db("UPDATE orders SET courier_id=NULL, status='wait' WHERE id=?", (oid,))
    cr = db("SELECT * FROM couriers WHERE tg_id=?", (c.from_user.id,), "one")
    db("UPDATE couriers SET courier_state='on' WHERE id=?", (cr[0],))
    bot_courier.send_message(c.from_user.id, f"↩️ Заказ #{oid} возвращён в список.")
    s = db("SELECT tg_id FROM shops WHERE id=?", (o[1],), "one")
    try: bot_shop.send_message(s[0], f"↩️ Курьер отказался от заказа #{oid}")
    except: pass
    bot_courier.answer_callback_query(c.id)

# ===== МОИ ЗАКАЗЫ =====
@bot_courier.message_handler(func=lambda m: m.text=="🚗 Мои заказы")
def cour_my(m):
    cr = db("SELECT * FROM couriers WHERE tg_id=?", (m.from_user.id,), "one")
    if not cr: return
    orders = db("SELECT * FROM orders WHERE courier_id=? AND status IN ('going','delivering','at_client') ORDER BY id DESC", (cr[0],), "all")
    if not orders:
        bot_courier.send_message(m.chat.id, "🚗 Мои заказы\n\nАктивных нет.")
        return
    for o in orders:
        em = config.STATUS_EMOJI.get(o[16], "❓")
        st_txt = config.STATUS_TEXT.get(o[16], o[16])
        txt = (f"{em} Заказ #{o[0]}\n"
               f"━━━━━━━━━━━━━━━\n"
               f"🏪 {o[3]}\n"
               f"📍 Забрать: {o[4]}\n"
               f"🎯 Доставить: {o[5]}\n"
               f"👤 {o[6]}\n"
               f"📞 {o[7]}\n"
               f"🕐 {o[9]}\n"
               f"💰 {o[13]:.2f} ₽\n"
               f"💬 {o[14] or '—'}\n"
               f"━━━━━━━━━━━━━━━\n"
               f"Статус: {st_txt}")
        kb = types.InlineKeyboardMarkup()
        if o[16] == "going":
            kb.add(types.InlineKeyboardButton("📦 Забрал", callback_data=f"picked_{o[0]}"))
            kb.add(types.InlineKeyboardButton("❌ Отменить заказ", callback_data=f"cancel_cour_{o[0]}"))
        elif o[16] == "delivering":
            kb.add(types.InlineKeyboardButton("📍 У клиента", callback_data=f"atcli_{o[0]}"))
            kb.add(types.InlineKeyboardButton("✅ Доставлено", callback_data=f"done_{o[0]}"))
            kb.add(types.InlineKeyboardButton("❌ Отменить заказ", callback_data=f"cancel_cour_{o[0]}"))
        elif o[16] == "at_client":
            kb.add(types.InlineKeyboardButton("✅ Доставлено", callback_data=f"done_{o[0]}"))
        kb.add(types.InlineKeyboardButton("🗺 Карта", url=f"https://yandex.ru/maps/?text={o[5].replace(' ','+')}"))
        kb.add(types.InlineKeyboardButton("📞 Клиент", url=f"tel:{o[7]}"))
        bot_courier.send_message(m.chat.id, txt, reply_markup=kb)

@bot_courier.callback_query_handler(func=lambda c: c.data.startswith("cancel_cour_"))
def cb_cancel_cour(c):
    oid = int(c.data.split("_")[2])
    o = db("SELECT * FROM orders WHERE id=?", (oid,), "one")
    if not o: bot_courier.answer_callback_query(c.id); return
    cr = db("SELECT * FROM couriers WHERE tg_id=?", (c.from_user.id,), "one")
    if o[2] != cr[0]:
        bot_courier.answer_callback_query(c.id, "Не ваш заказ"); return
    db("UPDATE orders SET courier_id=NULL, status='wait' WHERE id=?", (oid,))
    db("UPDATE couriers SET courier_state='on' WHERE id=?", (cr[0],))
    bot_courier.edit_message_text(f"❌ Заказ #{oid} отменён", c.message.chat.id, c.message.message_id)
    s = db("SELECT tg_id FROM shops WHERE id=?", (o[1],), "one")
    try: bot_shop.send_message(s[0], f"⚠️ Курьер {cr[2]} отменил заказ #{oid}")
    except: pass
    log(f"Курьер {cr[2]} отменил #{oid}")
    bot_courier.answer_callback_query(c.id, "Отменено")

# ===== ЗАРАБОТОК =====
@bot_courier.message_handler(func=lambda m: m.text=="💰 Заработок")
def cour_money(m):
    cr = db("SELECT * FROM couriers WHERE tg_id=?", (m.from_user.id,), "one")
    if not cr: return
    done = db("SELECT COUNT(*) FROM orders WHERE courier_id=? AND status='done'", (cr[0],), "one")[0]
    earned = db("SELECT COALESCE(SUM(courier_fee),0) FROM orders WHERE courier_id=? AND status='done'", (cr[0],), "one")[0]
    rating = cr[10] if len(cr) > 10 else 0
    cnt = cr[11] if len(cr) > 11 else 0
    txt = (f"💰 Мой заработок\n"
           f"━━━━━━━━━━━━━━━\n\n"
           f"💵 Баланс: {cr[7]:.2f} ₽\n"
           f"✅ Доставок: {done}\n"
           f"💸 Заработал: {earned:.2f}")
    if rating and cnt: txt += f"\n⭐ {rating} ({cnt})"
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("💳 Вывести", callback_data="withdraw"))
    bot_courier.send_message(m.chat.id, txt, reply_markup=kb)

@bot_courier.callback_query_handler(func=lambda c: c.data=="withdraw")
def cb_withdraw(c):
    cr = db("SELECT * FROM couriers WHERE tg_id=?", (c.from_user.id,), "one")
    if not cr: bot_courier.answer_callback_query(c.id); return
    if cr[7] < 100:
        bot_courier.answer_callback_query(c.id, f"Минимум 100. Баланс: {cr[7]:.2f}", show_alert=True); return
    withdraw_reg[c.from_user.id] = True
    bot_courier.send_message(c.from_user.id,
        f"💳 Вывод\n\nДоступно: {cr[7]:.2f}\n\nВведите сумму:",
        reply_markup=kb_cancel())
    bot_courier.answer_callback_query(c.id)

@bot_courier.message_handler(func=lambda m: m.from_user.id in withdraw_reg)
def cour_wd(m):
    if is_cancel(m):
        del withdraw_reg[m.from_user.id]
        bot_courier.send_message(m.chat.id, "Отменено.", reply_markup=kb_courier()); return
    try: amt = float(m.text.replace(",","."))
    except: bot_courier.send_message(m.chat.id, "❌ Введите число."); return
    cr = db("SELECT * FROM couriers WHERE tg_id=?", (m.from_user.id,), "one")
    if amt < 100: bot_courier.send_message(m.chat.id, "❌ Минимум 100"); return
    if amt > cr[7]: bot_courier.send_message(m.chat.id, f"❌ Баланс: {cr[7]:.2f}"); return
    db("INSERT INTO withdrawals (courier_id,amount,card,created_at) VALUES (?,?,?,?)", (cr[0], amt, cr[6], now()))
    del withdraw_reg[m.from_user.id]
    bot_courier.send_message(m.chat.id, f"⏳ Заявка на вывод {amt:.2f} отправлена.", reply_markup=kb_courier())
    wid = db("SELECT id FROM withdrawals ORDER BY id DESC LIMIT 1", fetch="one")[0]
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("✅ Подтвердить", callback_data=f"wok_{wid}"),
           types.InlineKeyboardButton("❌ Отклонить", callback_data=f"wno_{wid}"))
    bot_admin.send_message(config.ADMIN_ID,
        f"💳 ВЫВОД #{wid}\n🚚 {cr[2]}\n💰 {amt:.2f}\n💳 {cr[6]}",
        reply_markup=kb)
    log(f"Курьер {cr[2]} просит вывод {amt:.2f}")

# ===== ГЕО =====
@bot_courier.message_handler(func=lambda m: m.text=="📍 Гео")
def cour_loc(m):
    cr = db("SELECT * FROM couriers WHERE tg_id=?", (m.from_user.id,), "one")
    if not cr: return
    info = "нет данных"
    if len(cr) > 13 and cr[13]:
        link = geo_link(cr[13], cr[14])
        info = f"📍 {cr[13]:.5f}, {cr[14]:.5f}\n🗺 {link}"
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("📍 Делиться 8 часов", request_location=True))
    kb.row("🛑 Стоп гео"); kb.row("⬅️ Назад")
    bot_courier.send_message(m.chat.id,
        f"📍 Моя геолокация\n\n{info}\n\n"
        "Нажмите кнопку - выберите 8 часов.",
        reply_markup=kb)

@bot_courier.message_handler(func=lambda m: m.text=="🛑 Стоп гео")
def cour_loc_stop(m):
    db("UPDATE couriers SET lat=NULL, lon=NULL, loc_time=NULL WHERE tg_id=?", (m.from_user.id,))
    bot_courier.send_message(m.chat.id, "🛑 Гео остановлено.", reply_markup=kb_courier())

@bot_courier.message_handler(content_types=['location'])
def cour_loc_got(m):
    lat, lon = m.location.latitude, m.location.longitude
    live = getattr(m.location, "live_period", None)
    db("UPDATE couriers SET lat=?, lon=?, loc_time=? WHERE tg_id=?", (lat, lon, now(), m.from_user.id))
    if live:
        bot_courier.send_message(m.chat.id, f"✅ Трансляция активна на {live/3600:.1f} ч\n📍 {lat:.5f}, {lon:.5f}", reply_markup=kb_courier())
    else:
        bot_courier.send_message(m.chat.id, f"✅ Гео сохранено\n📍 {lat:.5f}, {lon:.5f}", reply_markup=kb_courier())

@bot_courier.edited_message_handler(content_types=['location'])
def cour_loc_update(m):
    lat, lon = m.location.latitude, m.location.longitude
    db("UPDATE couriers SET lat=?, lon=?, loc_time=? WHERE tg_id=?", (lat, lon, now(), m.from_user.id))

# ===== СМЕНЫ =====
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
        txt += f"{v['name']} ({v['start']}-{v['end']})\n{cnt}/{v['limit']} - {mark}\n\n"
    txt += f"━━━━━━━━━━━━━━━\n⚠️ Не вышли — штраф {config.SHIFT_PENALTY} ₽"
    bot_courier.send_message(m.chat.id, txt, reply_markup=kb_shift_slots())

@bot_courier.message_handler(func=lambda m: m.text in ["🌅 Утренняя 7-15","☀️ Дневная 9-18","🌆 Вечерняя 15-23","🌙 Ночная 18-00"])
def cour_shift_book(m):
    cr = db("SELECT * FROM couriers WHERE tg_id=?", (m.from_user.id,), "one")
    if not cr: return
    slot_map = {"🌅 Утренняя 7-15":"morning","☀️ Дневная 9-18":"day","🌆 Вечерняя 15-23":"evening","🌙 Ночная 18-00":"night"}
    slot = slot_map.get(m.text)
    if not slot: return
    v = config.SHIFT_SLOTS[slot]
    cnt = db("SELECT COUNT(*) FROM shifts WHERE date=? AND slot=?", (today(), slot), "one")[0]
    if cnt >= v["limit"]:
        bot_courier.send_message(m.chat.id, f"❌ {v['name']} заполнено", reply_markup=kb_shift_slots()); return
    already = db("SELECT id FROM shifts WHERE date=? AND slot=? AND courier_id=?", (today(), slot, cr[0]), "one")
    if already:
        bot_courier.send_message(m.chat.id, "✅ Уже записаны", reply_markup=kb_shift_slots()); return
    db("INSERT INTO shifts (courier_id,date,slot,status) VALUES (?,?,?,'booked')", (cr[0], today(), slot))
    bot_courier.send_message(m.chat.id,
        f"✅ Вы записаны\n{v['name']} {v['start']}-{v['end']}",
        reply_markup=kb_shift_slots())
    bot_admin.send_message(config.ADMIN_ID, f"📅 Курьер {cr[2]} записался на {v['name']}")

@bot_courier.message_handler(func=lambda m: m.text=="📋 Мои смены")
def cour_my_shifts(m):
    cr = db("SELECT * FROM couriers WHERE tg_id=?", (m.from_user.id,), "one")
    if not cr: return
    shifts = db("SELECT * FROM shifts WHERE courier_id=? AND date>=? ORDER BY date ASC LIMIT 20", (cr[0], today()), "all")
    if not shifts:
        bot_courier.send_message(m.chat.id, "📋 Нет записанных смен", reply_markup=kb_shift_slots()); return
    txt = "📋 Мои смены\n\n"
    for sh in shifts:
        v = config.SHIFT_SLOTS.get(sh[3], {})
        st_txt = config.SHIFT_STATUS.get(sh[4], sh[4])
        txt += f"{sh[2]} {v.get('name','?')}\n{st_txt}\n\n"
    bot_courier.send_message(m.chat.id, txt, reply_markup=kb_shift_slots())

@bot_courier.message_handler(func=lambda m: m.text=="📊 Статистика")
def cour_stats(m):
    cr = db("SELECT * FROM couriers WHERE tg_id=?", (m.from_user.id,), "one")
    if not cr: return
    done = db("SELECT COUNT(*) FROM orders WHERE courier_id=? AND status='done'", (cr[0],), "one")[0]
    active = db("SELECT COUNT(*) FROM orders WHERE courier_id=? AND status IN ('going','delivering','at_client')", (cr[0],), "one")[0]
    sd = db("SELECT COUNT(*) FROM shifts WHERE courier_id=? AND status='done'", (cr[0],), "one")[0]
    sm = db("SELECT COUNT(*) FROM shifts WHERE courier_id=? AND status='missed'", (cr[0],), "one")[0]
    rating = cr[10] if len(cr) > 10 else 0
    cnt = cr[11] if len(cr) > 11 else 0
    txt = (f"📊 Моя статистика\n"
           f"━━━━━━━━━━━━━━━\n\n"
           f"✅ Доставок: {done}\n"
           f"🚗 Активных: {active}\n"
           f"💰 Баланс: {cr[7]:.2f} ₽\n\n"
           f"📅 Смен: {sd}\n"
           f"⚠️ Пропущено: {sm}")
    if rating and cnt: txt += f"\n⭐ {rating} ({cnt})"
    bot_courier.send_message(m.chat.id, txt)

# ===== АДМИН =====
@bot_admin.message_handler(commands=['start'])
def admin_start(m):
    if m.from_user.id != config.ADMIN_ID:
        bot_admin.send_message(m.chat.id, "⛔ Доступ запрещён."); return
    bot_admin.send_message(m.chat.id,
        f"👑 Админ-панель {config.SERVICE_NAME}\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"👤 {config.ADMIN_NAME}",
        reply_markup=kb_admin())

@bot_admin.message_handler(func=lambda m: m.text=="📝 Запросы" and m.from_user.id==config.ADMIN_ID)
def admin_requests_menu(m):
    sc = len(db("SELECT id FROM shops WHERE status='pending'", fetch="all"))
    cc = len(db("SELECT id FROM couriers WHERE status='pending'", fetch="all"))
    sh = len(db("SELECT id FROM shifts WHERE date=? AND status='booked'", (today(),), fetch="all"))
    wd = len(db("SELECT id FROM withdrawals WHERE status='pending'", fetch="all"))
    cn = len(db("SELECT id FROM orders WHERE status='cancel'", fetch="all"))
    bot_admin.send_message(m.chat.id,
        f"📝 ЗАПРОСЫ\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"🏪 Магазины: {sc if sc else 'нет'}\n"
        f"🚚 Курьеры: {cc if cc else 'нет'}\n"
        f"📅 Смены: {sh if sh else 'нет'}\n"
        f"💳 Выплаты: {wd if wd else 'нет'}\n"
        f"❌ Отмены: {cn if cn else 'нет'}",
        reply_markup=kb_admin_req())

@bot_admin.message_handler(func=lambda m: m.text=="⬅️ Назад" and m.from_user.id==config.ADMIN_ID)
def admin_back(m): bot_admin.send_message(m.chat.id, "Меню", reply_markup=kb_admin())

@bot_admin.message_handler(func=lambda m: m.text=="🏪 Заявки магазинов" and m.from_user.id==config.ADMIN_ID)
def admin_req_shops(m):
    shops = db("SELECT * FROM shops WHERE status='pending'", fetch="all")
    if not shops:
        bot_admin.send_message(m.chat.id, "🏪 Заявок нет.", reply_markup=kb_admin_req()); return
    for s in shops:
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("✅ Одобрить", callback_data=f"shop_ok_{s[0]}"),
               types.InlineKeyboardButton("❌ Отклонить", callback_data=f"shop_no_{s[0]}"))
        bot_admin.send_message(m.chat.id,
            f"🏪 {s[2]}\n📍 {s[3]}\n📞 {s[4]}\n✈️ {s[5]}\n📱 {s[6]}\n👤 {s[7]}",
            reply_markup=kb)

@bot_admin.message_handler(func=lambda m: m.text=="🚚 Заявки курьеров" and m.from_user.id==config.ADMIN_ID)
def admin_req_cour(m):
    crs = db("SELECT * FROM couriers WHERE status='pending'", fetch="all")
    if not crs:
        bot_admin.send_message(m.chat.id, "🚚 Заявок нет.", reply_markup=kb_admin_req()); return
    for c in crs:
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("✅ Одобрить", callback_data=f"cour_ok_{c[0]}"),
               types.InlineKeyboardButton("❌ Отклонить", callback_data=f"cour_no_{c[0]}"))
        bot_admin.send_message(m.chat.id,
            f"🚚 {c[2]}\n📞 {c[3]}\n📍 {c[4]}\n🚗 {c[5]}\n💳 {c[6]}",
            reply_markup=kb)

@bot_admin.message_handler(func=lambda m: m.text=="📅 Заявки смен" and m.from_user.id==config.ADMIN_ID)
def admin_req_shifts(m):
    shifts = db("SELECT s.*, c.name FROM shifts s JOIN couriers c ON c.id=s.courier_id WHERE s.date=? AND s.status='booked'", (today(),), fetch="all")
    if not shifts:
        bot_admin.send_message(m.chat.id, "📅 Заявок нет.", reply_markup=kb_admin_req()); return
    for s in shifts:
        v = config.SHIFT_SLOTS.get(s[3], {})
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("✅ Подтвердить", callback_data=f"shift_ok_{s[0]}"),
               types.InlineKeyboardButton("❌ Отменить", callback_data=f"shift_no_{s[0]}"))
        bot_admin.send_message(m.chat.id,
            f"📅 {s[5]}\n{v.get('name','?')} {v.get('start','?')}-{v.get('end','?')}",
            reply_markup=kb)

@bot_admin.message_handler(func=lambda m: m.text=="💳 Заявки выплат" and m.from_user.id==config.ADMIN_ID)
def admin_req_wd(m):
    ws = db("SELECT w.*, c.name, c.phone, c.card FROM withdrawals w JOIN couriers c ON c.id=w.courier_id WHERE w.status='pending'", fetch="all")
    if not ws:
        bot_admin.send_message(m.chat.id, "💳 Заявок нет.", reply_markup=kb_admin_req()); return
    for w in ws:
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("✅ Подтвердить", callback_data=f"wok_{w[0]}"),
               types.InlineKeyboardButton("❌ Отклонить", callback_data=f"wno_{w[0]}"))
        bot_admin.send_message(m.chat.id,
            f"💳 #{w[0]}\n🚚 {w[5]}\n📞 {w[6]}\n💰 {w[2]:.2f}\n💳 {w[3]}",
            reply_markup=kb)

@bot_admin.message_handler(func=lambda m: m.text=="❌ Отмены заявок" and m.from_user.id==config.ADMIN_ID)
def admin_req_cancel(m):
    cancels = db("SELECT * FROM orders WHERE status='cancel' ORDER BY id DESC LIMIT 20", fetch="all")
    if not cancels:
        bot_admin.send_message(m.chat.id, "❌ Отмен нет.", reply_markup=kb_admin_req()); return
    txt = f"❌ Отменённые: {len(cancels)}\n\n"
    for o in cancels[:10]:
        txt += f"#{o[0]} {o[3]}\n🎯 {o[5][:40]}\n💰 {o[11]:.2f}\n\n"
    bot_admin.send_message(m.chat.id, txt, reply_markup=kb_admin_req())

@bot_admin.message_handler(func=lambda m: m.text=="🏪 Магазины" and m.from_user.id==config.ADMIN_ID)
def admin_shops(m):
    shops = db("SELECT * FROM shops WHERE status='active'", fetch="all")
    if not shops:
        bot_admin.send_message(m.chat.id, "🏪 Активных нет."); return
    tot=0; rev=0.0; cm=0.0
    for s in shops:
        orders = db("SELECT * FROM orders WHERE shop_id=?", (s[0],), "all")
        r = sum(o[11] for o in orders if o[11])
        c = sum(o[12] for o in orders if o[12])
        tot += len(orders); rev += r; cm += c
        rating = s[9] if len(s) > 9 else 0
        cnt = s[10] if len(s) > 10 else 0
        txt = f"🏪 {s[2]}\n📍 {s[3]}\n📞 {s[4]}\n👤 {s[7]}\n\n📦 {len(orders)}\n💰 {r:.2f}\n💵 {c:.2f}"
        if rating and cnt: txt += f"\n⭐ {rating} ({cnt})"
        bot_admin.send_message(m.chat.id, txt)
    bot_admin.send_message(m.chat.id, f"📊 ИТОГО\n🏪 {len(shops)}\n📦 {tot}\n💰 {rev:.2f}\n💵 {cm:.2f}")

@bot_admin.message_handler(func=lambda m: m.text=="🚚 Курьеры" and m.from_user.id==config.ADMIN_ID)
def admin_cour(m):
    crs = db("SELECT * FROM couriers WHERE status='active'", fetch="all")
    if not crs:
        bot_admin.send_message(m.chat.id, "🚚 Активных нет."); return
    td=0; te=0.0; tb=0.0; active_coords = []
    states = {"off": "⚪", "on": "🟢", "break": "☕", "busy": "🚚"}
    for c in crs:
        d = db("SELECT COUNT(*) FROM orders WHERE courier_id=? AND status='done'", (c[0],), "one")[0]
        e = db("SELECT COALESCE(SUM(courier_fee),0) FROM orders WHERE courier_id=? AND status='done'", (c[0],), "one")[0]
        td+=d; te+=e; tb+=c[7]
        state = c[9] if len(c) > 9 else "off"
        rating = c[10] if len(c) > 10 else 0
        cnt = c[11] if len(c) > 11 else 0
        txt = f"{states.get(state,'⚪')} {c[2]}\n📞 {c[3]}\n📍 {c[4]}\n\n✅ {d}\n💰 {e:.2f}\n💵 {c[7]:.2f}"
        if rating and cnt: txt += f"\n⭐ {rating} ({cnt})"
        if len(c) > 13 and c[13]:
            txt += f"\n\n📍 {c[13]:.5f}, {c[14]:.5f}"
            active_coords.append((c[2], c[13], c[14]))
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("🗺 Карта", url=geo_link(c[13], c[14])))
            bot_admin.send_message(m.chat.id, txt, reply_markup=kb)
        else:
            bot_admin.send_message(m.chat.id, txt)
    bot_admin.send_message(m.chat.id, f"📊 ИТОГО\n🚚 {len(crs)}\n✅ {td}\n💰 {te:.2f}\n💵 {tb:.2f}")

@bot_admin.message_handler(func=lambda m: m.text=="💰 Финансы" and m.from_user.id==config.ADMIN_ID)
def admin_fin(m):
    oa = db("SELECT COUNT(*) FROM orders", fetch="one")[0]
    sc = db("SELECT COUNT(*) FROM shops WHERE status='active'", fetch="one")[0]
    cc = db("SELECT COUNT(*) FROM couriers WHERE status='active'", fetch="one")[0]
    if oa == 0 and sc == 0 and cc == 0:
        bot_admin.send_message(m.chat.id, "💰 Данных нет."); return
    r = db("SELECT COUNT(*), COALESCE(SUM(delivery_price),0), COALESCE(SUM(commission),0), COALESCE(SUM(courier_fee),0) FROM orders WHERE payment_status='confirmed'", fetch="one")
    od = db("SELECT COUNT(*) FROM orders WHERE status='done'", fetch="one")[0]
    oact = db("SELECT COUNT(*) FROM orders WHERE status IN ('going','delivering','at_client')", fetch="one")[0]
    po = db("SELECT COALESCE(SUM(amount),0) FROM withdrawals WHERE status='approved'", fetch="one")[0]
    cb = db("SELECT COALESCE(SUM(balance),0) FROM couriers", fetch="one")[0]
    pen = db("SELECT COALESCE(SUM(penalty),0) FROM shifts", fetch="one")[0]
    txt = (f"💰 ФИНАНСЫ\n"
           f"━━━━━━━━━━━━━━━\n\n"
           f"📦 Заказы: {oa}\n"
           f"✅ Доставлено: {od}\n"
           f"🚚 В работе: {oact}\n\n"
           f"🏪 Магазины: {sc}\n"
           f"🚚 Курьеры: {cc}\n\n"
           f"💵 Мои: {r[2]:.2f}\n"
           f"От магазинов: {r[1]:.2f}")
    if pen > 0: txt += f"\n⚠️ Штрафы: {pen:.2f}"
    txt += (f"\n\n🚚 КУРЬЕРАМ\n"
            f"Должен: {cb:.2f}\n"
            f"Выплачено: {po:.2f}\n"
            f"Всего: {r[3]:.2f}\n\n"
            f"💳 {config.CARD_NUMBER}")
    bot_admin.send_message(m.chat.id, txt)

@bot_admin.message_handler(func=lambda m: m.text=="💳 Выплаты" and m.from_user.id==config.ADMIN_ID)
def admin_wd(m):
    ws = db("SELECT w.*, c.name, c.phone, c.card FROM withdrawals w JOIN couriers c ON c.id=w.courier_id WHERE w.status='pending'", fetch="all")
    bl = db("SELECT name, balance, card FROM couriers WHERE status='active' AND balance>0 ORDER BY balance DESC", fetch="all")
    if not ws and not bl:
        bot_admin.send_message(m.chat.id, "💳 Заявок нет."); return
    txt = "💳 ВЫПЛАТЫ\n\n"
    if ws: txt += f"📤 Заявок: {len(ws)}\n"
    if bl:
        tb = sum(b[1] for b in bl); txt += f"\n💰 Должен: {tb:.2f}\n"
        for b in bl: txt += f"• {b[0]}: {b[1]:.2f}\n"
    bot_admin.send_message(m.chat.id, txt)
    for w in ws:
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("✅ Подтвердить", callback_data=f"wok_{w[0]}"),
               types.InlineKeyboardButton("❌ Отклонить", callback_data=f"wno_{w[0]}"))
        bot_admin.send_message(m.chat.id,
            f"📤 #{w[0]}\n🚚 {w[5]}\n💰 {w[2]:.2f}\n💳 {w[3]}",
            reply_markup=kb)

@bot_admin.message_handler(func=lambda m: m.text=="📅 Смены" and m.from_user.id==config.ADMIN_ID)
def admin_shifts(m):
    crs = db("SELECT COUNT(*) FROM couriers WHERE status='active'", fetch="one")[0]
    if crs == 0:
        bot_admin.send_message(m.chat.id, "📅 Курьеров нет."); return
    txt = f"📅 Смены на {today()}\n\n"
    total = 0
    for k, v in config.SHIFT_SLOTS.items():
        cnt = db("SELECT COUNT(*) FROM shifts WHERE date=? AND slot=?", (today(), k), "one")[0]
        free = v["limit"] - cnt; total += cnt
        txt += f"{v['name']} ({v['start']}-{v['end']})\n{cnt}/{v['limit']} - "
        txt += f"свободно {free}\n\n" if free > 0 else "заполнено\n\n"
    txt += f"Всего: {total}"
    bot_admin.send_message(m.chat.id, txt)

@bot_admin.message_handler(func=lambda m: m.text=="⭐ Отзывы" and m.from_user.id==config.ADMIN_ID)
def admin_reviews(m):
    shops = db("SELECT name, rating, reviews_count FROM shops WHERE reviews_count > 0", fetch="all")
    crs = db("SELECT name, rating, reviews_count FROM couriers WHERE reviews_count > 0", fetch="all")
    svc = db("SELECT AVG(rating), COUNT(*) FROM reviews WHERE target_type='service'", fetch="one")
    if not shops and not crs and not svc[1]:
        bot_admin.send_message(m.chat.id, "⭐ Отзывов пока нет."); return
    txt = "⭐ ОТЗЫВЫ\n━━━━━━━━━━━━━━━\n\n"
    if shops:
        txt += "🏪 Магазины:\n"
        for s in shops: txt += f"• {s[0]}: {s[1]}⭐ ({s[2]})\n"
        txt += "\n"
    if crs:
        txt += "🚚 Курьеры:\n"
        for c in crs: txt += f"• {c[0]}: {c[1]}⭐ ({c[2]})\n"
        txt += "\n"
    if svc[1]:
        txt += f"🌸 Сервис: {round(svc[0],2)}⭐ ({svc[1]})\n"
    bot_admin.send_message(m.chat.id, txt)

@bot_admin.message_handler(func=lambda m: m.text=="🔒 Доступ" and m.from_user.id==config.ADMIN_ID)
def admin_access(m):
    bot_admin.send_message(m.chat.id,
        "🔒 УПРАВЛЕНИЕ ДОСТУПОМ\n"
        "━━━━━━━━━━━━━━━\n\n"
        "Выберите раздел:",
        reply_markup=None)
    shops = db("SELECT id, name, status FROM shops ORDER BY id DESC LIMIT 20", fetch="all")
    if shops:
        bot_admin.send_message(m.chat.id, "🏪 Магазины:")
        for s in shops:
            em = "✅" if s[2]=="active" else "⏳" if s[2]=="pending" else "🚫"
            kb = types.InlineKeyboardMarkup()
            if s[2] == "active":
                kb.add(types.InlineKeyboardButton("🚫 Заблокировать", callback_data=f"block_shop_{s[0]}"))
            elif s[2] == "blocked":
                kb.add(types.InlineKeyboardButton("✅ Открыть", callback_data=f"unblock_shop_{s[0]}"))
            else:
                kb.add(types.InlineKeyboardButton("✅ Одобрить", callback_data=f"shop_ok_{s[0]}"),
                       types.InlineKeyboardButton("❌ Отклонить", callback_data=f"shop_no_{s[0]}"))
            bot_admin.send_message(m.chat.id, f"{em} {s[1]}", reply_markup=kb)
    crs = db("SELECT id, name, status FROM couriers ORDER BY id DESC LIMIT 20", fetch="all")
    if crs:
        bot_admin.send_message(m.chat.id, "🚚 Курьеры:")
        for c in crs:
            em = "✅" if c[2]=="active" else "⏳" if c[2]=="pending" else "🚫"
            kb = types.InlineKeyboardMarkup()
            if c[2] == "active":
                kb.add(types.InlineKeyboardButton("🚫 Заблокировать", callback_data=f"block_cour_{c[0]}"))
            elif c[2] == "blocked":
                kb.add(types.InlineKeyboardButton("✅ Открыть", callback_data=f"unblock_cour_{c[0]}"))
            else:
                kb.add(types.InlineKeyboardButton("✅ Одобрить", callback_data=f"cour_ok_{c[0]}"),
                       types.InlineKeyboardButton("❌ Отклонить", callback_data=f"cour_no_{c[0]}"))
            bot_admin.send_message(m.chat.id, f"{em} {c[1]}", reply_markup=kb)

@bot_admin.message_handler(func=lambda m: m.text=="📜 Логи" and m.from_user.id==config.ADMIN_ID)
def admin_logs(m):
    bot_admin.send_message(m.chat.id,
        "📜 Логи\n"
        "━━━━━━━━━━━━━━━\n\n"
        "Сюда приходят все важные события:\n"
        "• новые заказы\n"
        "• взятие заказов курьерами\n"
        "• доставки\n"
        "• отмены\n"
        "• запросы на вывод\n"
        "• блокировки\n\n"
        "Всё уже летит в этот чат автоматически ✨")

# ===== CALLBACK АДМИНА =====
@bot_admin.callback_query_handler(func=lambda c: c.data.startswith("shop_ok_"))
def cb_shop_ok(c):
    if c.from_user.id != config.ADMIN_ID: return
    sid = int(c.data.split("_")[2])
    db("UPDATE shops SET status='active' WHERE id=?", (sid,))
    s = db("SELECT tg_id,name FROM shops WHERE id=?", (sid,), "one")
    bot_admin.edit_message_text(f"✅ {s[1]} ОДОБРЕН", c.message.chat.id, c.message.message_id)
    try: bot_shop.send_message(s[0], "✅ Ваш магазин одобрен! Отправьте /start")
    except: pass
    log(f"Магазин {s[1]} одобрен")

@bot_admin.callback_query_handler(func=lambda c: c.data.startswith("shop_no_"))
def cb_shop_no(c):
    if c.from_user.id != config.ADMIN_ID: return
    sid = int(c.data.split("_")[2])
    db("UPDATE shops SET status='blocked' WHERE id=?", (sid,))
    s = db("SELECT tg_id,name FROM shops WHERE id=?", (sid,), "one")
    bot_admin.edit_message_text(f"❌ {s[1]} ОТКЛОНЁН", c.message.chat.id, c.message.message_id)
    try: bot_shop.send_message(s[0], "❌ Ваш магазин отклонён.")
    except: pass

@bot_admin.callback_query_handler(func=lambda c: c.data.startswith("cour_ok_"))
def cb_cour_ok(c):
    if c.from_user.id != config.ADMIN_ID: return
    cid = int(c.data.split("_")[2])
    db("UPDATE couriers SET status='active' WHERE id=?", (cid,))
    cc = db("SELECT tg_id,name FROM couriers WHERE id=?", (cid,), "one")
    bot_admin.edit_message_text(f"✅ {cc[1]} ОДОБРЕН", c.message.chat.id, c.message.message_id)
    try: bot_courier.send_message(cc[0], "✅ Вы одобрены! Отправьте /start")
    except: pass
    log(f"Курьер {cc[1]} одобрен")

@bot_admin.callback_query_handler(func=lambda c: c.data.startswith("cour_no_"))
def cb_cour_no(c):
    if c.from_user.id != config.ADMIN_ID: return
    cid = int(c.data.split("_")[2])
    db("UPDATE couriers SET status='blocked' WHERE id=?", (cid,))
    cc = db("SELECT tg_id,name FROM couriers WHERE id=?", (cid,), "one")
    bot_admin.edit_message_text(f"❌ {cc[1]} ОТКЛОНЁН", c.message.chat.id, c.message.message_id)
    try: bot_courier.send_message(cc[0], "❌ Вас отклонили.")
    except: pass

@bot_admin.callback_query_handler(func=lambda c: c.data.startswith("block_shop_"))
def cb_block_shop(c):
    if c.from_user.id != config.ADMIN_ID: return
    sid = int(c.data.split("_")[2])
    db("UPDATE shops SET status='blocked' WHERE id=?", (sid,))
    s = db("SELECT tg_id,name FROM shops WHERE id=?", (sid,), "one")
    bot_admin.edit_message_text(f"🚫 {s[1]} ЗАБЛОКИРОВАН", c.message.chat.id, c.message.message_id)
    try: bot_shop.send_message(s[0], "🚫 Доступ закрыт админом.")
    except: pass
    log(f"Магазин {s[1]} заблокирован")

@bot_admin.callback_query_handler(func=lambda c: c.data.startswith("unblock_shop_"))
def cb_unblock_shop(c):
    if c.from_user.id != config.ADMIN_ID: return
    sid = int(c.data.split("_")[2])
    db("UPDATE shops SET status='active' WHERE id=?", (sid,))
    s = db("SELECT tg_id,name FROM shops WHERE id=?", (sid,), "one")
    bot_admin.edit_message_text(f"✅ {s[1]} ОТКРЫТ", c.message.chat.id, c.message.message_id)
    try: bot_shop.send_message(s[0], "✅ Доступ открыт! /start")
    except: pass
    log(f"Магазин {s[1]} разблокирован")

@bot_admin.callback_query_handler(func=lambda c: c.data.startswith("block_cour_"))
def cb_block_cour(c):
    if c.from_user.id != config.ADMIN_ID: return
    cid = int(c.data.split("_")[2])
    db("UPDATE couriers SET status='blocked' WHERE id=?", (cid,))
    cc = db("SELECT tg_id,name FROM couriers WHERE id=?", (cid,), "one")
    bot_admin.edit_message_text(f"🚫 {cc[1]} ЗАБЛОКИРОВАН", c.message.chat.id, c.message.message_id)
    try: bot_courier.send_message(cc[0], "🚫 Доступ закрыт админом.")
    except: pass
    log(f"Курьер {cc[1]} заблокирован")

@bot_admin.callback_query_handler(func=lambda c: c.data.startswith("unblock_cour_"))
def cb_unblock_cour(c):
    if c.from_user.id != config.ADMIN_ID: return
    cid = int(c.data.split("_")[2])
    db("UPDATE couriers SET status='active' WHERE id=?", (cid,))
    cc = db("SELECT tg_id,name FROM couriers WHERE id=?", (cid,), "one")
    bot_admin.edit_message_text(f"✅ {cc[1]} ОТКРЫТ", c.message.chat.id, c.message.message_id)
    try: bot_courier.send_message(cc[0], "✅ Доступ открыт! /start")
    except: pass
    log(f"Курьер {cc[1]} разблокирован")

@bot_admin.callback_query_handler(func=lambda c: c.data.startswith("shift_ok_"))
def cb_shift_ok(c):
    if c.from_user.id != config.ADMIN_ID: return
    sid = int(c.data.split("_")[2])
    sh = db("SELECT s.*, c.tg_id, c.name FROM shifts s JOIN couriers c ON c.id=s.courier_id WHERE s.id=?", (sid,), "one")
    if not sh: bot_admin.answer_callback_query(c.id); return
    v = config.SHIFT_SLOTS.get(sh[3], {})
    bot_admin.edit_message_text(f"✅ Смена подтверждена", c.message.chat.id, c.message.message_id)
    try: bot_courier.send_message(sh[6], f"✅ Смена подтверждена\n{v.get('name','?')}")
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
    try: bot_courier.send_message(sh[6], "❌ Смена отклонена админом.")
    except: pass
    bot_admin.answer_callback_query(c.id)

@bot_admin.callback_query_handler(func=lambda c: c.data.startswith("wok_"))
def cb_wok(c):
    if c.from_user.id != config.ADMIN_ID: return
    wid = int(c.data.split("_")[1])
    w = db("SELECT * FROM withdrawals WHERE id=?", (wid,), "one")
    if not w: bot_admin.answer_callback_query(c.id); return
    db("UPDATE withdrawals SET status='approved' WHERE id=?", (wid,))
    db("UPDATE couriers SET balance=balance-? WHERE id=?", (w[2], w[1]))
    ci = db("SELECT tg_id FROM couriers WHERE id=?", (w[1],), "one")
    bot_admin.edit_message_text(f"✅ Выплачено {w[2]:.2f}", c.message.chat.id, c.message.message_id)
    try: bot_courier.send_message(ci[0], f"✅ Вывод {w[2]:.2f} подтверждён.")
    except: pass
    log(f"Выплата {w[2]:.2f}")
    bot_admin.answer_callback_query(c.id)

@bot_admin.callback_query_handler(func=lambda c: c.data.startswith("wno_"))
def cb_wno(c):
    if c.from_user.id != config.ADMIN_ID: return
    wid = int(c.data.split("_")[1])
    w = db("SELECT * FROM withdrawals WHERE id=?", (wid,), "one")
    db("UPDATE withdrawals SET status='rejected' WHERE id=?", (wid,))
    bot_admin.edit_message_text(f"❌ #{wid} ОТКЛОНЁН", c.message.chat.id, c.message.message_id)
    if w:
        ci = db("SELECT tg_id FROM couriers WHERE id=?", (w[1],), "one")
        try: bot_courier.send_message(ci[0], f"❌ Заявка на вывод {w[2]:.2f} отклонена.")
        except: pass
    bot_admin.answer_callback_query(c.id)

# ===== АВТОШТРАФ =====
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
                    try: bot_courier.send_message(sh[5], f"⚠️ Штраф\n📅 {slot['name']}\n💰 {config.SHIFT_PENALTY}")
                    except: pass
                    try: bot_admin.send_message(config.ADMIN_ID, f"⚠️ Автоштраф\n🚚 {sh[6]}\n💰 {config.SHIFT_PENALTY}")
                    except: pass
        except Exception as e: print(f"check_shifts: {e}")

# ===== ЗАПУСК =====
def run_bot(bot, name):
    print(f"Запуск: {name}")
    while True:
        try: bot.infinity_polling(timeout=30, long_polling_timeout=20)
        except Exception as e:
            print(f"{name}: {e}"); time.sleep(5)

if __name__ == "__main__":
    print("Инициализация БД...")
    db_init()
    print("База готова")
    for b, n in [(bot_shop,"Магазин"),(bot_courier,"Курьер"),(bot_admin,"Админ"),(bot_client,"Клиент")]:
        threading.Thread(target=run_bot, args=(b, n), daemon=True).start()
    threading.Thread(target=check_shifts, daemon=True).start()
    print("Автоштраф запущен")
    print("Все боты запущены!")
    while True: time.sleep(60)

