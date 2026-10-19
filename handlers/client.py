# -*- coding: utf-8 -*-
"""
Flowers Express — бот клиента

FIX bug3: добавлен from services import notify.
FIX bug6: требование гео перед оформлением (cart_checkout).
FIX bug15: track_order передаёт payment_status.
FIX: Review.from_tg_id → from_user_id (переименовано в models.py).
FIX: create_order_from_cart — убран distance_km.
FIX: rating_kb — добавлены обработчики rate_shop_*, rate_courier_*, rate_skip_*, rate_start_*.
FIX: tip_* — добавлены обработчики чаевых (Feature 7).
FIX: wd_sbp — отдельный флоу (было сломано).
FIX: got_location — не перехватывает OrderFSM.
FIX: promo_apply — для fixed начисляет на bonus_balance.
FIX: show_order_confirm — реальная дистанция.
FIX: order_back — обработчик.
FIX Feature 4: order_date с closed_dates.
"""
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, BufferedInputFile, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import select, delete

import config
import keyboards as kb
from states import OrderFSM, ClientFSM
from database import async_session
from models import (
    Client, Shop, Product, CartItem, Favorite, Order, OrderItem,
    ClientAddress, ClientEvent, Courier, Review, ShopSubscription,
    Promo, PromoUse,
)
from services import orders as orders_service
from services import geo as geo_service
from services import payments as payments_service
from services import notify  # FIX bug3
from services import bonuses as bonuses_service
from utils import helpers
from bots import bot_admin, bot_shop, bot_courier

log = logging.getLogger(__name__)
router = Router(name="client")


async def get_or_create_client(session, tg_id: int):
    result = await session.execute(select(Client).where(Client.tg_id == tg_id))
    client = result.scalar_one_or_none()
    if not client:
        client = Client(tg_id=tg_id)
        session.add(client)
        await session.commit()
        await session.refresh(client)
    return client


# ═══════════════════════════════════════════
#   /start И ГЛАВНОЕ МЕНЮ
# ═══════════════════════════════════════════
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        client = await get_or_create_client(session, message.from_user.id)
        # FIX: снимаем bot_blocked при /start
        if client.bot_blocked:
            client.bot_blocked = False
            await session.commit()

    text = (
        f"🌸 <b>Добро пожаловать в {config.SERVICE_NAME}!</b>\n"
        f"Доставка цветов и подарков по городу {config.CITY}.\n"
        f"🕒 Работаем: {config.WORK_HOURS}\n\n"
        "Выберите действие:"
    )
    await message.answer(text, reply_markup=kb.client_main())


@router.callback_query(F.data == "client_main")
async def back_to_main(call: CallbackQuery, state: FSMContext):
    await state.clear()
    text = f"🌸 <b>{config.SERVICE_NAME}</b>\nВыберите действие:"
    try:
        await call.message.edit_text(text, reply_markup=kb.client_main())
    except TelegramBadRequest:
        await call.message.delete()
        await call.message.answer(text, reply_markup=kb.client_main())
    await call.answer()


@router.callback_query(F.data == "client_about")
async def about(call: CallbackQuery):
    text = (
        f"ℹ️ <b>{config.SERVICE_NAME}</b>\nДоставка цветов и подарков\n\n"
        f"🏙 Город: {config.CITY}\n🕒 Работаем: {config.WORK_HOURS}\n📞 Поддержка: {config.SUPPORT_TG}"
    )
    await call.message.edit_text(text, reply_markup=kb.client_back())
    await call.answer()


@router.callback_query(F.data == "client_support")
async def support(call: CallbackQuery):
    await call.message.edit_text(
        f"🆘 <b>Поддержка</b>\n\nНапишите ваш вопрос — мы ответим.\nИли свяжитесь: {config.SUPPORT_TG}",
        reply_markup=kb.client_back(),
    )
    await call.answer()


@router.callback_query(F.data == "noop")
async def noop(call: CallbackQuery):
    await call.answer()


# ═══════════════════════════════════════════
#   КАТАЛОГ И ГЕОЛОКАЦИЯ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "client_catalog")
async def catalog(call: CallbackQuery):
    try:
        await call.message.delete()
    except TelegramBadRequest:
        pass

    await call.message.answer(
        "📍 Нажмите на кнопку внизу экрана, чтобы показать ближайшие магазины.\n"
        "Или выберите «Показать все магазины».",
        reply_markup=kb.client_geo(),
    )
    await call.message.answer("⬇️ Нажмите кнопку ниже:", reply_markup=kb.get_geo_kb())
    await call.answer()


@router.message(F.location)
async def got_location(message: Message, state: FSMContext):
    """FIX: не перехватывает OrderFSM — только сохраняет гео и предупреждает."""
    async with async_session() as session:
        client = await get_or_create_client(session, message.from_user.id)
        client.lat = message.location.latitude
        client.lon = message.location.longitude
        await session.commit()

    # Если пользователь в процессе оформления заказа — не мешаем, только подсказываем
    current = await state.get_state()
    if current and current.startswith("OrderFSM"):
        await message.answer("✅ Гео сохранено! Продолжайте оформление заказа.", reply_markup=kb.order_cancel())
        return

    await message.answer("✅ Геопозиция получена! 🔍 Ищем магазины...", reply_markup=ReplyKeyboardRemove())

    async with async_session() as session:
        shops = await geo_service.find_nearby_shops(
            session, message.location.latitude, message.location.longitude,
        )

    if not shops:
        await message.answer("😔 Рядом нет магазинов. Попробуйте «Показать все».", reply_markup=kb.client_geo())
        return

    items = [
        {"id": s["id"], "name": s["name"], "rating": s["rating"], "is_open": s.get("is_open", True)}
        for s in shops
    ]
    has_next = len(items) > 5
    await message.answer(
        f"📍 <b>Ближайшие к вам ({len(items)})</b>",
        reply_markup=kb.client_shops(items[:5], 0, has_next=has_next),
    )


@router.callback_query(F.data == "client_all_shops")
async def all_shops(call: CallbackQuery):
    async with async_session() as session:
        shops = await geo_service.get_all_shops(session, limit=20)
        items = [
            {"id": s.id, "name": s.name, "rating": float(s.rating or 0), "is_open": geo_service.is_shop_open(s)}
            for s in shops
        ]
    if not items:
        await call.message.edit_text("😔 Пока нет активных магазинов.", reply_markup=kb.client_back())
        await call.answer()
        return
    has_next = len(items) > 5
    await call.message.edit_text(
        f"🏪 <b>Магазины ({len(items)})</b>\nВыберите:",
        reply_markup=kb.client_shops(items[:5], 0, has_next=has_next),
    )
    await call.answer()


@router.callback_query(F.data.startswith("shops_page_"))
async def shops_page(call: CallbackQuery):
    page = int(call.data.split("_")[-1])
    async with async_session() as session:
        shops = await geo_service.get_all_shops(session, limit=100)
        items = [
            {"id": s.id, "name": s.name, "rating": float(s.rating or 0), "is_open": geo_service.is_shop_open(s)}
            for s in shops
        ]
    page_items = items[page * 5:(page * 5) + 5]
    has_next = (page + 1) * 5 < len(items)
    await call.message.edit_text(
        f"🏪 <b>Магазины (стр. {page + 1})</b>",
        reply_markup=kb.client_shops(page_items, page, has_next=has_next),
    )
    await call.answer()


# ═══════════════════════════════════════════
#   КАРТОЧКА МАГАЗИНА
# ═══════════════════════════════════════════
@router.callback_query(
    F.data.startswith("shop_")
    & ~F.data.startswith("shop_products_")
    & ~F.data.startswith("shop_hits_")
    & ~F.data.startswith("shop_reviews_")
    & ~F.data.startswith("shop_call_")
    & ~F.data.startswith("shop_subscribe_")
)
async def shop_card(call: CallbackQuery):
    try:
        shop_id = int(call.data.split("_")[-1])
    except (IndexError, ValueError):
        return

    async with async_session() as session:
        result = await session.execute(select(Shop).where(Shop.id == shop_id))
        shop = result.scalar_one_or_none()
        if not shop:
            return

        client = await get_or_create_client(session, call.from_user.id)
        sub_result = await session.execute(
            select(ShopSubscription).where(
                ShopSubscription.client_id == client.id,
                ShopSubscription.shop_id == shop_id,
            )
        )
        is_subscribed = sub_result.scalar_one_or_none() is not None

    is_open = geo_service.is_shop_open(shop)
    text = (
        f"🏪 <b>{helpers.escape(shop.name)}</b>\n"
        f"⭐ {float(shop.rating or 0):.1f} ({shop.reviews_count})\n"
        f"📍 {helpers.escape(shop.address or '—')}\n"
        f"🕒 {shop.work_start} – {shop.work_end}"
    )

    try:
        await call.message.edit_text(text, reply_markup=kb.shop_card(shop_id, is_subscribed, shop.phone, is_open))
    except TelegramBadRequest:
        await call.message.edit_text(text, reply_markup=kb.shop_card(shop_id, is_subscribed, None, is_open))
    await call.answer()


