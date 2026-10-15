# -*- coding: utf-8 -*-
"""
SLIPI — модели базы данных
"""
from datetime import datetime, date
from decimal import Decimal

from sqlalchemy import (
    BigInteger, Boolean, Date, DateTime, ForeignKey,
    Integer, Numeric, String, Text, UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


# ═══════════════════════════════════════════
#   КЛИЕНТЫ
# ═══════════════════════════════════════════
class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tg_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    vk_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    lat: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    lon: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    last_location_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    active_promo: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ClientAddress(Base):
    __tablename__ = "client_addresses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    title: Mapped[str] = mapped_column(String(100))
    address: Mapped[str] = mapped_column(Text)
    lat: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    lon: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ClientEvent(Base):
    __tablename__ = "client_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    title: Mapped[str] = mapped_column(String(255))
    event_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    event_date: Mapped[date] = mapped_column(Date)
    notified_3d: Mapped[bool] = mapped_column(Boolean, default=False)
    notified_1d: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ═══════════════════════════════════════════
#   МАГАЗИНЫ
# ═══════════════════════════════════════════
class Shop(Base):
    __tablename__ = "shops"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tg_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    vk_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    telegram: Mapped[str | None] = mapped_column(String(100), nullable=True)
    vk_link: Mapped[str | None] = mapped_column(String(100), nullable=True)
    owner_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lat: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    lon: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    rating: Mapped[float] = mapped_column(Numeric(3, 2), default=0)
    reviews_count: Mapped[int] = mapped_column(Integer, default=0)
    total_orders: Mapped[int] = mapped_column(Integer, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0)
    is_paused: Mapped[bool] = mapped_column(Boolean, default=False)
    work_start: Mapped[str] = mapped_column(String(5), default="08:00")
    work_end: Mapped[str] = mapped_column(String(5), default="22:00")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ShopCategory(Base):
    __tablename__ = "shop_categories"
    __table_args__ = (UniqueConstraint("shop_id", "category", name="uq_shop_category"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"))
    category: Mapped[str] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ═══════════════════════════════════════════
#   ТОВАРЫ
# ═══════════════════════════════════════════
class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"))
    category: Mapped[str] = mapped_column(String(50), default="bouquets")
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    shop_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    markup: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    client_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    order_count: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Favorite(Base):
    __tablename__ = "favorites"
    __table_args__ = (UniqueConstraint("client_id", "product_id", name="uq_fav"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ═══════════════════════════════════════════
#   КУРЬЕРЫ
# ═══════════════════════════════════════════
class Courier(Base):
    __tablename__ = "couriers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tg_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    vk_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    transport: Mapped[str | None] = mapped_column(String(50), nullable=True)
    card_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    courier_state: Mapped[str] = mapped_column(String(20), default="off")
    lat: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    lon: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    loc_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rating: Mapped[float] = mapped_column(Numeric(3, 2), default=0)
    reviews_count: Mapped[int] = mapped_column(Integer, default=0)
    level: Mapped[str] = mapped_column(String(20), default="newbie")
    total_orders: Mapped[int] = mapped_column(Integer, default=0)
    referred_by: Mapped[int | None] = mapped_column(ForeignKey("couriers.id"), nullable=True)
    referral_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_paused_geo: Mapped[bool] = mapped_column(Boolean, default=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    work_radius_km: Mapped[int] = mapped_column(Integer, default=5)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CourierDailyStat(Base):
    __tablename__ = "courier_daily_stats"
    __table_args__ = (UniqueConstraint("courier_id", "date", name="uq_courier_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    courier_id: Mapped[int] = mapped_column(ForeignKey("couriers.id"))
    date: Mapped[date] = mapped_column(Date, default=date.today)
    completed_orders: Mapped[int] = mapped_column(Integer, default=0)
    earned: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    bonus_earned: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)


# ═══════════════════════════════════════════
#   КОРЗИНА
# ═══════════════════════════════════════════
class CartItem(Base):
    __tablename__ = "cart_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ═══════════════════════════════════════════
#   ЗАКАЗЫ (от клиента)
# ═══════════════════════════════════════════
class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"))
    courier_id: Mapped[int | None] = mapped_column(ForeignKey("couriers.id"), nullable=True)

    status: Mapped[str] = mapped_column(String(30), default="pending")
    payment_status: Mapped[str] = mapped_column(String(20), default="pending")

    address: Mapped[str] = mapped_column(Text)
    lat: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    lon: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    client_name: Mapped[str] = mapped_column(String(255))
    client_phone: Mapped[str] = mapped_column(String(20))
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    delivery_date: Mapped[date] = mapped_column(Date, default=date.today)
    delivery_slot: Mapped[str | None] = mapped_column(String(30), nullable=True)
    is_preorder: Mapped[bool] = mapped_column(Boolean, default=False)

    items_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    delivery_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    discount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    total_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    platform_income: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)

    courier_fee: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    boost_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)

    need_delivery_photo: Mapped[bool] = mapped_column(Boolean, default=True)
    delivery_photo_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    photo_requested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    cancel_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    cancelled_by: Mapped[str | None] = mapped_column(String(20), nullable=True)

    wait_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    taken_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    track_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    promo_code: Mapped[str | None] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    title: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(50))
    shop_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    markup: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    client_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2))


# ═══════════════════════════════════════════
#   СВОЯ ДОСТАВКА (магазин создаёт сам)
# ═══════════════════════════════════════════
class DeliveryOrder(Base):
    """Заявка на доставку, которую создаёт магазин."""
    __tablename__ = "delivery_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"))
    courier_id: Mapped[int | None] = mapped_column(ForeignKey("couriers.id"), nullable=True)

    # Откуда (авто из магазина)
    from_address: Mapped[str] = mapped_column(Text)
    from_lat: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    from_lon: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)

    # Куда
    to_address: Mapped[str] = mapped_column(Text)
    to_lat: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    to_lon: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)

    client_name: Mapped[str] = mapped_column(String(255))
    client_phone: Mapped[str] = mapped_column(String(20))

    delivery_date: Mapped[date] = mapped_column(Date, default=date.today)
    delivery_slot: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # Фото букета
    bouquet_photo_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Комментарии
    shop_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Фото вручения
    need_delivery_photo: Mapped[bool] = mapped_column(Boolean, default=False)
    delivery_photo_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Деньги
    distance_km: Mapped[float] = mapped_column(Numeric(6, 2), default=0)
    client_pays: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    courier_fee: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    platform_fee: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)

    # Статус
    status: Mapped[str] = mapped_column(String(30), default="pending")
    payment_status: Mapped[str] = mapped_column(String(20), default="pending")

    cancel_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)

    taken_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ═══════════════════════════════════════════
