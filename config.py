# -*- coding: utf-8 -*-
import os
from dotenv import load_dotenv

load_dotenv()

SERVICE_NAME = "CityExpress"
CITY = "Киров"

# ═══ ТОКЕНЫ TELEGRAM ═══
TG_CLIENT_TOKEN = os.getenv("CLIENT_TOKEN", "")
TG_SHOP_TOKEN = os.getenv("SHOP_TOKEN", "")
TG_COURIER_TOKEN = os.getenv("COURIER_TOKEN", "")
TG_ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")

# Мостики для старых handlers (чтобы старый ТГ-код не упал)
CLIENT_TOKEN = TG_CLIENT_TOKEN
SHOP_TOKEN = TG_SHOP_TOKEN
COURIER_TOKEN = TG_COURIER_TOKEN
ADMIN_TOKEN = TG_ADMIN_TOKEN

# ═══ ТОКЕНЫ VK ═══
VK_CLIENT_TOKEN = os.getenv("VK_CLIENT_TOKEN", "")
VK_CLIENT_GROUP_ID = int(os.getenv("VK_CLIENT_GROUP_ID", 0))
VK_SHOP_TOKEN = os.getenv("VK_SHOP_TOKEN", "")
VK_SHOP_GROUP_ID = int(os.getenv("VK_SHOP_GROUP_ID", 0))
VK_COURIER_TOKEN = os.getenv("VK_COURIER_TOKEN", "")
VK_COURIER_GROUP_ID = int(os.getenv("VK_COURIER_GROUP_ID", 0))
VK_ADMIN_TOKEN = os.getenv("VK_ADMIN_TOKEN", "")
VK_ADMIN_GROUP_ID = int(os.getenv("VK_ADMIN_GROUP_ID", 0))

# ═══ АДМИНЫ ═══
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
ADMIN_IDS = [ADMIN_ID]
ADMIN_CHANNEL_ID = os.getenv("ADMIN_CHANNEL_ID", "")

# ═══ БАЗА ДАННЫХ ═══
DATABASE_URL = os.getenv("DATABASE_URL", "")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# ═══ НАШИ НОВЫЕ ПРАВИЛА ═══
MIN_ORDER_AMOUNT = 500
MIN_PLATFORM_MARGIN = 20

MARKUP_BY_CATEGORY = {
    "cafe":     0.20,
    "flowers":  0.15,
    "pharmacy": 0.15,
    "gifts":    0.15,
}

DELIVERY_ZONES = [
    (0,  2,  250, 269),
    (2,  5,  280, 300),
    (5,  10, 330, 350),
    (10, 15, 380, 400),
]
MAX_DELIVERY_RADIUS = 15

PREP_TIME = {
    "cafe": 25,
    "pharmacy": 15,
    "flowers": 10,
    "gifts": 10,
}
DELIVERY_BUFFER_MINUTES = 10

TRAVEL_TIME = {
    "zone_1": 20,
    "zone_2": 30,
    "zone_3": 45,
    "zone_4": 60,
}

SLOT_DURATION_HOURS = 1

COURIER_LEVELS = {
    "newbie":      (0,   0.00),
    "experienced": (51,  0.02),
    "pro":         (201, 0.045),
    "legend":      (501, 0.07),
}
MAX_ORDERS_PER_COURIER = 10
LATE_PENALTY_PER_20_MIN = 50

CLIENT_WITHDRAW_COMMISSION = 5.0
COURIER_WITHDRAW_COMMISSION = 1.5
SHOP_WITHDRAW_COMMISSION = 0.0

MIN_WITHDRAW_CLIENT = 100
MIN_WITHDRAW_COURIER = 100
MIN_WITHDRAW_SHOP = 1000

# ═══ СТАРЫЕ ДАННЫЕ (Мостики для старых handlers) ═══
CATEGORIES = {
    "cafe": {"name": "🍕 Еда", "emoji": "🍕"},
    "flowers": {"name": "💐 Цветы", "emoji": "💐"},
    "pharmacy": {"name": "💊 Аптека", "emoji": "💊"},
    "gifts": {"name": "🎁 Подарки", "emoji": "🎁"},
}

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

DELIVERY_SLOTS = {
    "morning": {"name": "🌅 Утро", "hours": "08:00 – 12:00", "slots": ["08:00-09:00", "09:00-10:00", "10:00-11:00", "11:00-12:00"]},
    "day": {"name": "☀️ День", "hours": "12:00 – 18:00", "slots": ["12:00-13:00", "13:00-14:00", "14:00-15:00", "15:00-16:00", "16:00-17:00", "17:00-18:00"]},
    "evening": {"name": "🌆 Вечер", "hours": "18:00 – 22:00", "slots": ["18:00-19:00", "19:00-20:00", "20:00-21:00", "21:00-22:00"]},
}

WORKDAYS = {"mon": "Пн", "tue": "Вт", "wed": "Ср", "thu": "Чт", "fri": "Пт", "sat": "Сб", "sun": "Вс"}

# ═══ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ═══
def get_markup(price: float, category: str = "flowers") -> float:
    pct = MARKUP_BY_CATEGORY.get(category, 0.15)
    return float(int((price * pct) / 10 + 0.5) * 10)

def get_client_price(price: float, category: str = "flowers") -> float:
    return price + get_markup(price, category)
