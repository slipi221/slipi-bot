# -*- coding: utf-8 -*-
"""
SLIPI — геолокация
"""
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import config
from models import Shop, Courier, Order, DeliveryOrder
from utils import helpers


# ═══════════════════════════════════════════
#   БЛИЖАЙШИЕ МАГАЗИНЫ
# ═══════════════════════════════════════════
async def find_nearby_shops(
    session: AsyncSession,
    client_lat: float,
    client_lon: float,
    radius_km: float = None,
    limit: int = 20,
) -> list:
    if radius_km is None:
        radius_km = config.NEARBY_SHOPS_RADIUS_KM

    result = await session.execute(
        select(Shop).where(
            Shop.status == "active",
            Shop.is_paused == False,
            Shop.lat.isnot(None),
            Shop.lon.isnot(None),
        )
    )
    shops = result.scalars().all()

    out = []
    for shop in shops:
        dist = helpers.distance_km(
            client_lat, client_lon,
            float(shop.lat), float(shop.lon),
        )
        if dist <= radius_km:
            out.append({
                "shop": shop,
                "distance": dist,
                "id": shop.id,
                "name": shop.name,
                "rating": float(shop.rating or 0),
            })

    out.sort(key=lambda x: x["distance"])
    return out[:limit]


# ═══════════════════════════════════════════
#   ВСЕ АКТИВНЫЕ МАГАЗИНЫ
# ═══════════════════════════════════════════
async def get_all_shops(session: AsyncSession, limit: int = 50) -> list:
    result = await session.execute(
        select(Shop).where(
            Shop.status == "active",
            Shop.is_paused == False,
        ).order_by(Shop.rating.desc()).limit(limit)
    )
    return result.scalars().all()


# ═══════════════════════════════════════════
#   БЛИЖАЙШИЕ КУРЬЕРЫ (для пуша заказов)
# ═══════════════════════════════════════════
async def find_nearby_couriers(
    session: AsyncSession,
    shop_lat: float,
    shop_lon: float,
    radius_km: float = 5,
) -> list:
    result = await session.execute(
        select(Courier).where(
            Courier.status == "active",
            Courier.courier_state == "on",
            Courier.is_blocked == False,
            Courier.lat.isnot(None),
            Courier.lon.isnot(None),
        )
    )
    couriers = result.scalars().all()

    out = []
    for c in couriers:
        dist = helpers.distance_km(
            shop_lat, shop_lon,
            float(c.lat), float(c.lon),
        )
        if dist <= radius_km:
            out.append({"courier": c, "distance": dist})

    out.sort(key=lambda x: x["distance"])
    return out


# ═══════════════════════════════════════════
#   ОБНОВЛЕНИЕ ГЕО КУРЬЕРА
# ═══════════════════════════════════════════
async def update_courier_location(
    session: AsyncSession,
    courier_id: int,
    lat: float,
    lon: float,
):
    result = await session.execute(select(Courier).where(Courier.id == courier_id))
    courier = result.scalar_one_or_none()
    if not courier:
        return False

    courier.lat = lat
    courier.lon = lon
    courier.loc_time = datetime.now()

    # Авто-смена: если курьер не был на смене — ставим автоматически
    if courier.courier_state == "off":
        courier.courier_state = "on"
        courier.status = "active"

    await session.commit()
    return True


# ═══════════════════════════════════════════
#   РАССТОЯНИЯ ДЛЯ КУРЬЕРА
# ═══════════════════════════════════════════
async def order_distance_for_courier(
    session: AsyncSession,
    order: Order,
    courier: Courier,
) -> dict:
    shop_result = await session.execute(select(Shop).where(Shop.id == order.shop_id))
    shop = shop_result.scalar_one_or_none()

    if not shop or not shop.lat or not shop.lon:
        return {"to_shop": 999.0, "to_client": 999.0, "total": 999.0}

    to_shop = 999.0
    if courier.lat and courier.lon:
        to_shop = helpers.distance_km(
            float(courier.lat), float(courier.lon),
            float(shop.lat), float(shop.lon),
        )

    to_client = 999.0
    if order.lat and order.lon:
        to_client = helpers.distance_km(
            float(shop.lat), float(shop.lon),
            float(order.lat), float(order.lon),
        )

    return {
        "to_shop": to_shop,
        "to_client": to_client,
        "total": round(to_shop + to_client, 2),
    }


# ═══════════════════════════════════════════
#   ПРОВЕРКА ГРАФИКА РАБОТЫ МАГАЗИНА
# ═══════════════════════════════════════════
def is_shop_open(shop: Shop) -> bool:
    """
    Проверяет, работает ли магазин сейчас.
    Учитывает schedule (график по дням) или work_start/work_end.
    """
    now_dt = datetime.now()
    weekday_keys = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    today_key = weekday_keys[now_dt.weekday()]

    # Если есть schedule — используем его
    if shop.schedule:
        schedule = helpers.str_to_schedule(shop.schedule)
        today_schedule = schedule.get(today_key)
        if not today_schedule or today_schedule == "выходной":
            return False
        try:
            start_str, end_str = today_schedule.split("-")
            sh, sm = map(int, start_str.split(":"))
            eh, em = map(int, end_str.split(":"))
            start_min = sh * 60 + sm
            end_min = eh * 60 + em
            now_min = now_dt.hour * 60 + now_dt.minute
            return start_min <= now_min <= end_min
        except Exception:
            return True

    # Иначе — по общим часам
    try:
        sh, sm = map(int, (shop.work_start or "08:00").split(":"))
        eh, em = map(int, (shop.work_end or "22:00").split(":"))
        start_min = sh * 60 + sm
        end_min = eh * 60 + em
        now_min = now_dt.hour * 60 + now_dt.minute
        return start_min <= now_min <= end_min
    except Exception:
        return True


# ═══════════════════════════════════════════
#   ССЫЛКИ НА КАРТЫ
# ═══════════════════════════════════════════
def shop_map_link(shop: Shop) -> str:
    if shop.lat and shop.lon:
        return helpers.geo_link(float(shop.lat), float(shop.lon))
    return ""


def order_map_link(order: Order) -> str:
    if order.lat and order.lon:
        return helpers.geo_link(float(order.lat), float(order.lon))
    return ""


def route_to_shop_link(courier: Courier, shop: Shop) -> str:
    if courier.lat and courier.lon and shop.lat and shop.lon:
        return helpers.route_link(
            float(courier.lat), float(courier.lon),
            float(shop.lat), float(shop.lon),
        )
    return ""


def route_to_client_link(shop: Shop, order: Order) -> str:
    if shop.lat and shop.lon and order.lat and order.lon:
        return helpers.route_link(
            float(shop.lat), float(shop.lon),
            float(order.lat), float(order.lon),
        )
    return ""
