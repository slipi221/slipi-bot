# -*- coding: utf-8 -*-
"""
Flowers Express (ex-SLIPI) — конфигурация проекта

FIX Feature 8: MARKUP_PERCENT = 0.15 (было MARKUP_STEPS — ступени 50–1000₽).
FIX: NEARBY_SHOPS_RADIUS_KM = 13 (было 20) — выровнен с MAX_DELIVERY_RADIUS.
FIX: PREORDER_DAYS_AHEAD = 3 (было 2) — максимум на 3 дня вперёд.
NEW: CLIENT_BOT_USERNAME — для реферальных ссылок.
NEW: TIP_PLATFORM_PERCENT — комиссия с чаевых (10% платформе, 90% курьеру).
NEW: HOLIDAY_MARKUP_PERCENT — праздничная наценка (0 = выкл). Грузится из БД.
NEW: 4 отдельных канала для логов (Client/Shop/Courier/Admin), fallback на общий.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ═══════════════════════════════════════════
#   НАЗВАНИЕ И БРЕНДИНГ
# ═══════════════════════════════════════════
SERVICE_NAME = "Цветочный Экспресс"
SERVICE_TAG = "flowers_express"
CITY = "Киров"

# ═══════════════════════════════════════════
#   ТОКЕНЫ БОТОВ
# ═══════════════════════════════════════════
CLIENT_TOKEN  = os.getenv("CLIENT_TOKEN", "")
SHOP_TOKEN    = os.getenv("SHOP_TOKEN", "")
COURIER_TOKEN = os.getenv("COURIER_TOKEN", "")
ADMIN_TOKEN   = os.getenv("ADMIN_TOKEN", "")

# Юзернейм клиентского бота (для реферальных ссылок)
# ЗАМЕНИ на реальный!
CLIENT_BOT_USERNAME = os.getenv("CLIENT_BOT_USERNAME", "flowers_express_bot")

# ═══════════════════════════════════════════
#   АДМИН
# ═══════════════════════════════════════════
ADMIN_ID   = int(os.getenv("ADMIN_ID", 0))
ADMIN_NAME = "Максим"

# Общий канал (fallback)
ADMIN_CHANNEL_ID = os.getenv("ADMIN_CHANNEL_ID", "")

# 4 отдельных канала для логов (Feature 1).
# Если пусто — используется ADMIN_CHANNEL_ID (fallback).
ADMIN_CHANNEL_ID_CLIENT  = os.getenv("ADMIN_CHANNEL_ID_CLIENT", "") or ADMIN_CHANNEL_ID
ADMIN_CHANNEL_ID_SHOP    = os.getenv("ADMIN_CHANNEL_ID_SHOP", "")   or ADMIN_CHANNEL_ID
ADMIN_CHANNEL_ID_COURIER = os.getenv("ADMIN_CHANNEL_ID_COURIER", "") or ADMIN_CHANNEL_ID
ADMIN_CHANNEL_ID_ADMIN   = os.getenv("ADMIN_CHANNEL_ID_ADMIN", "")   or ADMIN_CHANNEL_ID

# ═══════════════════════════════════════════
#   БАЗА ДАННЫХ
# ═══════════════════════════════════════════
DATABASE_URL_ENV = os.getenv("DATABASE_URL", "")

if DATABASE_URL_ENV:
    DATABASE_URL = DATABASE_URL_ENV
else:
    DATA_DIR = os.getenv("DATA_DIR", "data")
    Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
    DATABASE_URL = f"sqlite+aiosqlite:///{DATA_DIR}/flowers_express.db"

# ═══════════════════════════════════════════
#   ОПЛАТА
# ═══════════════════════════════════════════
CARD_NUMBER = "2200 1523 3577 2441"
CARD_HOLDER = "МАКСИМ С."
BANK_NAME   = "Альфа-Банк"
SBP_PHONE   = "+7 991 792-92-51"

# ═══════════════════════════════════════════
#   ЗОНЫ ДОСТАВКИ И НАЦЕНКИ
# ═══════════════════════════════════════════
MAX_DELIVERY_RADIUS = 13

# (от_км, до_км, клиент_платит, курьер_получает)
DELIVERY_ZONES = [
    (0,  3,   350, 280),
    (3,  6,   420, 330),
    (6,  10,  500, 380),
    (10, 13,  600, 450),
]

# FIX Feature 8: наценка +15% ко всем товарам (было MARKUP_STEPS — фикс. ступени).
# Округление до 10₽. Доставку не трогаем.
MARKUP_PERCENT = 0.15

# FIX Feature 9: праздничная наценка (грузится из БД при старте, 0 = выкл).
# Пример: 15 → +15% ко всем товарам (помимо обычной наценки).
HOLIDAY_MARKUP_PERCENT = 0.0

# ═══════════════════════════════════════════
#   ФИНАНСЫ И БОНУСЫ
# ═══════════════════════════════════════════
BULK_DISCOUNT_PERCENT = 3
BULK_DISCOUNT_MIN_BOUQUETS = 3

# Комиссии при выводе
CLIENT_WITHDRAW_COMMISSION = 5    # клиент платит 5%
COURIER_WITHDRAW_COMMISSION = 0   # курьер — 0%
SHOP_WITHDRAW_COMMISSION = 0      # магазин — 0%

CLIENT_MIN_WITHDRAW = 500
COURIER_MIN_WITHDRAW = 500

BONUS_PER_10_ORDERS = 50
URGENT_BONUS = 50
REFERRAL_PERCENT = 5
REFERRAL_MONTHS = 3

# Чаевые (Feature 7): платформа берёт 10%, курьеру идёт 90%
TIP_PLATFORM_PERCENT = 10

BOOST_MAX_PERCENT = 20
BOOST_TRIGGER_MINUTES = 30

# ═══════════════════════════════════════════
#   БАНКИ (для выплат)
# ═══════════════════════════════════════════
BANKS = [
    "🔵 Сбербанк",
    "🔴 Альфа-Банк",
    "🟡 Тинькофф",
    "🟢 ВТБ",
    "🟣 Райффайзен",
    "⚫ Газпромбанк",
    "🔵 Россельхозбанк",
    "🟡 Открытие",
    "🟠 Совкомбанк",
    "⚪ Другой",
]

# ═══════════════════════════════════════════
#   ГОРОД И РАБОТА
# ═══════════════════════════════════════════
WORK_HOURS = "7:00 – 24:00"
WORK_DAYS = "Пн – Вс"
WORK_START_HOUR = 7
WORK_END_HOUR = 24

NIGHT_MODE_START = 23
NIGHT_MODE_END = 8
NIGHT_ORDER_DEADLINE_HOUR = 10

# ═══════════════════════════════════════════
#   АВТООТМЕНА И ПРЕДЗАКАЗ
# ═══════════════════════════════════════════
DAY_ORDER_TIMEOUT_MINUTES = 30
ORDER_REMINDER_INTERVAL_MIN = 10
PREORDER_DAYS_AHEAD = 3  # FIX: было 2

# ═══════════════════════════════════════════
#   ГЕО И СЕРВИС
# ═══════════════════════════════════════════
COURIER_GEO_UPDATE_MINUTES = 5
NEARBY_SHOPS_RADIUS_KM = 13  # FIX: было 20 (выровнено с MAX_DELIVERY_RADIUS)
SERVICE_VK = "vk.com/flowers_express"
SERVICE_VK_TG = "@flowers_express"
SUPPORT_TG = "@flowers_express_support"
SUPPORT_PHONE = "+7 991 792-92-51"

# ═══════════════════════════════════════════
#   КАТЕГОРИИ
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
#   СТАТУСЫ
# ═══════════════════════════════════════════
STATUS_EMOJI = {
    "new": "🆕", "pending": "⏳", "wait": "🔍", "going": "🚗",
    "picked": "📦", "delivering": "🚴", "at_client": "📍",
    "done": "✅", "cancel": "❌", "refunded": "💸", "problem": "🆘",
}

STATUS_TEXT = {
    "new": "Новый", "pending": "Ожидает оплаты", "wait": "Ищем курьера",
    "going": "Курьер едет в магазин", "picked": "Курьер забрал букет",
    "delivering": "Курьер везёт вам", "at_client": "Курьер у вас",
    "done": "Доставлено", "cancel": "Отменено", "refunded": "Возврат", "problem": "Проблема",
}

COURIER_STATES = {
    "off": "⚪ Не на смене", "on": "🟢 На смене",
    "break": "☕ Перерыв", "busy": "🚗 На заказе",
}

# ═══════════════════════════════════════════
#   СЛОТЫ ДОСТАВКИ
# ═══════════════════════════════════════════
DELIVERY_SLOTS = {
    "morning": {
        "name": "🌅 Утро", "hours": "07:00 – 12:00",
        "slots": ["07:00-08:00", "08:00-09:00", "09:00-10:00", "10:00-11:00", "11:00-12:00"],
    },
    "day": {
        "name": "☀️ День", "hours": "12:00 – 17:00",
        "slots": ["12:00-13:00", "13:00-14:00", "14:00-15:00", "15:00-16:00", "16:00-17:00"],
    },
    "evening": {
        "name": "🌆 Вечер", "hours": "17:00 – 22:00",
        "slots": ["17:00-18:00", "18:00-19:00", "19:00-20:00", "20:00-21:00", "21:00-22:00"],
    },
    "night": {
        "name": "🌙 Ночь", "hours": "22:00 – 00:00",
        "slots": ["22:00-23:00", "23:00-00:00"],
    },
}

WEEKDAYS = {"mon": "Пн", "tue": "Вт", "wed": "Ср", "thu": "Чт", "fri": "Пт", "sat": "Сб", "sun": "Вс"}

ADMIN_PERMISSIONS = {
    "requests": "📨 Заявки", "shops": "🏪 Магазины", "couriers": "🚴 Курьеры",
    "block": "🚫 Блокировка", "finance": "💰 Финансы", "payments": "💳 Переводы",
    "payouts": "💸 Выплаты", "settings": "⚙️ Настройки", "admins": "🔑 Админы",
    "broadcast": "📢 Рассылка", "analytics": "📊 Аналитика", "logs": "📜 Логи",
}

# ═══════════════════════════════════════════
#   ФУНКЦИИ
# ═══════════════════════════════════════════
def get_markup(price: float) -> float:
    """
    FIX Feature 8: наценка +15%, округление до 10₽.
    Пример: 500₽ → 75₽ → 80₽ (округление вверх) → клиент платит 580₽.
    """
    try:
        p = float(price)
    except (TypeError, ValueError):
        return 0.0
    if p <= 0:
        return 0.0
    raw = p * MARKUP_PERCENT
    # Округление до 10₽ (половина вверх)
    return float(int(raw / 10 + 0.5) * 10)


def get_client_price(shop_price: float) -> float:
    """
    FIX Feature 8 + Feature 9: shop_price + наценка 15% (+ праздничная наценка, если задана).
    Округление до 10₽.
    """
    try:
        p = float(shop_price)
    except (TypeError, ValueError):
        return 0.0
    base = p + get_markup(p)
    if HOLIDAY_MARKUP_PERCENT > 0:
        base = base * (1 + HOLIDAY_MARKUP_PERCENT / 100)
        base = int(base / 10 + 0.5) * 10
    return float(base)


def get_delivery_zone(distance_km: float) -> dict | None:
    if distance_km > MAX_DELIVERY_RADIUS:
        return None
    for min_km, max_km, client_pays, courier_gets in DELIVERY_ZONES:
        if min_km <= distance_km < max_km:
            return {
                "client_pays": client_pays,
                "courier_gets": courier_gets,
                "platform_gets": client_pays - courier_gets,
            }
    last = DELIVERY_ZONES[-1]
    return {
        "client_pays": last[2],
        "courier_gets": last[3],
        "platform_gets": last[2] - last[3],
    }


def get_category_name(key: str) -> str:
    return CATEGORIES.get(key, {}).get("name", "🌿 Другое")
