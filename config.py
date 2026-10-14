# -*- coding: utf-8 -*-
"""
SLIPI — конфигурация проекта
Доставка цветов и подарков
"""
import os
from dotenv import load_dotenv

load_dotenv()


# ═══════════════════════════════════════════
#   ТОКЕНЫ БОТОВ (Telegram)
# ═══════════════════════════════════════════
CLIENT_TOKEN  = os.getenv("CLIENT_TOKEN",  "")
SHOP_TOKEN    = os.getenv("SHOP_TOKEN",    "")
COURIER_TOKEN = os.getenv("COURIER_TOKEN", "")
ADMIN_TOKEN   = os.getenv("ADMIN_TOKEN",   "")


# ═══════════════════════════════════════════
#   АДМИН
# ═══════════════════════════════════════════
ADMIN_ID   = int(os.getenv("ADMIN_ID", 0))
ADMIN_NAME = "Максим"


# ═══════════════════════════════════════════
#   БАЗА ДАННЫХ (PostgreSQL)
# ═══════════════════════════════════════════
DB_HOST     = os.getenv("DB_HOST", "localhost")
DB_PORT     = int(os.getenv("DB_PORT", 5432))
DB_USER     = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
DB_NAME     = os.getenv("DB_NAME", "slipi")

DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"


# ═══════════════════════════════════════════
#   ОПЛАТА (карта для приёма)
# ═══════════════════════════════════════════
CARD_NUMBER = "2200 1523 3577 2441"
CARD_HOLDER = "МАКСИМ С."
BANK_NAME   = "Альфа-Банк"
SBP_PHONE   = "+7 991 792-92-51"


# ═══════════════════════════════════════════
#   ФИНАНСЫ
# ═══════════════════════════════════════════
COMMISSION_PERCENT = 25        # комиссия с доставки
DELIVERY_PRICE = 350           # стоимость доставки

BULK_DISCOUNT_PERCENT = 3       # скидка 3% от 3+ букетов
BULK_DISCOUNT_MIN_BOUQUETS = 3

CLIENT_WITHDRAW_COMMISSION = 5  # % за вывод с баланса клиента
CLIENT_MIN_WITHDRAW = 500       # мин. вывод

COURIER_MIN_WITHDRAW = 500
COURIER_INSTANT_WITHDRAW_MIN = 100
COURIER_INSTANT_WITHDRAW_PERCENT = 2

# Наценка платформы (СТУПЕНЧАТАЯ)
MARKUP_STEPS = [
    (0,     500,   50),
    (500,   1000,  100),
    (1000,  1500,  150),
    (1500,  2000,  200),
    (2000,  2500,  250),
    (2500,  3000,  300),
    (3000,  4000,  400),
    (4000,  5000,  500),
    (5000,  7000,  600),
    (7000,  10000, 800),
    (10000, float('inf'), 1000),
]


# ═══════════════════════════════════════════
#   БОНУСЫ КУРЬЕРАМ
# ═══════════════════════════════════════════
BONUS_PER_10_ORDERS = 50


# ═══════════════════════════════════════════
#   РЕФЕРАЛЬНАЯ ПРОГРАММА
# ═══════════════════════════════════════════
REFERRAL_PERCENT = 5
REFERRAL_MONTHS = 3


# ═══════════════════════════════════════════
#   BOOST (прибавка к заказу)
# ═══════════════════════════════════════════
BOOST_MAX_PERCENT = 20
BOOST_TRIGGER_MINUTES = 30


# ═══════════════════════════════════════════
#   ГОРОД И РАБОТА
# ═══════════════════════════════════════════
CITY = "Киров"
WORK_HOURS = "7:00 – 24:00"
WORK_DAYS = "Пн – Вс"
WORK_START_HOUR = 7
WORK_END_HOUR = 24
NIGHT_MODE_START = 23
NIGHT_MODE_END = 8
NIGHT_ORDER_DEADLINE_HOUR = 10


# ═══════════════════════════════════════════
#   АВТООТМЕНА
# ═══════════════════════════════════════════
DAY_ORDER_TIMEOUT_MINUTES = 30
NIGHT_ORDER_TIMEOUT_HOURS = 2
ORDER_REMINDER_INTERVAL_MIN = 10
PREORDER_DAYS_AHEAD = 2


# ═══════════════════════════════════════════
#   ГЕО
# ═══════════════════════════════════════════
COURIER_GEO_UPDATE_MINUTES = 5
NEARBY_SHOPS_RADIUS_KM = 10


# ═══════════════════════════════════════════
#   СЕРВИС
# ═══════════════════════════════════════════
SERVICE_NAME = "SLIPI"
SERVICE_VK = "vk.com/slipi221"
SERVICE_VK_TG = "@slipi221"
SUPPORT_TG = "@slipi221"
SUPPORT_PHONE = "+7 991 792-92-51"


