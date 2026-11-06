# -*- coding: utf-8 -*-
"""
CityExpress — Модели базы данных (PostgreSQL, SQLAlchemy 2.0)
"""
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import (
    BigInteger, Boolean, Date, DateTime, ForeignKey,
    Integer, Numeric, String, Text, UniqueConstraint, Index, JSON
)
from sqlalchemy.orm import Mapped, mapped_column
from database import Base
from utils.helpers import now_moscow, today_moscow


# ═══════════════════════════════════════════
#   КЛИЕНТЫ
# ═══════════════════════════════════════════
class Client(Base):
    __tablename__ = "clients"
    __table_args__ = (Index("ix_clients_tg_id", "tg_id"), Index("ix_clients_vk_id", "vk_id"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tg_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    vk_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    bonus_balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    lat: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    lon: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    active_promo: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    bot_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    sbp_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Для совместимости со старым кодом
    card_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    bank_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    card_holder: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_moscow)

class ClientAddress(Base):
    __tablename__ = "client_addresses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(100))
    address: Mapped[str] = mapped_column(Text)
    lat: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    lon: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_moscow)

class ClientEvent(Base):
    __tablename__ = "client_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(255))
    event_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    event_date: Mapped[date] = mapped_column(Date)
    notified_3d: Mapped[bool] = mapped_column(Boolean, default=False)
    notified_1d: Mapped[bool] = mapped_column(Boolean, default=False)
    sent_day_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    order_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_moscow)


# ═══════════════════════════════════════════
#   МАГАЗИНЫ
# ═══════════════════════════════════════════
class Shop(Base):
    __tablename__ = "shops"
    __table_args__ = (Index("ix_shops_tg_id", "tg_id"), Index("ix_shops_vk_id", "vk_id"), Index("ix_shops_status", "status"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tg_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    vk_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    street: Mapped[str | None] = mapped_column(String(255), nullable=True)
    house: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    telegram: Mapped[str | None] = mapped_column(String(100), nullable=True)
    vk_link: Mapped[str | None] = mapped_column(String(100), nullable=True)
    owner_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lat: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    lon: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    rating: Mapped[float] = mapped_column(Numeric(3, 2), default=0)
    reviews_count: Mapped[int] = mapped_column(Integer, default=0)
    total_orders: Mapped[int] = mapped_column(Integer, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0)
    is_paused: Mapped[bool] = mapped_column(Boolean, default=False)
    is_on_shift: Mapped[bool] = mapped_column(Boolean, default=False)
    work_start: Mapped[str] = mapped_column(String(5), default="08:00")
    work_end: Mapped[str] = mapped_column(String(5), default="22:00")
    schedule: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # НОВЫЕ ПОЛЯ
    avg_prep_minutes: Mapped[int] = mapped_column(Integer, default=15)
    allow_pickup: Mapped[bool] = mapped_column(Boolean, default=True)
    pickup_fee: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("30.00"))
    max_preorder_days: Mapped[int] = mapped_column(Integer, default=3)
    cash_debt: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    cash_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Старые реквизиты (для совместимости)
    card_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    bank_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    card_holder: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sbp_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_moscow)

class ShopCategory(Base):
    __tablename__ = "shop_categories"
    __table_args__ = (UniqueConstraint("shop_id", "category", name="uq_shop_category"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"))
    category: Mapped[str] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_moscow)

class ShopChangeRequest(Base):
    __tablename__ = "shop_change_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"))
    changes: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    admin_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_moscow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# ═══════════════════════════════════════════
#   ЗОНЫ ДОСТАВКИ
# ═══════════════════════════════════════════
class DeliveryZone(Base):
    __tablename__ = "delivery_zones"
    __table_args__ = (Index("ix_zone_shop", "shop_id", "from_km"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(50))
    from_km: Mapped[float] = mapped_column(Numeric(5, 2))
    to_km: Mapped[float] = mapped_column(Numeric(5, 2))
    client_fee: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    courier_fee: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_moscow)


# ═══════════════════════════════════════════
#   ТОВАРЫ И КОРЗИНА
# ═══════════════════════════════════════════
class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"))
    category: Mapped[str] = mapped_column(String(50), default="flowers")
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    shop_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    markup: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    client_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    order_count: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_draft: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_moscow)