@router.callback_query(F.data.startswith("shop_call_"))
async def shop_call(call: CallbackQuery):
    shop_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        r = await session.execute(select(Shop).where(Shop.id == shop_id))
        shop = r.scalar_one_or_none()
    if shop and shop.phone:
        await call.message.answer(f"📞 Телефон магазина: <code>{shop.phone}</code>")
    else:
        await call.message.answer("📞 Магазин не указал телефон.")
    await call.answer()


@router.callback_query(F.data.startswith("shop_subscribe_"))
async def shop_subscribe(call: CallbackQuery):
    shop_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        client = await get_or_create_client(session, call.from_user.id)
        result = await session.execute(
            select(ShopSubscription).where(
                ShopSubscription.client_id == client.id,
                ShopSubscription.shop_id == shop_id,
            )
        )
        sub = result.scalar_one_or_none()
        if sub:
            await session.delete(sub)
            await session.commit()
            await call.answer("💔 Отписались")
        else:
            session.add(ShopSubscription(client_id=client.id, shop_id=shop_id))
            await session.commit()
            await call.answer("❤️ Подписались")
    await shop_card(call)


@router.callback_query(F.data.startswith("shop_hits_"))
async def shop_hits(call: CallbackQuery):
    shop_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        result = await session.execute(
            select(Product).where(
                Product.shop_id == shop_id, Product.is_active == True,
                Product.is_draft == False, Product.order_count >= 1,
            ).order_by(Product.order_count.desc()).limit(5)
        )
        products = result.scalars().all()

    if not products:
        await call.answer("🔥 Хитов продаж пока нет", show_alert=True)
        return

    items = [{"id": p.id, "title": p.title, "price": helpers.money(p.client_price)} for p in products]
    await call.message.edit_text(
        f"🔥 <b>Хиты продаж ({len(products)})</b>",
        reply_markup=kb.products_list(shop_id, "hits", items, 0, total=len(products)),
    )
    await call.answer()


@router.callback_query(F.data.startswith("shop_reviews_"))
async def shop_reviews(call: CallbackQuery):
    shop_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        result = await session.execute(
            select(Review).where(
                Review.target_type == "shop", Review.target_id == shop_id,
            ).order_by(Review.id.desc()).limit(5)
        )
        reviews = result.scalars().all()

    if not reviews:
        await call.message.edit_text("⭐ <b>Отзывов пока нет.</b>", reply_markup=kb.client_back(f"shop_{shop_id}"))
        await call.answer()
        return

    text = "⭐ <b>Последние отзывы:</b>\n\n"
    for r in reviews:
        text += f"{'⭐' * r.rating}\n"
        if r.comment:
            text += f"💬 {helpers.escape(r.comment[:100])}\n"
        text += "\n"

    await call.message.edit_text(text, reply_markup=kb.client_back(f"shop_{shop_id}"))
    await call.answer()


# ═══════════════════════════════════════════
#   ТОВАРЫ
# ═══════════════════════════════════════════
@router.callback_query(F.data.startswith("shop_products_"))
async def shop_products(call: CallbackQuery):
    shop_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        result = await session.execute(
            select(Product.category, Product.id).where(
                Product.shop_id == shop_id, Product.is_active == True, Product.is_draft == False,
            )
        )
        rows = result.all()

    cats_count = {}
    for cat, _ in rows:
        cats_count[cat] = cats_count.get(cat, 0) + 1
    if not cats_count:
        await call.message.edit_text("😔 В магазине пока нет товаров.", reply_markup=kb.client_back(f"shop_{shop_id}"))
        return

    categories = [(key, helpers.category_name(key), cnt) for key, cnt in cats_count.items()]
    await call.message.edit_text("🗂 <b>Выберите категорию:</b>", reply_markup=kb.shop_categories(shop_id, categories))
    await call.answer()


@router.callback_query(F.data.startswith("cat_"))
async def show_category(call: CallbackQuery):
    parts = call.data.split("_")
    shop_id, category = int(parts[1]), parts[2]

    async with async_session() as session:
        q = select(Product).where(Product.shop_id == shop_id, Product.is_active == True, Product.is_draft == False)
        if category != "all":
            q = q.where(Product.category == category)
        result = await session.execute(q)
        products = result.scalars().all()

    if not products:
        await call.answer("Пусто", show_alert=True)
        return

    items = [{"id": p.id, "title": p.title, "price": helpers.money(p.client_price)} for p in products[:5]]
    await call.message.edit_text(
        f"📦 <b>Товары ({len(products)})</b>",
        reply_markup=kb.products_list(shop_id, category, items, 0, total=len(products)),
    )
    await call.answer()


@router.callback_query(F.data.startswith("prods_"))
async def prods_page(call: CallbackQuery):
    parts = call.data.split("_")
    shop_id, category, page = int(parts[1]), parts[2], int(parts[3])

    async with async_session() as session:
        q = select(Product).where(Product.shop_id == shop_id, Product.is_active == True, Product.is_draft == False)
        if category != "all" and category != "hits":
            q = q.where(Product.category == category)
        result = await session.execute(q)
        products = result.scalars().all()

    page_items = products[page * 5:(page * 5) + 5]
    items = [{"id": p.id, "title": p.title, "price": helpers.money(p.client_price)} for p in page_items]
    await call.message.edit_text(
        f"📦 <b>Товары (стр. {page + 1})</b>",
        reply_markup=kb.products_list(shop_id, category, items, page, total=len(products)),
    )
    await call.answer()


# ═══════════════════════════════════════════
#   КАРТОЧКА ТОВАРА
# ═══════════════════════════════════════════
@router.callback_query(F.data.startswith("product_"))
async def product_card(call: CallbackQuery):
    product_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        r = await session.execute(select(Product).where(Product.id == product_id))
        product = r.scalar_one_or_none()
        if not product:
            await call.answer("Товар не найден", show_alert=True)
            return

        client = await get_or_create_client(session, call.from_user.id)
        fav_result = await session.execute(
            select(Favorite).where(Favorite.client_id == client.id, Favorite.product_id == product_id)
        )
        in_fav = fav_result.scalar_one_or_none() is not None

    text = f"💐 <b>{helpers.escape(product.title)}</b>\n\n📝 {helpers.escape(product.description or '—')}\n\n💰 <b>{helpers.money(product.client_price)}</b>"
    markup = kb.product_card(product_id, in_fav)

    sent = False
    if product.photo_id:
        try:
            file = await bot_shop.get_file(product.photo_id)
            file_bytes = await bot_shop.download_file(file.file_path)
            photo_input = BufferedInputFile(file_bytes.read(), filename="product.jpg")
            await call.message.answer_photo(photo=photo_input, caption=text, reply_markup=markup)
            sent = True
        except Exception as e:
            log.error(f"Ошибка фото товара #{product_id}: {e}")

    if not sent:
        await call.message.answer(text, reply_markup=markup)

    try:
        await call.message.delete()
    except TelegramBadRequest:
        pass
    await call.answer()


@router.callback_query(F.data.startswith("fav_toggle_"))
async def fav_toggle(call: CallbackQuery):
    product_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        client = await get_or_create_client(session, call.from_user.id)
        result = await session.execute(
            select(Favorite).where(Favorite.client_id == client.id, Favorite.product_id == product_id)
        )
        fav = result.scalar_one_or_none()
        if fav:
            await session.delete(fav)
            await session.commit()
            await call.answer("💔 Удалено из избранного")
        else:
            session.add(Favorite(client_id=client.id, product_id=product_id))
            await session.commit()
            await call.answer("❤️ Добавлено в избранное")
    await product_card(call)


# ═══════════════════════════════════════════
#   КОРЗИНА
# ═══════════════════════════════════════════
@router.callback_query(F.data == "client_cart")
async def open_cart(call: CallbackQuery):
    await cart_view(call)


