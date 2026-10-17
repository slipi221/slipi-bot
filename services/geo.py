# -*- coding: utf-8 -*-
"""
Flowers Express — геолокация
"""
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import config
from models import Shop, Courier, Order
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
#   ВСЕ КУРЬЕРЫ НА СМЕНЕ (БЕЗ ФИЛЬТРА ПО РАССТОЯНИЮ)
# ═══════════════════════════════════════════
async def get_couriers_on_shift(session: AsyncSession) -> list:
    """
    Возвращает ВСЕХ курьеров на смене.
    Фильтр по расстоянию убран (пункт 279).
    """
    result = await session.execute(
        select(Courier).where(
            Courier.status == "active",
            Courier.courier_state == "on",
            Courier.is_blocked == False,
            Courier.tg_id.isnot(None),
        )
    )
    return result.scalars().all()

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
    courier.loc_time = helpers.now_moscow()

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
    Учитывает ночные смены (если смена переходит через полночь).
    """
    now_dt = helpers.now_moscow()
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
            
            # Если смена переходит через полночь (например, 22:00-06:00)
            if start_min > end_min:
                return now_min >= start_min or now_min <= end_min
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
        
        if start_min > end_min:
            return now_min >= start_min or now_min <= end_min
        return start_min <= now_min <= end_min
    except Exception:
        return True
