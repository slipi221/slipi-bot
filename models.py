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

    card_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    bank_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    card_holder: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sbp_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)

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
    
    # ИСПРАВЛЕНО (Баг #1): Разделенный адрес
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    street: Mapped[str | None] = mapped_column(String(255), nullable=True)
    house: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True) # Полный адрес для вывода

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
    is_on_shift: Mapped[bool] = mapped_column(Boolean, default=False) # ДОБАВЛЕНО (Баг #3)

    work_start: Mapped[str] = mapped_column(String(5), default="08:00")
    work_end: Mapped[str] = mapped_column(String(5), default="22:00")
    schedule: Mapped[str | None] = mapped_column(Text, nullable=True)

    card_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    bank_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    card_holder: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sbp_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)

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
    is_draft: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Favorite(Base):
    __tablename__ = "favorites"
    __table_args__ = (UniqueConstraint("client_id", "product_id", name="uq_fav"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ShopSubscription(Base):
    __tablename__ = "shop_subscriptions"
    __table_args__ = (UniqueConstraint("client_id", "shop_id", name="uq_sub"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"))
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

    card_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    bank_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    card_holder: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sbp_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)

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
#   ЗАКАЗЫ
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
    
    # ДОБАВЛЕНО для функции "Контроль доставки" (защита от спама)
    is_urgent_notified: Mapped[bool] = mapped_column(Boolean, default=False) 

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
    photo_id: Mapped[str | None] = mapped_column(String(255), nullable=True) # ДОБАВЛЕНО (Баг #12)


# ═══════════════════════════════════════════
#   СВОЯ ДОСТАВКА
# ═══════════════════════════════════════════
class DeliveryOrder(Base):
    __tablename__ = "delivery_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"))
    courier_id: Mapped[int | None] = mapped_column(ForeignKey("couriers.id"), nullable=True)

    from_address: Mapped[str] = mapped_column(Text)
    from_lat: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    from_lon: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)

    to_address: Mapped[str] = mapped_column(Text)
    to_lat: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    to_lon: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)

    client_name: Mapped[str] = mapped_column(String(255))
    client_phone: Mapped[str] = mapped_column(String(20))

    delivery_date: Mapped[date] = mapped_column(Date, default=date.today)
    delivery_slot: Mapped[str | None] = mapped_column(String(30), nullable=True)

    bouquet_photo_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    shop_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    need_delivery_photo: Mapped[bool] = mapped_column(Boolean, default=False)
    delivery_photo_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    distance_km: Mapped[float] = mapped_column(Numeric(6, 2), default=0)
    client_pays: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    courier_fee: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    platform_fee: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)

    status: Mapped[str] = mapped_column(String(30), default="pending")
    payment_status: Mapped[str] = mapped_column(String(20), default="pending")

    cancel_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)

    taken_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ═══════════════════════════════════════════
#   ЧАТ И УВЕДОМЛЕНИЯ
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

class Outbox(Base):
    """Очередь отложенных уведомлений (для ночных заказов)"""
    __tablename__ = "outbox"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recipient_type: Mapped[str] = mapped_column(String(20)) # client, shop, courier, admin
    recipient_id: Mapped[int] = mapped_column(Integer) 
    message_text: Mapped[str] = mapped_column(Text)
    reply_markup: Mapped[str | None] = mapped_column(Text, nullable=True) # JSON
    status: Mapped[str] = mapped_column(String(20), default="pending") # pending, sent
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


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

    method: Mapped[str] = mapped_column(String(20), default="card")
    target: Mapped[str | None] = mapped_column(String(50), nullable=True)
    card_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    bank_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    card_holder: Mapped[str | None] = mapped_column(String(255), nullable=True)

    status: Mapped[str] = mapped_column(String(20), default="pending")
    admin_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# ═══════════════════════════════════════════
#   ОТЗЫВЫ И ЖАЛОБЫ
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


class Complaint(Base):
    __tablename__ = "complaints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(Integer)
    from_tg_id: Mapped[int] = mapped_column(BigInteger)
    target_type: Mapped[str] = mapped_column(String(20))
    target_id: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text)
    photo_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    admin_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
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
#   ДОСТИЖЕНИЯ И АДМИНЫ
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


class Admin(Base):
    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    added_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    permissions: Mapped[str] = mapped_column(Text, default="{}")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ═══════════════════════════════════════════
#   ЛОГИ И ОБНОВЛЕНИЯ
# ═══════════════════════════════════════════
class Log(Base):
    __tablename__ = "logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ChangeLog(Base):
    __tablename__ = "change_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    object_type: Mapped[str] = mapped_column(String(20))
    object_id: Mapped[int] = mapped_column(Integer)
    field: Mapped[str] = mapped_column(String(50))
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_by: Mapped[str] = mapped_column(String(20))
    changed_by_id: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class BotUpdate(Base):
    __tablename__ = "bot_updates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[str] = mapped_column(String(20))
    changes: Mapped[str] = mapped_column(Text)
    sent_to_all: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
