# -*- coding: utf-8 -*-
"""
SLIPI — вспомогательные функции
"""
import json
import html
from datetime import datetime, date
from math import radians, sin, cos, sqrt, atan2

import config

# ═══════════════════════════════════════════
#   БЕЗОПАСНОСТЬ (ЭКРАНИРОВАНИЕ HTML)
# ═══════════════════════════════════════════
def escape(text) -> str:
    """Экранирует HTML-символы (<, >, &), чтобы Telegram не выдавал ошибку."""
    return html.escape(str(text)) if text else ""

# ═══════════════════════════════════════════
#   ВРЕМЯ
# ═══════════════════════════════════════════
def now() -> datetime:
    return datetime.now()

def today() -> date:
    return date.today()

def format_dt(dt) -> str:
    if not dt: return "—"
    return dt.strftime("%d.%m.%Y %H:%M")

def format_date(d) -> str:
    if not d: return "—"
    return d.strftime("%d.%m.%Y")

def format_time(dt) -> str:
    if not dt: return "—"
    return dt.strftime("%H:%M")

def is_night_now() -> bool:
    h = datetime.now().hour
    return h >= config.NIGHT_MODE_START or h < config.NIGHT_MODE_END

def date_label(d: date) -> str:
    diff = (d - date.today()).days
    if diff == 0: return "Сегодня"
    if diff == 1: return "Завтра"
    if diff == 2: return "Послезавтра"
    return format_date(d)

def is_slot_past(slot: str) -> bool:
    try:
        end_str = slot.split("-")[1]
        h, m = map(int, end_str.split(":"))
        now_dt = datetime.now()
        slot_end = now_dt.replace(hour=h, minute=m, second=0, microsecond=0)
        if h == 0 and now_dt.hour > 12:
            slot_end = slot_end.replace(day=now_dt.day + 1)
        return slot_end < now_dt
    except Exception:
        return False

# ═══════════════════════════════════════════
#   ДЕНЬГИ
# ═══════════════════════════════════════════
def money(value) -> str:
    if value is None: return "0 ₽"
    try: val = float(value)
    except (TypeError, ValueError): return "0 ₽"
    if val == int(val): return f"{int(val)} ₽"
    return f"{val:.2f} ₽"

def money_float(value) -> float:
    if value is None: return 0.0
    try: return float(value)
    except (TypeError, ValueError): return 0.0

def money_short(value) -> str:
    v = money_float(value)
    return f"{int(v):,}".replace(",", " ") + " ₽"

# ═══════════════════════════════════════════
#   ГЕО
# ═══════════════════════════════════════════
def distance_km(lat1, lon1, lat2, lon2) -> float:
    if not all([lat1, lon1, lat2, lon2]): return 999.0
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return round(R * c, 2)

def geo_link(lat, lon) -> str:
    return f"https://yandex.ru/maps/?pt={lon},{lat}&z=17&l=map"

def route_link(points: list[tuple[float, float]]) -> str:
    """
    Строит мультимаршрут.
    Принимает список кортежей [(lat1, lon1), (lat2, lon2), ...]
    """
    if not points or len(points) < 2:
        return ""
    
    # Формат: rtext=lat1,lon1~lat2,lon2~lat3,lon3
    coords = "~".join([f"{lat},{lon}" for lat, lon in points])
    return f"https://yandex.ru/maps/?rtext={coords}&rtt=auto"

# ═══════════════════════════════════════════
#   ВАЛИДАЦИЯ
# ═══════════════════════════════════════════
def clean_phone(text) -> str:
    if not text: return ""
    return (text.replace(" ", "").replace("-", "").replace("(", "").replace(")", "").replace("+", ""))

def is_valid_phone(text) -> bool:
    clean = clean_phone(text)
    return clean.isdigit() and 10 <= len(clean) <= 15

def is_valid_card(text) -> bool:
    clean = text.replace(" ", "").replace("-", "")
    return clean.isdigit() and len(clean) == 16

def format_card(text) -> str:
    if not text: return "—"
    clean = text.replace(" ", "").replace("-", "")
    if len(clean) != 16: return text
    return f"{clean[:4]} **** **** {clean[-4:]}"

def is_valid_time(text) -> bool:
    try:
        h, m = text.split(":")
        h, m = int(h), int(m)
        return 0 <= h < 24 and 0 <= m < 60
    except Exception:
        return False

# ═══════════════════════════════════════════
#   СТАТУСЫ И ТЕКСТЫ
# ═══════════════════════════════════════════
def status_emoji(status) -> str:
    return config.STATUS_EMOJI.get(status, "❓")

def status_text(status) -> str:
    return config.STATUS_TEXT.get(status, status)

def category_name(key) -> str:
    return config.CATEGORIES.get(key, {}).get("name", "🌿 Другое")

def weekday_name(key) -> str:
    return config.WEEKDAYS.get(key, key)

def truncate(text, length=50) -> str:
    if not text: return ""
    return text if len(text) <= length else text[:length] + "…"

def plural_orders(n) -> str:
    if n % 10 == 1 and n % 100 != 11: return "заказ"
    if 2 <= n % 10 <= 4 and (n % 100 < 10 or n % 100 >= 20): return "заказа"
    return "заказов"

def referral_link(tg_id) -> str:
    bot_name = config.SERVICE_VK_TG.replace("@", "")
    return f"https://t.me/{bot_name}?start=ref_{tg_id}"

# ═══════════════════════════════════════════
#   РАСЧЁТЫ
# ═══════════════════════════════════════════
def calculate_markup(shop_price):
    return config.get_markup(shop_price)

def calculate_client_price(shop_price):
    return config.get_client_price(shop_price)

def calculate_delivery_zone(distance_km):
    return config.get_delivery_zone(distance_km)

def calculate_eta(distance_km: float, transport: str = "Авто") -> int:
    speed_map = {"Авто": 40, "Мото": 45, "Вело": 15, "Пешком": 5}
    speed = speed_map.get(transport, 30)
    minutes = int((distance_km / speed) * 60) + 5
    return max(minutes, 5)

# ═══════════════════════════════════════════
#   ГРАФИК РАБОТЫ
# ═══════════════════════════════════════════
def schedule_to_str(schedule: dict) -> str:
    if not schedule: return "{}"
    return json.dumps(schedule, ensure_ascii=False)

def str_to_schedule(text: str) -> dict:
    if not text: return {}
    try: return json.loads(text)
    except Exception: return {}

def format_schedule(schedule: dict) -> str:
    if not schedule: return "—"
    lines = []
    for key, day in config.WEEKDAYS.items():
        time_str = schedule.get(key, "выходной")
        lines.append(f"{day}: {time_str}")
    return "\n".join(lines)

def default_schedule() -> dict:
    return {k: "08:00-22:00" for k in config.WEEKDAYS.keys()}

# ═══════════════════════════════════════════
#   ПРАВА АДМИНОВ
# ═══════════════════════════════════════════
def parse_permissions(text) -> dict:
    if not text: return {}
    try: return json.loads(text)
    except Exception: return {}

def permissions_to_str(perms: dict) -> str:
    return json.dumps(perms, ensure_ascii=False)

def is_main_admin(tg_id: int) -> bool:
    return tg_id == config.ADMIN_ID

def has_permission(perms: dict, key: str) -> bool:
    return perms.get(key, False)