class Favorite(Base):
    __tablename__ = "favorites"
    __table_args__ = (UniqueConstraint("client_id", "product_id", name="uq_fav"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_moscow)

class ShopSubscription(Base):
    __tablename__ = "shop_subscriptions"
    __table_args__ = (UniqueConstraint("client_id", "shop_id", name="uq_sub"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"))
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_moscow)

class CartItem(Base):
    __tablename__ = "cart_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_moscow)


# ═══════════════════════════════════════════
#   КУРЬЕРЫ
# ═══════════════════════════════════════════
class Courier(Base):
    __tablename__ = "couriers"
    __table_args__ = (Index("ix_couriers_tg_id", "tg_id"), Index("ix_couriers_vk_id", "vk_id"), Index("ix_couriers_status", "status"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tg_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    vk_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    transport: Mapped[str | None] = mapped_column(String(50), nullable=True)
    balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    courier_state: Mapped[str] = mapped_column(String(20), default="off")
    lat: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    lon: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    loc_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rating: Mapped[float] = mapped_column(Numeric(3, 2), default=0)
    reviews_count: Mapped[int] = mapped_column(Integer, default=0)
    level: Mapped[str] = mapped_column(String(20), default="newbie")
    total_orders: Mapped[int] = mapped_column(Integer, default=0)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    bot_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    sbp_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    
    # НОВЫЕ ПОЛЯ
    has_thermal_bag: Mapped[bool] = mapped_column(Boolean, default=False)
    thermal_bag_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    
    # Старые реквизиты (для совместимости)
    card_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    bank_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    card_holder: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_moscow)

class CourierDailyStat(Base):
    __tablename__ = "courier_daily_stats"
    __table_args__ = (UniqueConstraint("courier_id", "date", name="uq_courier_date"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    courier_id: Mapped[int] = mapped_column(ForeignKey("couriers.id", ondelete="CASCADE"))
    date: Mapped[date] = mapped_column(Date, default=today_moscow)
    completed_orders: Mapped[int] = mapped_column(Integer, default=0)
    earned: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    bonus_earned: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    
    # НОВЫЕ ПОЛЯ
    on_time_count: Mapped[int] = mapped_column(Integer, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, default=0)
    violation_count: Mapped[int] = mapped_column(Integer, default=0)
    serious_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_late_minutes: Mapped[float] = mapped_column(Numeric(5, 2), default=0)


# ═══════════════════════════════════════════
#   ЗАКАЗЫ
# ═══════════════════════════════════════════
class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (Index("ix_orders_status", "status"), Index("ix_orders_client_id", "client_id"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="RESTRICT"))
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="RESTRICT"))
    courier_id: Mapped[int | None] = mapped_column(ForeignKey("couriers.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    payment_status: Mapped[str] = mapped_column(String(20), default="pending")
    address: Mapped[str] = mapped_column(Text)
    lat: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    lon: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    client_name: Mapped[str] = mapped_column(String(255))
    client_phone: Mapped[str] = mapped_column(String(20))
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivery_date: Mapped[date] = mapped_column(Date, default=today_moscow)
    delivery_slot: Mapped[str | None] = mapped_column(String(30), nullable=True)
    is_preorder: Mapped[bool] = mapped_column(Boolean, default=False)
    items_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    delivery_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    discount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    bonus_used: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    total_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    tip_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    tip_courier: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    tip_platform: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    platform_income: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    courier_fee: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    boost_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
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
    client_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    promo_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    
    # НОВЫЕ ПОЛЯ
    delivery_type: Mapped[str] = mapped_column(String(20), default="delivery") # delivery / pickup
    pickup_code: Mapped[str | None] = mapped_column(String(4), nullable=True)
    pickup_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    pickup_attempts: Mapped[int] = mapped_column(Integer, default=0)
    estimated_delivery_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    late_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    late_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    shop_response_deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    shop_auto_cancel_deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    shop_reminder_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_moscow)

class OrderItem(Base):
    __tablename__ = "order_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    title: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(50))
    shop_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    markup: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    client_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    photo_id: Mapped[str | None] = mapped_column(String(255), nullable=True)


# ═══════════════════════════════════════════
#   СВОЯ ДОСТАВКА
# ═══════════════════════════════════════════
class DeliveryOrder(Base):
    __tablename__ = "delivery_orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="RESTRICT"))
    courier_id: Mapped[int | None] = mapped_column(ForeignKey("couriers.id", ondelete="SET NULL"), nullable=True)
    from_address: Mapped[str] = mapped_column(Text)
    to_address: Mapped[str] = mapped_column(Text)
    client_name: Mapped[str] = mapped_column(String(255))
    client_phone: Mapped[str] = mapped_column(String(20))
    delivery_date: Mapped[date] = mapped_column(Date, default=today_moscow)
    delivery_slot: Mapped[str | None] = mapped_column(String(30), nullable=True)
    bouquet_photo_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    need_delivery_photo: Mapped[bool] = mapped_column(Boolean, default=False)
    delivery_photo_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    distance_km: Mapped[float] = mapped_column(Numeric(6, 2), default=0)
    client_pays: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    courier_fee: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    platform_fee: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    status: Mapped[str] = mapped_column(String(30), default="pending")
    payment_status: Mapped[str] = mapped_column(String(20), default="pending")
    
    # НОВЫЕ ПОЛЯ
    payment_method: Mapped[str] = mapped_column(String(20), default="balance") # balance / sbp / cash
    cash_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    cash_received_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_moscow)


# ═══════════════════════════════════════════
#   ОПЛАТЫ И ВЫПЛАТЫ
# ═══════════════════════════════════════════
class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(Integer)
    client_id: Mapped[int] = mapped_column(Integer)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    admin_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_moscow)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class Payout(Base):
    __tablename__ = "payouts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_type: Mapped[str] = mapped_column(String(20))
    user_id: Mapped[int] = mapped_column(Integer)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    commission: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    amount_to_pay: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    method: Mapped[str] = mapped_column(String(20), default="sbp")
    target: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sbp_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    
    # НОВЫЕ ПОЛЯ
    platform: Mapped[str] = mapped_column(String(10), default="tg")
    meeting_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    meeting_place: Mapped[str | None] = mapped_column(String(255), nullable=True)
    admin_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    user_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    admin_transferred_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reject_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    admin_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_moscow)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# ═══════════════════════════════════════════
#   ПРОЧЕЕ (СТАРЫЕ ТАБЛИЦЫ ДЛЯ СОВМЕСТИМОСТИ)
# ═══════════════════════════════════════════
class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_type: Mapped[str] = mapped_column(String(20))
    user_id: Mapped[int] = mapped_column(Integer)
    account_type: Mapped[str] = mapped_column(String(10), default="main")
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    type: Mapped[str] = mapped_column(String(30))
    order_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_moscow)