@router.callback_query(F.data.startswith("cart_add_"))
async def cart_add(call: CallbackQuery):
    product_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        client = await get_or_create_client(session, call.from_user.id)
        p_result = await session.execute(select(Product).where(Product.id == product_id))
        product = p_result.scalar_one_or_none()
        if not product or not product.is_active:
            await call.answer("Товар недоступен", show_alert=True)
            return

        cart_result = await session.execute(select(CartItem).where(CartItem.client_id == client.id))
        cart_items = cart_result.scalars().all()

        if cart_items and cart_items[0].shop_id != product.shop_id:
            await call.answer("⚠️ В корзине уже есть товар из другого магазина.", show_alert=True)
            return

        existing = next((ci for ci in cart_items if ci.product_id == product_id), None)
        if existing:
            existing.quantity += 1
        else:
            session.add(CartItem(client_id=client.id, product_id=product_id, shop_id=product.shop_id, quantity=1))
        await session.commit()

    await call.answer("✅ Добавлено в корзину")


@router.callback_query(F.data == "cart_view")
async def cart_view(call: CallbackQuery):
    async with async_session() as session:
        client = await get_or_create_client(session, call.from_user.id)
        result = await session.execute(
            select(CartItem, Product, Shop)
            .join(Product, Product.id == CartItem.product_id)
            .join(Shop, Shop.id == CartItem.shop_id)
            .where(CartItem.client_id == client.id)
        )
        rows = result.all()

    if not rows:
        try:
            await call.message.edit_text("🛒 Корзина пуста.", reply_markup=kb.cart_empty())
        except TelegramBadRequest:
            await call.message.delete()
            await call.message.answer("🛒 Корзина пуста.", reply_markup=kb.cart_empty())
        return

    shop_name = rows[0][2].name
    text = f"🛒 <b>Ваша корзина</b>\n🏪 Магазин: <b>{helpers.escape(shop_name)}</b>\n\n"

    total = Decimal("0.00")
    has_deleted = False
    for ci, p, _ in rows:
        if not p.is_active:
            text += f"❌ <s>{helpers.escape(p.title)}</s> (товар удален)\n"
            has_deleted = True
            continue
        line = Decimal(str(p.client_price)) * ci.quantity
        total += line
        text += f"• {helpers.escape(p.title)} × {ci.quantity} = {helpers.money(line)}\n"

    text += f"\n🚚 Доставка рассчитывается по адресу"
    text += f"\n<b>Итого (без доставки): {helpers.money(total)}</b>"
    if has_deleted:
        text += "\n\n⚠️ <i>Удалите недоступные товары из корзины</i>"

    try:
        await call.message.edit_text(text, reply_markup=kb.cart_view())
    except TelegramBadRequest:
        await call.message.delete()
        await call.message.answer(text, reply_markup=kb.cart_view())

    await call.answer()


@router.callback_query(F.data == "cart_edit")
async def cart_edit(call: CallbackQuery):
    async with async_session() as session:
        client = await get_or_create_client(session, call.from_user.id)
        result = await session.execute(
            select(CartItem, Product).join(Product, Product.id == CartItem.product_id).where(CartItem.client_id == client.id)
        )
        rows = result.all()

    items = [(ci.id, p.title, ci.quantity) for ci, p in rows]
    try:
        await call.message.edit_text("✏️ <b>Изменить количество:</b>", reply_markup=kb.cart_edit(items))
    except TelegramBadRequest:
        await call.message.delete()
        await call.message.answer("✏️ <b>Изменить количество:</b>", reply_markup=kb.cart_edit(items))
    await call.answer()


@router.callback_query(F.data.startswith("cart_plus_"))
async def cart_plus(call: CallbackQuery):
    item_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        result = await session.execute(select(CartItem).where(CartItem.id == item_id))
        ci = result.scalar_one_or_none()
        if ci:
            ci.quantity += 1
            await session.commit()
    await cart_edit(call)


@router.callback_query(F.data.startswith("cart_minus_"))
async def cart_minus(call: CallbackQuery):
    item_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        result = await session.execute(select(CartItem).where(CartItem.id == item_id))
        ci = result.scalar_one_or_none()
        if ci:
            if ci.quantity > 1:
                ci.quantity -= 1
            else:
                await session.delete(ci)
            await session.commit()
    await cart_edit(call)


@router.callback_query(F.data == "cart_remove_menu")
async def cart_remove_menu(call: CallbackQuery):
    async with async_session() as session:
        client = await get_or_create_client(session, call.from_user.id)
        result = await session.execute(
            select(CartItem, Product).join(Product, Product.id == CartItem.product_id).where(CartItem.client_id == client.id)
        )
        rows = result.all()

    items = [(ci.id, p.title) for ci, p in rows]
    try:
        await call.message.edit_text("🗑 <b>Что удалить?</b>", reply_markup=kb.cart_remove_menu(items))
    except TelegramBadRequest:
        await call.message.delete()
        await call.message.answer("🗑 <b>Что удалить?</b>", reply_markup=kb.cart_remove_menu(items))
    await call.answer()


@router.callback_query(F.data.startswith("cart_del_"))
async def cart_del(call: CallbackQuery):
    item_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        await session.execute(delete(CartItem).where(CartItem.id == item_id))
        await session.commit()
    await cart_view(call)


@router.callback_query(F.data == "cart_clear")
async def cart_clear(call: CallbackQuery):
    async with async_session() as session:
        client = await get_or_create_client(session, call.from_user.id)
        await session.execute(delete(CartItem).where(CartItem.client_id == client.id))
        await session.commit()
    try:
        await call.message.edit_text("🗑 Корзина очищена.", reply_markup=kb.cart_empty())
    except TelegramBadRequest:
        await call.message.delete()
        await call.message.answer("🗑 Корзина очищена.", reply_markup=kb.cart_empty())


# ═══════════════════════════════════════════
#   ОФОРМЛЕНИЕ ЗАКАЗА
# ═══════════════════════════════════════════
@router.callback_query(F.data == "cart_checkout")
async def cart_checkout(call: CallbackQuery, state: FSMContext):
    """FIX bug6: проверка гео + проверка непустой корзины."""
    async with async_session() as session:
        client = await get_or_create_client(session, call.from_user.id)
        cart_result = await session.execute(select(CartItem).where(CartItem.client_id == client.id))
        if not cart_result.scalars().first():
            await call.answer("Корзина пуста", show_alert=True)
            return

        if not client.lat or not client.lon:
            # Гео нет — просим отправить, остаёмся в состоянии address_city
            await state.set_state(OrderFSM.address_city)
            await call.message.edit_text(
                "📍 <b>Для расчёта доставки нужна ваша геопозиция</b>\n\n"
                "Отправьте её через скрепку (📎 → Геопозиция). Затем введите ваш город.",
                reply_markup=kb.get_geo_kb(),
            )
            await call.answer()
            return

    await state.set_state(OrderFSM.address_city)
    await call.message.edit_text("📝 <b>Шаг 1/10:</b> Введите ваш город:", reply_markup=kb.order_cancel())
    await call.answer()


@router.callback_query(F.data == "order_cancel", OrderFSM)
async def order_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Оформление отменено.", reply_markup=kb.client_main())
    await call.answer()


