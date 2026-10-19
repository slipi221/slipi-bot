# -*- coding: utf-8 -*-
"""
Flowers Express — модели базы данных

FIX bug1: все DateTime через now_moscow (naive MSK), все Date через today_moscow.
Feature 7: Order.tip_amount, DeliveryOrder.tip_amount (чаевые).
Промокод-бонус: Client.bonus_balance, Order.bonus_used.
Feature 1/2: Outbox.platform, ChatMessage.platform, Review/Complaint.from_platform.
Fix: Client.bot_blocked (клиент заблокировал бота) — отдельно от is_blocked (бан админа).
Feature 9: Setting (key-value) — праздничная наценка и прочие админ-настройки.
"""
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import (
    BigInteger, Boolean, Date, DateTime, ForeignKey,
    Integer, Numeric, String, Text, UniqueConstraint, Index,
)
from sqlalchemy.orm import Mapped, mapped_column
from database import Base
from utils.helpers import now_moscow, today_moscow


# ═══════════════════════════════════════════
#   КЛИЕНТЫ
# ═══════════════════════════════════════════
class Client(Base):
    __tablename__ = "clients"
    __table_args__ = (Index("ix_clients_tg_id", "tg_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tg_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    vk_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    # FIX: отдельный бонусный счёт (промокоды, рефералка). Только на заказы, не выводится.
    bonus_balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    lat: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    lon: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    last_location_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    active_promo: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)  # бан админа
    # FIX: клиент сам заблокировал бота (техническое, снимается при /start)
    bot_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    card_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    bank_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    card_holder: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sbp_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_moscow)


# ═══════════════════════════════════════════
#   МАГАЗИНЫ
# ═══════════════════════════════════════════
class Shop(Base):
    __tablename__ = "shops"
    __table_args__ = (Index("ix_shops_tg_id", "tg_id"), Index("ix_shops_status", "status"))
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
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/active/rejected/blocked
    balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    rating: Mapped[float] = mapped_column(Numeric(3, 2), default=0)
    reviews_count: Mapped[int] = mapped_column(Integer, default=0)
    total_orders: Mapped[int] = mapped_column(Integer, default=0)  # FIX: +1 на момент доставки
    rejected_count: Mapped[int] = mapped_column(Integer, default=0)
    is_paused: Mapped[bool] = mapped_column(Boolean, default=False)
    is_on_shift: Mapped[bool] = mapped_column(Boolean, default=False)
    work_start: Mapped[str] = mapped_column(String(5), default="08:00")
    work_end: Mapped[str] = mapped_column(String(5), default="22:00")
    schedule: Mapped[str | None] = mapped_column(Text, nullable=True)
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