# ═══════════════════════════════════════════
#   КАТЕГОРИИ ТОВАРОВ
# ═══════════════════════════════════════════
CATEGORIES = {
    "bouquets": {"name": "💐 Букеты",    "emoji": "💐"},
    "potted":   {"name": "🪴 Горшечные", "emoji": "🪴"},
    "cactus":   {"name": "🌵 Кактусы",   "emoji": "🌵"},
    "toys":     {"name": "🧸 Игрушки",   "emoji": "🧸"},
    "balloons": {"name": "🎈 Шары",      "emoji": "🎈"},
    "sweets":   {"name": "🍫 Сладкое",   "emoji": "🍫"},
    "cards":    {"name": "💌 Открытки",  "emoji": "💌"},
    "candles":  {"name": "🕯 Свечи",     "emoji": "🕯"},
    "decor":    {"name": "🎀 Декор",     "emoji": "🎀"},
    "other":    {"name": "🌿 Другое",    "emoji": "🌿"},
}


# ═══════════════════════════════════════════
#   СМЕНЫ КУРЬЕРОВ
# ═══════════════════════════════════════════
SHIFT_PENALTY = 500
SHIFT_GRACE_MIN = 30

SHIFT_SLOTS = {
    "morning": {"name": "🌅 Утренняя", "start": "07:00", "end": "15:00", "limit": 3},
    "day":     {"name": "☀️ Дневная",  "start": "09:00", "end": "18:00", "limit": 4},
    "evening": {"name": "🌆 Вечерняя", "start": "15:00", "end": "23:00", "limit": 3},
    "night":   {"name": "🌙 Ночная",   "start": "18:00", "end": "00:00", "limit": 2},
}

SHIFT_STATUS = {
    "booked": "📘 Записан",
    "active": "🟢 На смене",
    "done":   "✅ Отработана",
    "missed": "⚠️ Пропущена",
}


# ═══════════════════════════════════════════
#   СТАТУСЫ КУРЬЕРА
# ═══════════════════════════════════════════
COURIER_STATES = {
    "off":   "⚪ Не на смене",
    "on":    "🟢 На смене",
    "break": "☕ Перерыв",
    "busy":  "🚗 На заказе",
}


# ═══════════════════════════════════════════
#   СТАТУСЫ ЗАКАЗА
# ═══════════════════════════════════════════
STATUS_EMOJI = {
    "new":        "🆕",
    "wait":       "⏳",
    "going":      "🚗",
    "picked":     "📦",
    "delivering": "🚴",
    "at_client":  "📍",
    "done":       "✅",
    "cancel":     "❌",
    "refunded":   "💸",
}

STATUS_TEXT = {
    "new":        "Новый",
    "wait":       "Ждёт курьера",
    "going":      "Еду в магазин",
    "picked":     "Забрал в магазине",
    "delivering": "Везёт клиенту",
    "at_client":  "У клиента",
    "done":       "Доставлено",
    "cancel":     "Отменено",
    "refunded":   "Возврат",
}


# ═══════════════════════════════════════════
#   ВРЕМЯ ДОСТАВКИ (слоты)
# ═══════════════════════════════════════════
DELIVERY_SLOTS = {
    "morning": {
        "name": "🌅 Утро",
        "hours": "07:00 – 12:00",
        "slots": ["07:00-08:00", "08:00-09:00", "09:00-10:00", "10:00-11:00", "11:00-12:00"],
    },
    "day": {
        "name": "☀️ День",
        "hours": "12:00 – 17:00",
        "slots": ["12:00-13:00", "13:00-14:00", "14:00-15:00", "15:00-16:00", "16:00-17:00"],
    },
    "evening": {
        "name": "🌆 Вечер",
        "hours": "17:00 – 22:00",
        "slots": ["17:00-18:00", "18:00-19:00", "19:00-20:00", "20:00-21:00", "21:00-22:00"],
    },
    "night": {
        "name": "🌙 Ночь",
        "hours": "22:00 – 00:00",
        "slots": ["22:00-23:00", "23:00-00:00"],
    },
}


# ═══════════════════════════════════════════
#   ПОЛЕЗНЫЕ ФУНКЦИИ
# ═══════════════════════════════════════════

def get_markup(price: float) -> float:
    """Наценка платформы по ступенькам."""
    for min_p, max_p, markup in MARKUP_STEPS:
        if min_p <= price < max_p:
            return markup
    return 1000


def get_client_price(shop_price: float) -> float:
    """Цена для клиента."""
    return shop_price + get_markup(shop_price)


def get_courier_fee(delivery_price: float = DELIVERY_PRICE) -> float:
    """Сколько получит курьер с доставки."""
    return round(delivery_price * (100 - COMMISSION_PERCENT) / 100, 2)


def get_platform_fee(delivery_price: float = DELIVERY_PRICE) -> float:
    """Сколько получит платформа с доставки."""
    return round(delivery_price * COMMISSION_PERCENT / 100, 2)


def get_category_name(key: str) -> str:
    """Название категории по ключу."""
    return CATEGORIES.get(key, {}).get("name", "🌿 Другое")
