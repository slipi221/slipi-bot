# === ТОКЕНЫ TELEGRAM ===
CLIENT_TOKEN = "8856833031:AAGeIHsf65LwJ0_o-WDIbJAPZGJQaerSLrc"
SHOP_TOKEN = "8964453456:AAH8Lg0N9pJELGMRHk4kanj8n_IOcjt7C1c"
COURIER_TOKEN = "8726398351:AAFDOHa3AOAEptreO-4VG3C-R8RiN-M0BvQ"
ADMIN_TOKEN = "8871827276:AAEM238clLuRpOZgkJG-CzMoxSvvegFGA3s"

# === ВКОНТАКТЕ ===
VK_TOKEN = "vk1.a.uXAqB0kca3yr4WO7dwnKR5PdHWdB5ZZE2j6iXGdLyo686fkxaGfCkzfn94aBjk2ejaBF2IS5eJBhQDBTzDUX-9G_i3WJopRrh4tmpa3A8Uv2Hrlj23nfQPHtKs1Sye8BNmvFoSz4jm8AhqXDDhGMcA06WGxDE6wf5Xj2GttI0-7TkZu1A9InuSnToIZSSTW6_SpfeI2QQFu_0fc4A2wnTA"
VK_GROUP_ID = 242277871

# === АДМИН ===
ADMIN_ID = 5430837239
ADMIN_NAME = "Максим"

# === ОПЛАТА ===
CARD_NUMBER = "2200 1523 3577 2441"
CARD_HOLDER = "МАКСИМ С."
BANK_NAME = "Альфа-Банк"
SBP_PHONE = "+7 991 792-92-51"

# === ФИНАНСЫ ===
COMMISSION_PERCENT = 15
MIN_DELIVERY = 350
COURIER_MIN = 297.50

# === ГОРОД ===
CITY = "Киров"
WORK_HOURS = "7:00 – 24:00"
WORK_DAYS = "Пн – Вс"

# === СЕРВИС ===
SERVICE_NAME = "SLIPI"
SERVICE_VK = "vk.com/slipi221"
SERVICE_VK_TG = "@slipi221"
SUPPORT_TG = "@slipi221"
SUPPORT_PHONE = "+7 991 792-92-51"

# === СМЕНЫ ===
SHIFT_PENALTY = 500
SHIFT_GRACE_MIN = 30
SHIFT_SLOTS = {
    "morning": {"name": "🌅 Утренняя", "start": "07:00", "end": "15:00", "limit": 3},
    "day":     {"name": "☀️ Дневная",  "start": "09:00", "end": "18:00", "limit": 4},
    "evening": {"name": "🌆 Вечерняя", "start": "15:00", "end": "23:00", "limit": 3},
    "night":   {"name": "🌙 Ночная",   "start": "18:00", "end": "00:00", "limit": 2},
}
SHIFT_STATUS = {
    "booked": "📅 Записан",
    "active": "🟢 На смене",
    "done": "✅ Отработана",
    "missed": "⚠️ Пропущена",
}

# === СТАТУСЫ ЗАКАЗА ===
STATUS_EMOJI = {
    "new": "🆕", "wait": "⏳", "going": "🚗", "picked": "📦",
    "delivering": "🚚", "at_client": "📍", "done": "✅", "cancel": "❌",
}
STATUS_TEXT = {
    "new": "Новая", "wait": "Ждёт курьера", "going": "Еду в магазин",
    "picked": "Забрал в магазине", "delivering": "Везёт клиенту",
    "at_client": "У клиента", "done": "Доставлено", "cancel": "Отменено",
}
DELIVERY_ZONES = {
    "zone1": {"name": "🟢 Центр (до 5 км)", "price": 350},
    "zone2": {"name": "🟡 Ближние (5-10 км)", "price": 450},
    "zone3": {"name": "🟠 Средние (10-15 км)", "price": 600},
    "zone4": {"name": "🔴 Дальние (15+ км)", "price": 800},
}