class Review(Base):
    __tablename__ = "reviews"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(Integer)
    from_user_id: Mapped[int] = mapped_column(BigInteger)
    from_platform: Mapped[str] = mapped_column(String(10), default="tg")
    target_type: Mapped[str] = mapped_column(String(20))
    target_id: Mapped[int] = mapped_column(Integer)
    rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_moscow)

class Promo(Base):
    __tablename__ = "promos"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True)
    discount_type: Mapped[str] = mapped_column(String(20))
    discount_value: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    min_order: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    max_uses: Mapped[int] = mapped_column(Integer, default=0)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_moscow)

class PromoUse(Base):
    __tablename__ = "promo_uses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    promo_id: Mapped[int] = mapped_column(ForeignKey("promos.id", ondelete="CASCADE"))
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"))
    order_id: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_moscow)

class Admin(Base):
    __tablename__ = "admins"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    permissions: Mapped[str] = mapped_column(Text, default="{}")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

class Setting(Base):
    __tablename__ = "settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(50), unique=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_moscow)

class Log(Base):
    __tablename__ = "logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_moscow)

class ActionLog(Base):
    __tablename__ = "action_logs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    platform: Mapped[str] = mapped_column(String(10))
    user_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    platform_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(String(128))
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_moscow)

class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(Integer)
    from_role: Mapped[str] = mapped_column(String(20))
    to_role: Mapped[str] = mapped_column(String(20))
    text: Mapped[str] = mapped_column(Text)
    platform: Mapped[str] = mapped_column(String(10), default="tg")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_moscow)

class Outbox(Base):
    __tablename__ = "outbox"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recipient_type: Mapped[str] = mapped_column(String(20))
    recipient_id: Mapped[int] = mapped_column(Integer)
    platform: Mapped[str] = mapped_column(String(10), default="tg")
    message_text: Mapped[str] = mapped_column(Text)
    reply_markup: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_moscow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class Achievement(Base):
    __tablename__ = "achievements"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    icon: Mapped[str | None] = mapped_column(String(10), nullable=True)
    target_type: Mapped[str] = mapped_column(String(20), default="courier")

class CourierAchievement(Base):
    __tablename__ = "courier_achievements"
    __table_args__ = (UniqueConstraint("courier_id", "achievement_id", name="uq_courier_ach"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    courier_id: Mapped[int] = mapped_column(ForeignKey("couriers.id", ondelete="CASCADE"))
    achievement_id: Mapped[int] = mapped_column(ForeignKey("achievements.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_moscow)

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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_moscow)

class BotUpdate(Base):
    __tablename__ = "bot_updates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[str] = mapped_column(String(20))
    changes: Mapped[str] = mapped_column(Text)
    sent_to_all: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_moscow)

class Complaint(Base):
    __tablename__ = "complaints"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(Integer)
    from_user_id: Mapped[int] = mapped_column(BigInteger)
    from_platform: Mapped[str] = mapped_column(String(10), default="tg")
    target_type: Mapped[str] = mapped_column(String(20))
    target_id: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    admin_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_moscow)

class DeliveryPayment(Base):
    __tablename__ = "delivery_payments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    delivery_id: Mapped[int] = mapped_column(ForeignKey("delivery_orders.id", ondelete="CASCADE"))
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    admin_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_moscow)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