@router.callback_query(F.data == "order_new_addr", OrderFSM.address_city)
async def order_new_addr(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("📝 Введите ваш город:", reply_markup=kb.order_cancel())
    await call.answer()


@router.callback_query(F.data == "order_back", OrderFSM)
async def order_back(call: CallbackQuery, state: FSMContext):
    """FIX Feature 5: обработчик «Назад» в оформлении заказа."""
    current = await state.get_state()
    data = await state.get_data()

    if current == OrderFSM.promo.state:
        period = data.get("period")
        if period:
            await state.set_state(OrderFSM.time_slot)
            await call.message.edit_text("🕒 Выберите время:", reply_markup=kb.order_time_slot(period))
        else:
            await state.set_state(OrderFSM.time_period)
            await call.message.edit_text("📝 Выберите период:", reply_markup=kb.order_time_period())
    elif current == OrderFSM.time_period.state:
        await state.set_state(OrderFSM.date)
        await call.message.edit_text("📅 Когда доставить?", reply_markup=kb.order_date())
    else:
        await state.clear()
        await call.message.edit_text("❌ Оформление отменено.", reply_markup=kb.client_main())
    await call.answer()


@router.message(OrderFSM.address_city)
async def order_city(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("❌ Отправьте название города текстом.")
        return
    await state.update_data(city=message.text.strip())
    await state.set_state(OrderFSM.address_street)
    await message.answer("📝 <b>Шаг 2/10:</b> Введите улицу:", reply_markup=kb.order_cancel())


@router.message(OrderFSM.address_street)
async def order_street(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("❌ Отправьте улицу текстом.")
        return
    await state.update_data(street=message.text.strip())
    await state.set_state(OrderFSM.address_house)
    await message.answer("📝 <b>Шаг 3/10:</b> Введите номер дома:", reply_markup=kb.order_cancel())


@router.message(OrderFSM.address_house)
async def order_house(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("❌ Отправьте номер дома.")
        return
    await state.update_data(house=message.text.strip())
    await state.set_state(OrderFSM.address_entrance)
    await message.answer("📝 <b>Шаг 4/10:</b> Введите подъезд (или «-»):", reply_markup=kb.order_cancel())


@router.message(OrderFSM.address_entrance)
async def order_entrance(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("❌ Отправьте текст (или «-»).")
        return
    val = message.text.strip()
    await state.update_data(entrance="" if val == "-" else val)
    await state.set_state(OrderFSM.address_flat)
    await message.answer("📝 <b>Шаг 5/10:</b> Квартира (или «-»):", reply_markup=kb.order_cancel())


@router.message(OrderFSM.address_flat)
async def order_flat(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("❌ Отправьте текст (или «-»).")
        return
    val = message.text.strip()
    await state.update_data(flat="" if val == "-" else val)
    await state.set_state(OrderFSM.address_floor)
    await message.answer("📝 <b>Шаг 6/10:</b> Этаж (или «-»):", reply_markup=kb.order_cancel())


@router.message(OrderFSM.address_floor)
async def order_floor(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("❌ Отправьте текст (или «-»).")
        return
    val = message.text.strip()
    data = await state.get_data()

    address = f"г. {data['city']}, ул. {data['street']}, д. {data['house']}"
    if data.get("entrance"):
        address += f", подъезд {data['entrance']}"
    if data.get("flat"):
        address += f", кв. {data['flat']}"
    if val != "-":
        address += f", этаж {val}"

    await state.update_data(address=address)
    await state.set_state(OrderFSM.client_name)
    await message.answer(
        f"✅ Адрес: {address}\n\n📝 <b>Шаг 7/10:</b> Как зовут получателя?",
        reply_markup=kb.order_cancel(),
    )


@router.message(OrderFSM.client_name)
async def order_set_name(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("❌ Отправьте имя текстом.")
        return
    await state.update_data(client_name=message.text.strip())
    await state.set_state(OrderFSM.client_phone)
    await message.answer("📝 <b>Шаг 8/10:</b> Телефон получателя\nФормат: +79991234567", reply_markup=kb.order_cancel())


@router.message(OrderFSM.client_phone)
async def order_set_phone(message: Message, state: FSMContext):
    if not message.text or not helpers.is_valid_phone(message.text):
        await message.answer("❌ Неверный номер.")
        return
    await state.update_data(client_phone=helpers.clean_phone(message.text))

    # FIX Feature 4: closed_dates — какие дни магазин не работает
    async with async_session() as session:
        client = await get_or_create_client(session, message.from_user.id)
        cart_result = await session.execute(select(CartItem).where(CartItem.client_id == client.id))
        cart_items = cart_result.scalars().all()
        closed = []
        if cart_items:
            shop_id = cart_items[0].shop_id
            shop_r = await session.execute(select(Shop).where(Shop.id == shop_id))
            shop = shop_r.scalar_one_or_none()
            if shop:
                schedule = helpers.str_to_schedule(shop.schedule)
                if schedule:
                    weekday_keys = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
                    today = helpers.today_moscow()
                    for i in range(4):
                        d = today + timedelta(days=i)
                        wk = weekday_keys[d.weekday()]
                        day_sched = str(schedule.get(wk, "")).strip().lower()
                        if day_sched in ("выходной", "off", "-", "closed"):
                            closed.append(str(d))

    await state.update_data(closed_dates=closed)
    await state.set_state(OrderFSM.date)
    closed_set = {date.fromisoformat(s) for s in closed}
    await message.answer("📝 <b>Шаг 9/10:</b> Когда доставить?", reply_markup=kb.order_date(closed_set))


@router.callback_query(F.data.startswith("order_date_"), OrderFSM.date)
async def order_set_date(call: CallbackQuery, state: FSMContext):
    part = call.data.replace("order_date_", "")
    today = helpers.today_moscow()
    if part == "today":
        d = today
    elif part == "tomorrow":
        d = today + timedelta(days=1)
    else:
        d = today + timedelta(days=2)

    # FIX Feature 4: проверка, что магазин не закрыт в этот день
    data = await state.get_data()
    if str(d) in data.get("closed_dates", []):
        await call.answer("🔴 Магазин не работает в этот день. Выберите другой.", show_alert=True)
        return

    await state.update_data(delivery_date=str(d))
    await state.set_state(OrderFSM.time_period)
    await call.message.edit_text("📝 <b>Шаг 10/10:</b> Выберите период:", reply_markup=kb.order_time_period())
    await call.answer()


@router.callback_query(F.data.startswith("order_period_"), OrderFSM.time_period)
async def order_set_period(call: CallbackQuery, state: FSMContext):
    period = call.data.replace("order_period_", "")
    await state.update_data(period=period)
    await state.set_state(OrderFSM.time_slot)
    await call.message.edit_text("🕒 Выберите время:", reply_markup=kb.order_time_slot(period))
    await call.answer()


@router.callback_query(F.data == "order_time_back", OrderFSM.time_slot)
async def order_time_back(call: CallbackQuery, state: FSMContext):
    await state.set_state(OrderFSM.time_period)
    await call.message.edit_text("📝 Выберите период:", reply_markup=kb.order_time_period())
    await call.answer()


@router.callback_query(F.data.startswith("order_slot_"), OrderFSM.time_slot)
async def order_set_slot(call: CallbackQuery, state: FSMContext):
    parts = call.data.split("_")
    slot = parts[-1]
    await state.update_data(delivery_slot=slot)
    await state.set_state(OrderFSM.promo)
    await call.message.edit_text(
        "🎁 <b>Есть промокод?</b>\nВведите код или пропустите.",
        reply_markup=kb.order_promo(),
    )
    await call.answer()


@router.message(OrderFSM.promo)
async def order_set_promo(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("❌ Отправьте код текстом или пропустите.")
        return
    await state.update_data(promo_code=message.text.strip().upper())
    await order_ask_photo(message, state)


@router.callback_query(F.data == "order_skip_promo", OrderFSM.promo)
async def order_skip_promo(call: CallbackQuery, state: FSMContext):
    await state.update_data(promo_code=None)
    await order_ask_photo(call.message, state, edit=True)
    await call.answer()


async def order_ask_photo(message: Message, state: FSMContext, edit: bool = False):
    await state.set_state(OrderFSM.delivery_photo)
    text = "📸 <b>Фото вручения</b>\n\nНужно ли курьеру сфотографировать момент передачи букета?"
    if edit:
        await message.edit_text(text, reply_markup=kb.order_delivery_photo())
    else:
        await message.answer(text, reply_markup=kb.order_delivery_photo())


@router.callback_query(F.data == "order_photo_yes", OrderFSM.delivery_photo)
async def order_photo_yes(call: CallbackQuery, state: FSMContext):
    await state.update_data(need_photo=True)
    await show_order_confirm(call.message, state, edit=True)
    await call.answer()


@router.callback_query(F.data == "order_photo_no", OrderFSM.delivery_photo)
async def order_photo_no(call: CallbackQuery, state: FSMContext):
    await state.update_data(need_photo=False)
    await show_order_confirm(call.message, state, edit=True)
    await call.answer()


# ═══════════════════════════════════════════
#   ПОДТВЕРЖДЕНИЕ И ОПЛАТА
# ═══════════════════════════════════════════
async def show_order_confirm(message: Message, state: FSMContext, edit: bool = False):
    """FIX: реальная дистанция + показ бонусов."""
    data = await state.get_data()

    async with async_session() as session:
        client = await get_or_create_client(session, message.chat.id)

        cart_result = await session.execute(
            select(CartItem, Product).join(Product, Product.id == CartItem.product_id).where(CartItem.client_id == client.id)
        )
        rows = cart_result.all()
        if not rows:
            return

        shop_id = rows[0][0].shop_id
        shop_r = await session.execute(select(Shop).where(Shop.id == shop_id))
        shop = shop_r.scalar_one_or_none()

        distance_km = 0.0
        if client.lat and client.lon and shop and shop.lat and shop.lon:
            distance_km = helpers.distance_km(
                float(client.lat), float(client.lon),
                float(shop.lat), float(shop.lon),
            )

        items = [{"product": p, "quantity": ci.quantity} for ci, p in rows]
        totals = orders_service.calculate_cart_total(items, distance_km)

        bonus_available = Decimal(str(client.bonus_balance or 0))

    text = "🧾 <b>Проверьте заказ</b>\n\n"
    for ci, p in rows:
        text += f"• {helpers.escape(p.title)} × {ci.quantity} = {helpers.money(Decimal(str(p.client_price)) * ci.quantity)}\n"

    if totals["discount"] > 0:
        text += f"\n🎁 Скидка 3%: -{helpers.money(totals['discount'])}"
    text += f"\n🚚 Доставка ({distance_km:.1f} км): {helpers.money(totals['delivery'])}"
    if data.get("promo_code"):
        text += f"\n🏷 Промокод: {data['promo_code']}"

    text += f"\n\n📍 {helpers.escape(data.get('address'))}\n👤 {helpers.escape(data.get('client_name'))}\n📞 {helpers.escape(data.get('client_phone'))}"
    text += f"\n📅 {data.get('delivery_date')} | 🕒 {data.get('delivery_slot')}"
    text += f"\n📸 Фото вручения: {'Да' if data.get('need_photo') else 'Нет'}"
    text += f"\n\n<b>Итого: {helpers.money(totals['total'])}</b>"

    if bonus_available > 0:
        final = totals["total"] - bonus_available
        if final < 0:
            final = Decimal("0")
        text += f"\n🎁 Бонусов доступно: {helpers.money(bonus_available)} (спишутся автоматически)"
        text += f"\n<b>К оплате: {helpers.money(final)}</b>"

    await state.update_data(distance_km=distance_km)
    await state.set_state(OrderFSM.confirm)
    if edit:
        await message.edit_text(text, reply_markup=kb.order_confirm())
    else:
        await message.answer(text, reply_markup=kb.order_confirm())


@router.callback_query(F.data == "order_edit", OrderFSM.confirm)
async def order_edit(call: CallbackQuery, state: FSMContext):
    await state.set_state(OrderFSM.address_city)
    await call.message.edit_text("📝 <b>Шаг 1/10:</b> Введите ваш город заново:", reply_markup=kb.order_cancel())
    await call.answer()


@router.callback_query(F.data == "order_pay", OrderFSM.confirm)
async def order_pay(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()

    async with async_session() as session:
        client = await get_or_create_client(session, call.from_user.id)
        # FIX: убран distance_km (в новой сигнатуре нет)
        order = await orders_service.create_order_from_cart(
            session=session,
            client_id=client.id,
            address=data.get("address"),
            client_name=data.get("client_name"),
            client_phone=data.get("client_phone"),
            delivery_date=date.fromisoformat(data.get("delivery_date")),
            delivery_slot=data.get("delivery_slot"),
            promo_code=data.get("promo_code"),
            need_photo=data.get("need_photo", True),
        )

    if not order:
        await call.message.edit_text(
            "❌ <b>Не удалось создать заказ.</b>\n\n"
            "Возможные причины:\n"
            "• Товар закончился\n"
            "• Магазин закрыт на эту дату\n"
            "• Закончились бонусы/промокод\n\n"
            "Попробуйте ещё раз.",
            reply_markup=kb.client_main(),
        )
        await state.clear()
        await call.answer()
        return

    # Если заказ полностью оплачен бонусами — payment_status уже confirmed
    if order.payment_status == "confirmed":
        msg = await call.message.edit_text(
            f"✅ <b>Заказ #{order.id} оплачен бонусами!</b>\n\n"
            f"Магазин получил заказ. Ожидайте подтверждения.",
            reply_markup=kb.client_main(),
        )
        # Сохраняем client_message_id
        async with async_session() as session:
            o_r = await session.execute(select(Order).where(Order.id == order.id))
            o = o_r.scalar_one_or_none()
            if o:
                o.client_message_id = msg.message_id
                await session.commit()

        # Уведомляем админа
        try:
            await bot_admin.send_message(
                config.ADMIN_ID,
                f"✅ <b>Заказ #{order.id} оплачен бонусами</b>\n\n💰 {helpers.money(order.total_price)}",
            )
        except Exception:
            pass

        await state.clear()
        await call.answer()
        return

    await state.update_data(order_id=order.id, order_total=float(order.total_price))

    text = (
        f"💳 <b>Оплата заказа #{order.id}</b>\n\n"
        f"Сумма: <b>{helpers.money(order.total_price)}</b>\n\n"
        f"Переведите на карту:\n<code>{config.CARD_NUMBER}</code>\n"
        f"Получатель: {config.CARD_HOLDER}\nБанк: {config.BANK_NAME}\n\n"
        f"📝 <b>В комментарии ОБЯЗАТЕЛЬНО укажите:</b> <code>{order.id}</code>\n\n"
        f"После оплаты нажмите «✅ Я оплатил»."
    )
    await state.set_state(OrderFSM.payment)
    await call.message.edit_text(text, reply_markup=kb.order_payment())
    await call.answer()


@router.callback_query(F.data == "order_paid", OrderFSM.payment)
async def order_paid(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    order_id = data.get("order_id")

    if not order_id:
        await call.message.edit_text("❌ Ошибка: заказ не найден.", reply_markup=kb.client_main())
        await state.clear()
        await call.answer()
        return

    async with async_session() as session:
        o_r = await session.execute(select(Order).where(Order.id == order_id))
        order = o_r.scalar_one_or_none()

        if order:
            msg = await call.message.edit_text(
                f"✅ <b>Заказ #{order.id} ожидает подтверждения оплаты.</b>\n\n"
                f"💳 Мы проверяем ваш платёж. Пожалуйста, подождите.\n\n"
                f"<i>Обычно это занимает до 15 минут.</i>",
                reply_markup=kb.client_main(),
            )
            order.client_message_id = msg.message_id
            await session.commit()

    await state.clear()

    if order:
        try:
            await bot_admin.send_message(
                config.ADMIN_ID,
                f"💳 <b>Новый платёж!</b>\n\n📦 Заказ #{order_id}\n💰 Сумма: {helpers.money(order.total_price)}",
                reply_markup=kb.admin_confirm_payment(order_id),
            )
        except Exception as e:
            log.error(f"Ошибка отправки админу: {e}")

    await call.answer()


# ═══════════════════════════════════════════
#   МОИ ЗАКАЗЫ И ТРЕКИНГ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "client_orders")
async def my_orders(call: CallbackQuery):
    async with async_session() as session:
        client = await get_or_create_client(session, call.from_user.id)
        orders = await orders_service.get_client_orders(session, client.id)

        items = []
        for o in orders[:10]:
            can_rate = False
            if o.status == "done":
                # FIX: Review.from_user_id (не from_tg_id)
                r = await session.execute(
                    select(Review).where(
                        Review.order_id == o.id,
                        Review.from_user_id == call.from_user.id,
                        Review.target_type == "shop",
                    )
                )
                if not r.scalar_one_or_none():
                    can_rate = True
            items.append({
                "id": o.id, "status": o.status,
                "price": helpers.money(o.total_price), "can_rate": can_rate,
            })

    if not items:
        await call.message.edit_text("📦 У вас пока нет заказов.", reply_markup=kb.client_back())
        await call.answer()
        return

    await call.message.edit_text(
        f"📦 <b>Мои заказы ({len(orders)})</b>\n\nНажмите на заказ для деталей:",
        reply_markup=kb.orders_list(items),
    )
    await call.answer()


@router.callback_query(F.data.startswith("track_refresh_"))
async def track_refresh(call: CallbackQuery):
    order_id = int(call.data.split("_")[-1])
    await show_track(call.message, order_id, edit=True)
    await call.answer("Обновлено")


async def show_track(message: Message, order_id: int, edit: bool = False):
    async with async_session() as session:
        result = await session.execute(select(Order).where(Order.id == order_id))
        order = result.scalar_one_or_none()
        if not order:
            return

        courier = None
        if order.courier_id:
            c_result = await session.execute(select(Courier).where(Courier.id == order.courier_id))
            courier = c_result.scalar_one_or_none()

        shop_res = await session.execute(select(Shop).where(Shop.id == order.shop_id))
        shop = shop_res.scalar_one_or_none()

    status_map = {
        "pending": "⏳ Ожидает подтверждения оплаты", "new": "🆕 Оплачен, ждет магазина",
        "wait": "🔍 Ищем курьера", "going": "🚴 Курьер едет в магазин",
        "picked": "📦 Курьер забрал букет", "delivering": "🚴 Курьер везёт вам",
        "at_client": "📍 Курьер у вас", "done": "✅ Доставлено", "cancel": "❌ Отменено",
    }
    status_text = status_map.get(order.status, order.status)

    text = (
        f"📦 <b>Заказ #{order.id}</b>\n\n"
        f"📍 {helpers.escape(order.address)}\n💰 {helpers.money(order.total_price)}\n"
        f"🕒 {helpers.format_date(order.delivery_date)} {order.delivery_slot or ''}\n\n"
        f"━━━━━━━━━━━━━━━\n<b>{status_text}</b>\n"
    )

    if order.is_preorder:
        text += "🗓 <b>ПРЕДЗАКАЗ</b>\n"

    if courier and order.status in ("going", "picked", "delivering", "at_client"):
        text += f"\n👤 Курьер: {helpers.escape(courier.name)}\n📞 {helpers.escape(courier.phone)}\n⭐ {float(courier.rating or 0):.1f}"

    if shop and shop.phone and order.status in ("wait", "going", "picked"):
        text += f"\n\n🏪 Магазин: {helpers.escape(shop.name)}\n📞 {helpers.escape(shop.phone)}"

    # FIX bug15: передаём payment_status — «Отменить» скрыта, если оплачено
    markup = kb.track_order(
        order_id, order.status, courier.phone if courier else None,
        float(courier.lat) if courier and courier.lat else None,
        float(courier.lon) if courier and courier.lon else None,
        payment_status=order.payment_status,
    )

    if edit:
        try:
            await message.edit_text(text, reply_markup=markup)
        except TelegramBadRequest:
            pass
    else:
        await message.answer(text, reply_markup=markup)


# ═══════════════════════════════════════════
#   ОТМЕНА ЗАКАЗА
# ═══════════════════════════════════════════
@router.callback_query(F.data.startswith("track_cancel_") & ~F.data.startswith("track_cancel_yes_"))
async def track_cancel(call: CallbackQuery):
    order_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        result = await session.execute(select(Order).where(Order.id == order_id))
        order = result.scalar_one_or_none()

    if not order:
        await call.answer("Заказ не найден", show_alert=True)
        return
    if order.status != "pending":
        await call.answer("❌ Заказ уже в работе. Отмена невозможна.", show_alert=True)
        return
    # FIX bug15: если оплачен — нельзя отменить
    if order.payment_status == "confirmed":
        await call.answer("❌ Заказ уже оплачен. Отмена невозможна — свяжитесь с поддержкой.", show_alert=True)
        return

    await call.message.edit_text(f"❌ <b>Отменить заказ #{order_id}?</b>", reply_markup=kb.cancel_confirm(order_id))
    await call.answer()


@router.callback_query(F.data.startswith("track_cancel_yes_"))
async def track_cancel_yes(call: CallbackQuery):
    order_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        order = await orders_service.cancel_order(
            session, order_id, reason="client_cancelled", cancelled_by="client", refund=True,
        )
    if not order:
        await call.answer("❌ Отмена невозможна", show_alert=True)
        return
    await call.message.edit_text(
        f"✅ Заказ #{order_id} отменён.\n💰 Деньги вернулись на баланс.",
        reply_markup=kb.client_main(),
    )
    await call.answer()


# ═══════════════════════════════════════════
#   ОЦЕНКА (Feature 6: магазин + курьер)
# ═══════════════════════════════════════════
async def _save_rating(call: CallbackQuery, order_id: int, target_type: str, rating: int):
    """Сохраняет отзыв и обновляет средний рейтинг."""
    async with async_session() as session:
        o_r = await session.execute(select(Order).where(Order.id == order_id))
        order = o_r.scalar_one_or_none()
        if not order:
            return

        if target_type == "shop":
            target_id = order.shop_id
        elif target_type == "courier":
            target_id = order.courier_id
        else:
            return

        if not target_id:
            return

        # Защита от дублей
        existing = await session.execute(
            select(Review).where(
                Review.order_id == order_id,
                Review.from_user_id == call.from_user.id,
                Review.target_type == target_type,
            )
        )
        if existing.scalar_one_or_none():
            return

        session.add(Review(
            order_id=order_id, from_user_id=call.from_user.id, from_platform="tg",
            target_type=target_type, target_id=target_id, rating=rating,
        ))

        # Обновляем средний рейтинг
        if target_type == "shop":
            r = await session.execute(select(Shop).where(Shop.id == target_id))
            obj = r.scalar_one_or_none()
        else:
            r = await session.execute(select(Courier).where(Courier.id == target_id))
            obj = r.scalar_one_or_none()

        if obj:
            n = obj.reviews_count or 0
            old = float(obj.rating or 0)
            new = (old * n + rating) / (n + 1)
            obj.rating = round(new, 2)
            obj.reviews_count = n + 1

            # Проверяем ачивки курьера (five_star)
            if target_type == "courier":
                await bonuses_service.check_achievements(session, target_id)

        await session.commit()


@router.callback_query(F.data.startswith("rate_start_"))
async def rate_start(call: CallbackQuery):
    """Из списка заказов — начать оценку магазина."""
    order_id = int(call.data.split("_")[-1])
    await call.message.edit_text(
        f"⭐ <b>Оцените заказ #{order_id}</b>\n\nМагазин:",
        reply_markup=kb.rating_kb("shop", order_id),
    )
    await call.answer()


@router.callback_query(F.data.startswith("rate_shop_") & ~F.data.startswith("rate_shop_skip"))
async def rate_shop(call: CallbackQuery):
    parts = call.data.split("_")
    order_id = int(parts[2])
    rating = int(parts[3])
    await _save_rating(call, order_id, "shop", rating)
    # После магазина — оценить курьера
    await call.message.edit_text(
        "⭐ Спасибо за оценку магазина!\n\n🚴 Оцените курьера:",
        reply_markup=kb.rating_kb("courier", order_id),
    )
    await call.answer()


@router.callback_query(F.data.startswith("rate_shop_skip_"))
async def rate_shop_skip(call: CallbackQuery):
    order_id = int(call.data.split("_")[-1])
    await call.message.edit_text(
        "🚴 Оцените курьера:",
        reply_markup=kb.rating_kb("courier", order_id),
    )
    await call.answer()


@router.callback_query(F.data.startswith("rate_courier_") & ~F.data.startswith("rate_courier_skip"))
async def rate_courier(call: CallbackQuery):
    parts = call.data.split("_")
    order_id = int(parts[2])
    rating = int(parts[3])
    await _save_rating(call, order_id, "courier", rating)
    # После обеих оценок — предложить чаевые
    await call.message.edit_text(
        "⭐ Спасибо! Ваш отзыв сохранён.\n\n💵 Хотите оставить чаевые курьеру?",
        reply_markup=kb.client_tip(order_id),
    )
    await call.answer()


@router.callback_query(F.data.startswith("rate_courier_skip_"))
async def rate_courier_skip(call: CallbackQuery):
    order_id = int(call.data.split("_")[-1])
    await call.message.edit_text(
        "💵 Хотите оставить чаевые курьеру?",
        reply_markup=kb.client_tip(order_id),
    )
    await call.answer()


# ═══════════════════════════════════════════
#   ЧАЕВЫЕ (Feature 7)
# ═══════════════════════════════════════════
@router.callback_query(F.data.startswith("tip_") & ~F.data.startswith("tip_custom") & ~F.data.startswith("tip_skip"))
async def tip_add(call: CallbackQuery):
    parts = call.data.split("_")
    order_id = int(parts[1])
    amount = Decimal(parts[2])

    async with async_session() as session:
        ok = await orders_service.add_tip_to_order(session, order_id, amount)

    if ok:
        await call.message.edit_text(
            f"💵 <b>Спасибо!</b>\n\nЧаевые {helpers.money(amount)} переданы курьеру.",
            reply_markup=kb.client_main(),
        )
    else:
        await call.answer("❌ Недостаточно средств на балансе", show_alert=True)
        return
    await call.answer()


@router.callback_query(F.data.startswith("tip_custom_"))
async def tip_custom(call: CallbackQuery, state: FSMContext):
    order_id = int(call.data.split("_")[-1])
    await state.update_data(tip_order_id=order_id)
    await state.set_state(ClientFSM.tip_custom)
    await call.message.edit_text("💵 Введите сумму чаевых:", reply_markup=kb.cancel_kb("client_main"))
    await call.answer()


@router.message(ClientFSM.tip_custom)
async def tip_custom_save(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("❌ Введите число.")
        return
    try:
        amount = Decimal(message.text.replace(",", ".").strip())
        if amount <= 0:
            raise ValueError
    except (ValueError, TypeError):
        await message.answer("❌ Введите число больше 0.")
        return

    data = await state.get_data()
    order_id = data.get("tip_order_id")
    if not order_id:
        await state.clear()
        await message.answer("❌ Ошибка контекста.", reply_markup=kb.client_main())
        return

    async with async_session() as session:
        ok = await orders_service.add_tip_to_order(session, order_id, amount)

    await state.clear()
    if ok:
        await message.answer(f"✅ Чаевые {helpers.money(amount)} переданы курьеру!", reply_markup=kb.client_main())
    else:
        await message.answer("❌ Недостаточно средств на балансе.", reply_markup=kb.client_main())


@router.callback_query(F.data.startswith("tip_skip_"))
async def tip_skip(call: CallbackQuery):
    await call.message.edit_text("Спасибо!", reply_markup=kb.client_main())
    await call.answer()


# ═══════════════════════════════════════════
#   ЧАТ И ПРОБЛЕМЫ
# ═══════════════════════════════════════════
@router.callback_query(F.data.startswith("chat_shop_"))
async def chat_shop(call: CallbackQuery, state: FSMContext):
    order_id = int(call.data.split("_")[-1])
    await state.update_data(chat_order_id=order_id, chat_target="shop")
    await state.set_state(ClientFSM.chat_message)
    await call.message.answer("💬 Введите сообщение для магазина:", reply_markup=kb.cancel_kb(f"track_refresh_{order_id}"))
    await call.answer()


@router.callback_query(F.data.startswith("chat_courier_"))
async def chat_courier(call: CallbackQuery, state: FSMContext):
    order_id = int(call.data.split("_")[-1])
    await state.update_data(chat_order_id=order_id, chat_target="courier")
    await state.set_state(ClientFSM.chat_message)
    await call.message.answer("💬 Введите сообщение для курьера:", reply_markup=kb.cancel_kb(f"track_refresh_{order_id}"))
    await call.answer()


@router.callback_query(F.data.startswith("track_problem_"))
async def track_problem(call: CallbackQuery):
    order_id = int(call.data.split("_")[-1])
    try:
        await bot_admin.send_message(
            config.ADMIN_ID,
            f"🆘 <b>Проблема с заказом #{order_id}</b>\n\nКлиент нажал кнопку «Проблема».\nСвяжитесь с ним.",
        )
    except Exception:
        pass
    await call.answer("🆘 Администратор уведомлен. Мы свяжемся с вами.", show_alert=True)


# ═══════════════════════════════════════════
#   ИЗБРАННОЕ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "client_favorites")
async def favorites(call: CallbackQuery):
    async with async_session() as session:
        client = await get_or_create_client(session, call.from_user.id)
        result = await session.execute(
            select(Product).join(Favorite, Favorite.product_id == Product.id).where(
                Favorite.client_id == client.id, Product.is_active == True,
            )
        )
        products = result.scalars().all()

    if not products:
        await call.message.edit_text("❤️ В избранном пусто.", reply_markup=kb.client_back())
        await call.answer()
        return

    items = [{"id": p.id, "title": p.title} for p in products]
    await call.message.edit_text(f"❤️ <b>Избранное ({len(items)})</b>", reply_markup=kb.favorites_list(items))
    await call.answer()


# ═══════════════════════════════════════════
#   БАЛАНС И ВЫВОД
# ═══════════════════════════════════════════
@router.callback_query(F.data == "client_balance")
async def balance(call: CallbackQuery):
    async with async_session() as session:
        client = await get_or_create_client(session, call.from_user.id)
        txs = await payments_service.get_user_transactions(session, "client", client.id, 5)
        balance_val = client.balance
        bonus_val = client.bonus_balance

    text = (
        f"💰 <b>Мой баланс: {helpers.money(balance_val)}</b>\n"
        f"🎁 Бонусов: {helpers.money(bonus_val)} <i>(только на заказы)</i>\n\n"
    )
    if txs:
        text += "Последние операции:\n"
        for t in txs:
            sign = "+" if float(t.amount) >= 0 else ""
            text += f"{sign}{helpers.money(t.amount)} — {t.type}\n"

    await call.message.edit_text(text, reply_markup=kb.client_balance())
    await call.answer()


@router.callback_query(F.data == "balance_history")
async def balance_history(call: CallbackQuery):
    async with async_session() as session:
        client = await get_or_create_client(session, call.from_user.id)
        txs = await payments_service.get_user_transactions(session, "client", client.id, 30)

    if not txs:
        await call.message.edit_text("📜 История пуста.", reply_markup=kb.client_back("client_balance"))
        await call.answer()
        return

    text = "📜 <b>История операций:</b>\n\n"
    for t in txs:
        sign = "+" if float(t.amount) >= 0 else ""
        text += f"{helpers.format_dt(t.created_at)} — {sign}{helpers.money(t.amount)} — {t.type}\n"

    await call.message.edit_text(text, reply_markup=kb.client_back("client_balance"))
    await call.answer()


@router.callback_query(F.data == "balance_withdraw")
async def balance_withdraw(call: CallbackQuery):
    async with async_session() as session:
        client = await get_or_create_client(session, call.from_user.id)
        if float(client.balance) < config.CLIENT_MIN_WITHDRAW:
            await call.answer(f"❌ Минимум для вывода: {config.CLIENT_MIN_WITHDRAW} ₽", show_alert=True)
            return

    await call.message.edit_text(
        f"💸 <b>Вывод на карту</b>\n\n💰 Баланс: {helpers.money(client.balance)}\n"
        f"💳 Комиссия: {config.CLIENT_WITHDRAW_COMMISSION}%\n💵 Минимум: {config.CLIENT_MIN_WITHDRAW} ₽\n\n"
        f"Выберите способ:",
        reply_markup=kb.withdraw_method(),
    )
    await call.answer()


@router.callback_query(F.data == "wd_card")
async def wd_card(call: CallbackQuery, state: FSMContext):
    await state.set_state(ClientFSM.withdraw_amount)
    await state.update_data(method="card")
    await call.message.edit_text("💳 <b>Вывод на карту</b>\n\nВведите сумму:", reply_markup=kb.cancel_kb("client_balance"))
    await call.answer()


@router.callback_query(F.data == "wd_sbp")
async def wd_sbp(call: CallbackQuery, state: FSMContext):
    await state.set_state(ClientFSM.withdraw_amount)
    await state.update_data(method="sbp")
    await call.message.edit_text("📱 <b>Вывод по СБП</b>\n\nВведите сумму:", reply_markup=kb.cancel_kb("client_balance"))
    await call.answer()


@router.message(ClientFSM.withdraw_amount)
async def process_withdraw(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("❌ Введите число.")
        return
    try:
        amount = Decimal(message.text.replace(",", ".").strip())
    except Exception:
        await message.answer("❌ Введите число.")
        return

    async with async_session() as session:
        client = await get_or_create_client(session, message.from_user.id)
        if amount < config.CLIENT_MIN_WITHDRAW:
            await message.answer(f"❌ Минимум {config.CLIENT_MIN_WITHDRAW} ₽")
            return
        if amount > client.balance:
            await message.answer(f"❌ Недостаточно средств. Ваш баланс: {helpers.money(client.balance)}")
            return

    await state.update_data(withdraw_amount=float(amount))
    data = await state.get_data()
    method = data.get("method", "card")

    # FIX: SBP-флоу отдельно от карты
    if method == "sbp":
        await state.set_state(ClientFSM.withdraw_sbp)
        await message.answer("📱 Введите телефон для СБП:", reply_markup=kb.cancel_kb("client_balance"))
    else:
        await state.set_state(ClientFSM.withdraw_card)
        await message.answer("💳 Введите номер карты (13/16/19 цифр):", reply_markup=kb.cancel_kb("client_balance"))


@router.message(ClientFSM.withdraw_card)
async def process_withdraw_card(message: Message, state: FSMContext):
    if not message.text or not helpers.is_valid_card(message.text):
        await message.answer("❌ Неверный номер карты.")
        return

    data = await state.get_data()
    amount = Decimal(str(data["withdraw_amount"]))
    card = helpers.clean_phone(message.text)

    async with async_session() as session:
        client = await get_or_create_client(session, message.from_user.id)
        payout = await payments_service.create_payout(
            session=session, user_type="client", user_id=client.id,
            amount=amount, method="card", card_number=card,
        )

        if not payout:
            await message.answer("❌ Ошибка. Недостаточно средств.", reply_markup=kb.client_main())
            await state.clear()
            return

    await state.clear()
    commission = amount * Decimal(str(config.CLIENT_WITHDRAW_COMMISSION)) / 100
    await message.answer(
        f"✅ Заявка на вывод создана.\n\n💰 Сумма: {helpers.money(amount)}\n"
        f"📉 Комиссия: -{helpers.money(commission)}\n💵 К получению: {helpers.money(amount - commission)}",
        reply_markup=kb.client_main(),
    )


@router.message(ClientFSM.withdraw_sbp)
async def process_withdraw_sbp(message: Message, state: FSMContext):
    if not message.text or not helpers.is_valid_phone(message.text):
        await message.answer("❌ Неверный номер телефона.")
        return

    data = await state.get_data()
    amount = Decimal(str(data["withdraw_amount"]))
    sbp_phone = helpers.clean_phone(message.text)

    async with async_session() as session:
        client = await get_or_create_client(session, message.from_user.id)
        payout = await payments_service.create_payout(
            session=session, user_type="client", user_id=client.id,
            amount=amount, method="sbp", sbp_phone=sbp_phone,
        )

        if not payout:
            await message.answer("❌ Ошибка. Недостаточно средств.", reply_markup=kb.client_main())
            await state.clear()
            return

    await state.clear()
    commission = amount * Decimal(str(config.CLIENT_WITHDRAW_COMMISSION)) / 100
    await message.answer(
        f"✅ Заявка на вывод создана.\n\n💰 Сумма: {helpers.money(amount)}\n"
        f"📉 Комиссия: -{helpers.money(commission)}\n💵 К получению: {helpers.money(amount - commission)}",
        reply_markup=kb.client_main(),
    )


# ═══════════════════════════════════════════
#   ПРОМОКОД И СОБЫТИЯ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "client_promo")
async def promo_menu(call: CallbackQuery, state: FSMContext):
    await state.set_state(ClientFSM.promo_input)
    await call.message.edit_text("🎁 <b>Активация промокода</b>\n\nВведите код:", reply_markup=kb.client_back())
    await call.answer()


@router.message(ClientFSM.promo_input)
async def promo_apply(message: Message, state: FSMContext):
    """FIX: fixed → бонусы на счёт; percent → скидка при заказе."""
    if not message.text:
        await message.answer("❌ Отправьте код текстом.")
        return
    code = message.text.strip().upper()

    async with async_session() as session:
        client = await get_or_create_client(session, message.from_user.id)
        promo = await orders_service.check_promo(session, code)

        if not promo:
            await message.answer("❌ Промокод не найден.", reply_markup=kb.client_main())
            await state.clear()
            return

        if promo.valid_until and promo.valid_until < helpers.today_moscow():
            await message.answer("❌ Промокод истёк.", reply_markup=kb.client_main())
            await state.clear()
            return

        if promo.max_uses > 0 and promo.used_count >= promo.max_uses:
            await message.answer("❌ Промокод больше не действует.", reply_markup=kb.client_main())
            await state.clear()
            return

        # Защита от повторного использования
        used = await session.execute(
            select(PromoUse).where(PromoUse.promo_id == promo.id, PromoUse.client_id == client.id)
        )
        if used.scalar_one_or_none():
            await message.answer("❌ Вы уже использовали этот промокод.", reply_markup=kb.client_main())
            await state.clear()
            return

        if promo.discount_type == "fixed":
            # Бонусы на бонусный счёт
            client.bonus_balance = Decimal(str(client.bonus_balance or 0)) + promo.discount_value
            promo.used_count += 1
            session.add(PromoUse(promo_id=promo.id, client_id=client.id, order_id=0))
            await session.commit()

            d = helpers.money(promo.discount_value)
            await state.clear()
            await message.answer(
                f"✅ <b>Промокод активирован!</b>\n\n🎁 +{d} на бонусный счёт.\n"
                f"💰 Бонусы спишутся автоматически при следующем заказе.",
                reply_markup=kb.client_main(),
            )
        else:
            # percent — сохраняем для следующего заказа
            client.active_promo = code
            await session.commit()

            d = f"{int(promo.discount_value)}%"
            await state.clear()
            await message.answer(
                f"✅ <b>Промокод активирован!</b>\n\n🎁 {code} — {d}\n"
                f"Скидка применится к следующему заказу.",
                reply_markup=kb.client_main(),
            )


@router.callback_query(F.data == "client_events")
async def events(call: CallbackQuery):
    async with async_session() as session:
        client = await get_or_create_client(session, call.from_user.id)
        result = await session.execute(
            select(ClientEvent).where(ClientEvent.client_id == client.id).order_by(ClientEvent.event_date.asc())
        )
        events_list = result.scalars().all()

    if not events_list:
        text = "📅 <b>Мои события</b>\n\nВы пока не добавили ни одного события."
    else:
        text = f"📅 <b>Мои события ({len(events_list)})</b>\n\n"
        for e in events_list:
            text += f"• {helpers.format_date(e.event_date)} — {helpers.escape(e.title)}\n"

    await call.message.edit_text(text, reply_markup=kb.events_menu())
    await call.answer()


@router.callback_query(F.data == "event_add")
async def event_add(call: CallbackQuery, state: FSMContext):
    await state.set_state(ClientFSM.event_whom)
    await call.message.edit_text("📅 <b>Кому напомнить?</b>", reply_markup=kb.event_whom())
    await call.answer()


@router.callback_query(F.data.startswith("event_whom_") & ~F.data.startswith("event_whom_custom"), ClientFSM.event_whom)
async def event_set_whom(call: CallbackQuery, state: FSMContext):
    whom = call.data.replace("event_whom_", "")
    await state.update_data(event_whom=whom)
    await state.set_state(ClientFSM.event_date)
    await call.message.edit_text(
        "📅 <b>Когда?</b>\n\nВведите дату ДД.ММ.ГГГГ\nПример: 15.05.1990",
        reply_markup=kb.cancel_kb("client_main"),
    )
    await call.answer()


@router.message(ClientFSM.event_date)
async def event_set_date(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("❌ Отправьте дату текстом.")
        return
    try:
        d = datetime.strptime(message.text.strip(), "%d.%m.%Y").date()
    except Exception:
        await message.answer("❌ Неверный формат. Пример: 15.05.1990")
        return
    await state.update_data(event_date=str(d))
    await state.set_state(ClientFSM.event_type)
    await message.answer("🎉 <b>Что за событие?</b>", reply_markup=kb.event_type())


@router.callback_query(F.data.startswith("event_type_") & ~F.data.startswith("event_type_custom"), ClientFSM.event_type)
async def event_set_type(call: CallbackQuery, state: FSMContext):
    etype = call.data.replace("event_type_", "")
    data = await state.get_data()
    title = f"{etype} {data.get('event_whom', '')}".strip()

    async with async_session() as session:
        client = await get_or_create_client(session, call.from_user.id)
        session.add(ClientEvent(
            client_id=client.id, title=title, event_type=etype,
            event_date=datetime.strptime(data["event_date"], "%Y-%m-%d").date(),
        ))
        await session.commit()

    await state.clear()
    await call.message.edit_text(
        f"✅ Событие добавлено!\n\n📅 {data['event_date']} — {helpers.escape(title)}",
        reply_markup=kb.client_main(),
    )
    await call.answer()


# ═══════════════════════════════════════════
#   ОТПРАВКА СООБЩЕНИЯ (ЧАТ)
# ═══════════════════════════════════════════
@router.message(ClientFSM.chat_message)
async def client_send_chat_message(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("❌ Отправьте текст сообщения.")
        return

    data = await state.get_data()
    order_id = data.get("chat_order_id")
    target = data.get("chat_target")
    text = message.text.strip()

    async with async_session() as session:
        o_r = await session.execute(select(Order).where(Order.id == order_id))
        order = o_r.scalar_one_or_none()
        if not order:
            await message.answer("❌ Заказ не найден.")
            await state.clear()
            return

        if target == "shop":
            await notify.send_notification(
                session=session, recipient_type="shop", recipient_id=order.shop_id,
                text=f"💬 <b>Сообщение от клиента по заказу #{order_id}:</b>\n\n{helpers.escape(text)}",
            )
            await message.answer("✅ Сообщение отправлено магазину.", reply_markup=kb.client_main())
        elif target == "courier" and order.courier_id:
            await notify.send_notification(
                session=session, recipient_type="courier", recipient_id=order.courier_id,
                text=f"💬 <b>Сообщение от клиента по заказу #{order_id}:</b>\n\n{helpers.escape(text)}",
            )
            await message.answer("✅ Сообщение отправлено курьеру.", reply_markup=kb.client_main())
        else:
            await message.answer("❌ Ошибка: получатель не найден.")

    await state.clear()
