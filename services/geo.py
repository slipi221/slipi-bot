# -*- coding: utf-8 -*-
"""
SLIPI — геолокация, поиск ближайших магазинов и курьеров
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import config
from models import Shop, Courier, Order
from utils import helpers


# ═══════════════════════════════════════════
#   ПОИСК БЛИЖАЙШИХ МАГАЗИНОВ
# ═══════════════════════════════════════════
async def find_nearby_shops(
    session: AsyncSession,
    client_lat: float,
    client_lon: float,
    radius_km: float = None,
    limit: int = 20,
) -> list:
    """
    Возвращает список магазинов, отсортированных по расстоянию.
    """
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

    shops_with_dist = []
    for shop in shops:
        dist = helpers.distance_km(
            client_lat, client_lon,
            float(shop.lat), float(shop.lon),
        )
        if dist <= radius_km:
            shops_with_dist.append({
                "shop": shop,
                "distance": dist,
                "id": shop.id,
                "name": shop.name,
                "rating": float(shop.rating or 0),
            })

    shops_with_dist.sort(key=lambda x: x["distance"])
    return shops_with_dist[:limit]


# ═══════════════════════════════════════════
#   ВСЕ АКТИВНЫЕ МАГАЗИНЫ
# ═══════════════════════════════════════════
async def get_all_shops(session: AsyncSession, limit: int = 50) -> list:
    """Все активные магазины (без сортировки по расстоянию)."""
    result = await session.execute(
        select(Shop).where(
            Shop.status == "active",
            Shop.is_paused == False,
        ).order_by(Shop.rating.desc()).limit(limit)
    )
    return result.scalars().all()


# ═══════════════════════════════════════════
#   БЛИЖАЙШИЕ КУРЬЕРЫ (для рассылки заказов)
# ═══════════════════════════════════════════
async def find_nearby_couriers(
    session: AsyncSession,
    shop_lat: float,
    shop_lon: float,
    radius_km: float = 5,
) -> list:
    """
    Возвращает список курьеров, готовых принять заказ
    (на смене, не в перерыве, в радиусе).
    """
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

    near = []
    for c in couriers:
        dist = helpers.distance_km(
            shop_lat, shop_lon,
            float(c.lat), float(c.lon),
        )
        if dist <= radius_km:
            near.append({"courier": c, "distance": dist})

    near.sort(key=lambda x: x["distance"])
    return near


# ═══════════════════════════════════════════
#   ОБНОВЛЕНИЕ ГЕО КУРЬЕРА
# ═══════════════════════════════════════════
async def update_courier_location(
    session: AsyncSession,
    courier_id: int,
    lat: float,
    lon: float,
):
    """Сохраняет текущую геолокацию курьера."""
    from datetime import datetime
    result = await session.execute(select(Courier).where(Courier.id == courier_id))
    courier = result.scalar_one_or_none()
    if not courier:
        return False

    courier.lat = lat
    courier.lon = lon
    courier.loc_time = datetime.now()
    await session.commit()
    return True


# ═══════════════════════════════════════════
#   РАССТОЯНИЕ ОТ КУРЬЕРА ДО ЗАКАЗА
# ═══════════════════════════════════════════
async def order_distance_for_courier(
    session: AsyncSession,
    order: Order,
    courier: Courier,
) -> dict:
    """
    Считает расстояния для конкретного заказа:
    - от курьера до магазина
    - от магазина до клиента
    - общий путь
    """
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