# ═══════════════════════════════════════════
#   ТОВАРЫ
# ═══════════════════════════════════════════
class Product(Base):
    __tablename__ = "products"
    __table_args__ = (Index("ix_products_shop_id", "shop_id"), Index("ix_products_category", "category"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"))
    category: Mapped[str] = mapped_column(String(50), default="bouquets")
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
    __table_args__ = (UniqueConstraint("client_id", "shop_id", name="uq_sub"), Index("ix_shop_sub_shop_id", "shop_id"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"))
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_moscow)


# ═══════════════════════════════════════════
#   КУРЬЕРЫ
# ═══════════════════════════════════════════
class Courier(Base):
    __tablename__ = "couriers"
    __table_args__ = (Index("ix_couriers_tg_id", "tg_id"), Index("ix_couriers_status", "status"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tg_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    vk_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    transport: Mapped[str | None] = mapped_column(String(50), nullable=True)
    balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/active/rejected/blocked
    courier_state: Mapped[str] = mapped_column(String(20), default="off")
    lat: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    lon: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    loc_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rating: Mapped[float] = mapped_column(Numeric(3, 2), default=0)
    reviews_count: Mapped[int] = mapped_column(Integer, default=0)
    level: Mapped[str] = mapped_column(String(20), default="newbie")
    total_orders: Mapped[int] = mapped_column(Integer, default=0)
    referred_by: Mapped[int | None] = mapped_column(ForeignKey("couriers.id", ondelete="SET NULL"), nullable=True)
    referral_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_paused_geo: Mapped[bool] = mapped_column(Boolean, default=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    bot_blocked: Mapped[bool] = mapped_column(Boolean, default=False)  # FIX: клиент заблокировал бота
    work_radius_km: Mapped[int] = mapped_column(Integer, default=5)
    card_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    bank_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    card_holder: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sbp_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_moscow)


class CourierDailyStat(Base):
    __tablename__ = "courier_daily_stats"
    __table_args__ = (UniqueConstraint("courier_id", "date", name="uq_courier_date"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    courier_id: Mapped[int] = mapped_column(ForeignKey("couriers.id", ondelete="CASCADE"))
    date: Mapped[date] = mapped_column(Date, default=today_moscow)  # FIX: МСК, не Германия
    completed_orders: Mapped[int] = mapped_column(Integer, default=0)
    earned: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    bonus_earned: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))


# ═══════════════════════════════════════════
#   КОРЗИНА
# ═══════════════════════════════════════════
class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (Index("ix_cart_client_id", "client_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_moscow)


# ═══════════════════════════════════════════
#   ЗАКАЗЫ
# ═══════════════════════════════════════════
class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        Index("ix_orders_status", "status"),
        Index("ix_orders_client_id", "client_id"),
        Index("ix_orders_shop_id", "shop_id"),
        Index("ix_orders_courier_id", "courier_id"),
    )
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
    delivery_date: Mapped[date] = mapped_column(Date, default=today_moscow)  # FIX: МСК
    delivery_slot: Mapped[str | None] = mapped_column(String(30), nullable=True)
    is_preorder: Mapped[bool] = mapped_column(Boolean, default=False)
    items_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    delivery_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    discount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    # FIX: сколько списано бонусов (из bonus_balance) — только для истории
    bonus_used: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    total_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    # FIX Feature 7: чаевые курьеру (90% курьеру, 10% платформе)
    tip_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
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
    __table_args__ = (
        Index("ix_delivery_status", "status"),
        Index("ix_delivery_shop_id", "shop_id"),
        Index("ix_delivery_courier_id", "courier_id"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="RESTRICT"))
    courier_id: Mapped[int | None] = mapped_column(ForeignKey("couriers.id", ondelete="SET NULL"), nullable=True)
    from_address: Mapped[str] = mapped_column(Text)
    from_lat: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    from_lon: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    to_address: Mapped[str] = mapped_column(Text)
    to_lat: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    to_lon: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    client_name: Mapped[str] = mapped_column(String(255))
    client_phone: Mapped[str] = mapped_column(String(20))
    delivery_date: Mapped[date] = mapped_column(Date, default=today_moscow)  # FIX: МСК
    delivery_slot: Mapped[str | None] = mapped_column(String(30), nullable=True)
    bouquet_photo_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    shop_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    need_delivery_photo: Mapped[bool] = mapped_column(Boolean, default=False)
    delivery_photo_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    distance_km: Mapped[float] = mapped_column(Numeric(6, 2), default=0)
    client_pays: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    courier_fee: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    platform_fee: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    # FIX Feature 7: чаевые
    tip_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    status: Mapped[str] = mapped_column(String(30), default="pending")
    payment_status: Mapped[str] = mapped_column(String(20), default="pending")
    cancel_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    taken_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_moscow)


# ═══════════════════════════════════════════
#   ЧАТ И УВЕДОМЛЕНИЯ
# ═══════════════════════════════════════════
class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (Index("ix_chat_order_id", "order_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(Integer)
    from_role: Mapped[str] = mapped_column(String(20))
    to_role: Mapped[str] = mapped_column(String(20))
    text: Mapped[str] = mapped_column(Text)
    # FIX Feature 2: платформа (tg/vk) + фото для моста
    platform: Mapped[str] = mapped_column(String(10), default="tg")
    photo_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_moscow)


class Outbox(Base):
    __tablename__ = "outbox"
    __table_args__ = (
        Index("ix_outbox_status", "status"),
        Index("ix_outbox_recipient", "recipient_type", "recipient_id"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recipient_type: Mapped[str] = mapped_column(String(20))   # client/shop/courier/admin
    recipient_id: Mapped[int] = mapped_column(Integer)         # внутренний ID (не TG!)
    # FIX Feature 2: целевая платформа (tg/vk)
    platform: Mapped[str] = mapped_column(String(10), default="tg")
    message_text: Mapped[str] = mapped_column(Text)
    reply_markup: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/sent/failed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_moscow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# ═══════════════════════════════════════════
#   ТРАНЗАКЦИИ И ПЛАТЕЖИ
# ═══════════════════════════════════════════
class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (Index("ix_trans_user", "user_type", "user_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_type: Mapped[str] = mapped_column(String(20))
    user_id: Mapped[int] = mapped_column(Integer)
    # FIX: "main" (реальные деньги) или "bonus" (бонусный счёт)
    account_type: Mapped[str] = mapped_column(String(10), default="main")
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    type: Mapped[str] = mapped_column(String(30))
    order_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_moscow)


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (Index("ix_payment_order_id", "order_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(Integer)
    client_id: Mapped[int] = mapped_column(Integer)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    card_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    admin_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_moscow)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DeliveryPayment(Base):
    __tablename__ = "delivery_payments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    delivery_id: Mapped[int] = mapped_column(ForeignKey("delivery_orders.id", ondelete="CASCADE"))
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"))
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
    method: Mapped[str] = mapped_column(String(20), default="card")
    target: Mapped[str | None] = mapped_column(String(50), nullable=True)
    card_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    bank_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    card_holder: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    admin_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_moscow)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# ═══════════════════════════════════════════
#   ОТЗЫВЫ, ЖАЛОБЫ, ПРОМОКОДЫ
# ═══════════════════════════════════════════
class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (Index("ix_review_target", "target_type", "target_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(Integer)
    from_user_id: Mapped[int] = mapped_column(BigInteger)  # FIX: было from_tg_id
    from_platform: Mapped[str] = mapped_column(String(10), default="tg")  # FIX
    target_type: Mapped[str] = mapped_column(String(20))
    target_id: Mapped[int] = mapped_column(Integer)
    rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_moscow)


class Complaint(Base):
    __tablename__ = "complaints"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(Integer)
    from_user_id: Mapped[int] = mapped_column(BigInteger)  # FIX: было from_tg_id
    from_platform: Mapped[str] = mapped_column(String(10), default="tg")  # FIX
    target_type: Mapped[str] = mapped_column(String(20))
    target_id: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text)
    photo_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/approved/rejected
    admin_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_moscow)


class Promo(Base):
    __tablename__ = "promos"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True)
    discount_type: Mapped[str] = mapped_column(String(20))  # "fixed" (бонус ₽) / "percent" (скидка %)
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


# ═══════════════════════════════════════════
#   ДОСТИЖЕНИЯ, АДМИНЫ, ЛОГИ
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
    courier_id: Mapped[int] = mapped_column(ForeignKey("couriers.id", ondelete="CASCADE"))
    achievement_id: Mapped[int] = mapped_column(ForeignKey("achievements.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_moscow)


class Admin(Base):
    __tablename__ = "admins"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    added_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    permissions: Mapped[str] = mapped_column(Text, default="{}")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_moscow)


class Log(Base):
    __tablename__ = "logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_moscow)


class ChangeLog(Base):
    __tablename__ = "change_logs"
    __table_args__ = (Index("ix_changelog_object", "object_type", "object_id"),)
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


# ═══════════════════════════════════════════
#   НАСТРОЙКИ (key-value) — Feature 9
# ═══════════════════════════════════════════
class Setting(Base):
    """
    Универсальные настройки: праздничная наценка, мин. вывод, бонусы и т.д.
    Админ меняет через UI → значение сохраняется сюда. При старте — загружается.
    """
    __tablename__ = "settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(50), unique=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_moscow)
