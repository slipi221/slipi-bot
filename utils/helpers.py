# -*- coding: utf-8 -*-
"""
SLIPI — вспомогательные функции
"""
from datetime import datetime, date
from math import radians, sin, cos, sqrt, atan2

import config


def now():
    return datetime.now()


def today():
    return date.today()


def format_dt(dt):
    if not dt:
        return "—"
    return dt.strftime("%d.%m.%Y %H:%M")


def format_date(d):
    if not d:
        return "—"
    return d.strftime("%d.%m.%Y")


def is_night_now():
    h = datetime.now().hour
    return h >= config.NIGHT_MODE_START or h < config.NIGHT_MODE_END


def date_label(d):
    diff = (d - date.today()).days
    if diff == 0:
        return "Сегодня"
    if diff == 1:
        return "Завтра"
    if diff == 2:
        return "Послезавтра"
    return format_date(d)


def money(value):
    if value is None:
        return "0 ₽"
    try:
        val = float(value)
    except (TypeError, ValueError):
        return "0 ₽"
    if val == int(val):
        return f"{int(val)} ₽"
    return f"{val:.2f} ₽"


def money_float(value):
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def distance_km(lat1, lon1, lat2, lon2):
    if not all([lat1, lon1, lat2, lon2]):
        return 999.0
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return round(R * c, 2)


def geo_link(lat, lon):
    return f"https://yandex.ru/maps/?pt={lon},{lat}&z=17&l=map"


def route_link(lat1, lon1, lat2, lon2):
    return f"https://yandex.ru/maps/?rtext={lat1},{lon1}~{lat2},{lon2}&rtt=auto"


def clean_phone(text):
    if not text:
        return ""
    return (text.replace(" ", "").replace("-", "")
                .replace("(", "").replace(")", "").replace("+", ""))


def is_valid_phone(text):
    clean = clean_phone(text)
    return clean.isdigit() and 10 <= len(clean) <= 15


def is_valid_card(text):
    clean = text.replace(" ", "").replace("-", "")
    return clean.isdigit() and len(clean) == 16


def format_card(text):
    if not text:
        return "—"
    clean = text.replace(" ", "").replace("-", "")
    if len(clean) != 16:
        return text
    return f"{clean[:4]} **** **** {clean[-4:]}"


def status_emoji(status):
    return config.STATUS_EMOJI.get(status, "❓")


def status_text(status):
    return config.STATUS_TEXT.get(status, status)


def category_name(key):
    return config.CATEGORIES.get(key, {}).get("name", "🌿 Другое")


def calculate_markup(shop_price):
    return config.get_markup(shop_price)


def calculate_client_price(shop_price):
    return config.get_client_price(shop_price)


def calculate_courier_fee(delivery_price=None):
    return config.get_courier_fee(delivery_price or config.DELIVERY_PRICE)


def calculate_platform_fee(delivery_price=None):
    return config.get_platform_fee(delivery_price or config.DELIVERY_PRICE)


def truncate(text, length=50):
    if not text:
        return ""
    return text if len(text) <= length else text[:length] + "…"


def plural_orders(n):
    if n % 10 == 1 and n % 100 != 11:
        return "заказ"
    if 2 <= n % 10 <= 4 and (n % 100 < 10 or n % 100 >= 20):
        return "заказа"
    return "заказов"


def referral_link(tg_id):
    bot_name = config.SERVICE_VK_TG.replace("@", "")
    return f"https://t.me/{bot_name}?start=ref_{tg_id}"


def max_boost(shop_price):
    return round(shop_price * config.BOOST_MAX_PERCENT / 100, 2)


def money_short(value):
    """1234 → 1 234 ₽"""
    v = money_float(value)
    return f"{int(v):,}".replace(",", " ") + " ₽"
