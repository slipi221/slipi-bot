# -*- coding: utf-8 -*-
"""
SLIPI — геолокация
"""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import config
from models import Shop, Courier, Order
from utils import helpers


async def find_nearby_shops(
    session: AsyncSession,
    client_lat: float,
    client_lon: float,
    radius_km: float = None,
    limit: int = 20,
) -> list:
    """Ближайшие магазины по гео."""
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


async def get_all_shops(session: AsyncSession, limit: int = 50) -> list:
    """Все активные магазины."""
    result = await session.execute(
        select(Shop).where(
            Shop.status == "active",
            Shop.is_paused == False,
        ).order_by(Shop.rating.desc()).limit(limit)
    )
    return result.scalars().all()


async def find_nearby_couriers(
    session: AsyncSession,
    shop_lat: float,
    shop_lon: float,
    radius_km: float = 5,
) -> list:
    """Курьеры на смене рядом с магазином."""
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


async def update_courier_location(
    session: AsyncSession,
    courier_id: int,
    lat: float,
    lon: float,
):
    """Сохраняет гео курьера."""
    result = await session.execute(select(Courier).where(Courier.id == courier_id))
    courier = result.scalar_one_or_none()
    if not courier:
        return False

    courier.lat = lat
    courier.lon = lon
    courier.loc_time = datetime.now()
    await session.commit()
    return True


async def order_distance_for_courier(
    session: AsyncSession,
    order: Order,
    courier: Courier,
) -> dict:
    """Расстояния: курьер → магазин, магазин → клиент."""
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