#   ЧАТ
# ═══════════════════════════════════════════
class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(Integer)
    from_role: Mapped[str] = mapped_column(String(20))
    to_role: Mapped[str] = mapped_column(String(20))
    text: Mapped[str] = mapped_column(Text)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ═══════════════════════════════════════════
#   ТРАНЗАКЦИИ
# ═══════════════════════════════════════════
class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_type: Mapped[str] = mapped_column(String(20))
    user_id: Mapped[int] = mapped_column(Integer)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    type: Mapped[str] = mapped_column(String(30))
    order_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(Integer)
    client_id: Mapped[int] = mapped_column(Integer)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    card_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    admin_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DeliveryPayment(Base):
    """Платежи за «Свою доставку»."""
    __tablename__ = "delivery_payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    delivery_id: Mapped[int] = mapped_column(ForeignKey("delivery_orders.id"))
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    admin_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Payout(Base):
    __tablename__ = "payouts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_type: Mapped[str] = mapped_column(String(20))
    user_id: Mapped[int] = mapped_column(Integer)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    commission: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    amount_to_pay: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    card_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    holder_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    admin_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# ═══════════════════════════════════════════
#   ОТЗЫВЫ
# ═══════════════════════════════════════════
class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(Integer)
    from_tg_id: Mapped[int] = mapped_column(BigInteger)
    target_type: Mapped[str] = mapped_column(String(20))
    target_id: Mapped[int] = mapped_column(Integer)
    rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ═══════════════════════════════════════════
#   ПРОМОКОДЫ
# ═══════════════════════════════════════════
class Promo(Base):
    __tablename__ = "promos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True)
    discount_type: Mapped[str] = mapped_column(String(20))
    discount_value: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    min_order: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    max_uses: Mapped[int] = mapped_column(Integer, default=0)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PromoUse(Base):
    __tablename__ = "promo_uses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    promo_id: Mapped[int] = mapped_column(ForeignKey("promos.id"))
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    order_id: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ═══════════════════════════════════════════
#   ДОСТИЖЕНИЯ
# ═══════════════════════════════════════════
class Achievement(Base):
    __tablename__ = "achievements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    icon: Mapped[str | None] = mapped_column(String(10), nullable=True)


class CourierAchievement(Base):
    __tablename__ = "courier_achievements"
    __table_args__ = (UniqueConstraint("courier_id", "achievement_id", name="uq_courier_ach"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    courier_id: Mapped[int] = mapped_column(ForeignKey("couriers.id"))
    achievement_id: Mapped[int] = mapped_column(ForeignKey("achievements.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ═══════════════════════════════════════════
#   ЛОГИ
# ═══════════════════════════════════════════
class Log(Base):
    __tablename__ = "logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
