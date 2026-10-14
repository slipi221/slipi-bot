# -*- coding: utf-8 -*-
"""
SLIPI — бот клиента
"""
from decimal import Decimal

from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

import config
import keyboards as kb
from states import OrderFSM, ClientFSM
from database import async_session
from models import Client, Shop, Product, CartItem, Favorite, Order, ClientAddress
from services import orders as orders_service
from services import geo as geo_service
from services import payments as payments_service
from utils import helpers

from sqlalchemy import select, delete, update

router = Router(name="client")


# ═══════════════════════════════════════════
#   ХЕЛПЕРЫ
# ═══════════════════════════════════════════
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
#   /start
# ═══════════════════════════════════════════
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        await get_or_create_client(session, message.from_user.id)

    text = (
        "🌸 <b>Добро пожаловать в SLIPI!</b>\n"
        f"Доставка цветов и подарков по городу {config.CITY}.\n"
        f"🕒 Работаем: {config.WORK_HOURS}\n\n"
        "Выберите действие:"
    )
    await message.answer(text, reply_markup=kb.client_main())


@router.callback_query(F.data == "client_main")
async def back_to_main(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text(
        f"🌸 <b>{config.SERVICE_NAME}</b>\nВыберите действие:",
        reply_markup=kb.client_main()
    )
    await call.answer()


@router.callback_query(F.data == "client_about")
async def about(call: CallbackQuery):
    text = (
        f"ℹ️ <b>{config.SERVICE_NAME}</b>\n"
        f"Доставка цветов и подарков\n\n"
        f"🏙 Город: {config.CITY}\n"
        f"🕒 Работаем: {config.WORK_HOURS}\n"
        f"📞 Поддержка: {config.SUPPORT_TG}"
    )
    await call.message.edit_text(text, reply_markup=kb.client_back())
    await call.answer()


# ═══════════════════════════════════════════
#   КАТАЛОГ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "client_catalog")
async def catalog(call: CallbackQuery):
    text = "📍 Чтобы показать ближайшие магазины, поделитесь геолокацией."
    await call.message.edit_text(text, reply_markup=kb.client_geo())
    await call.answer()


@router.callback_query(F.data == "client_all_shops")
async def all_shops(call: CallbackQuery):
    async with async_session() as session:
        shops = await geo_service.get_all_shops(session, limit=20)
        items = [{"id": s.id, "name": s.name, "rating": float(s.rating or 0)} for s in shops]
    if not items:
        await call.message.edit_text("😔 Пока нет активных магазинов.", reply_markup=kb.client_back())
        return
    await call.message.edit_text(
        f"🏪 <b>Магазины ({len(items)})</b>\nВыберите:",
        reply_markup=kb.client_shops(items, 0)
    )
    await call.answer()


@router.message(F.location)
async def got_location(message: Message):
    async with async_session() as session:
        client = await get_or_create_client(session, message.from_user.id)
        client.lat = message.location.latitude
        client.lon = message.location.longitude
        await session.commit()

        shops = await geo_service.find_nearby_shops(
            session, message.location.latitude, message.location.longitude
        )

    if not shops:
        await message.answer("😔 Рядом нет магазинов. Попробуйте «Показать все».",
                             reply_markup=kb.client_geo())
        return

    items = [{"id": s["id"], "name": s["name"], "rating": s["rating"]} for s in shops]
    await message.answer(
        f"📍 <b>Ближайшие к вам ({len(items)})</b>",
        reply_markup=kb.client_shops(items, 0)
    )


@router.callback_query(F.data.startswith("shops_page_"))
async def shops_page(call: CallbackQuery):
    page = int(call.data.split("_")[-1])
    async with async_session() as session:
        shops = await geo_service.get_all_shops(session, limit=100)
    items = [{"id": s.id, "name": s.name, "rating": float(s.rating or 0)} for s in shops]
    start = page * 5
    page_items = items[start:start + 5]
    await call.message.edit_text(
        f"🏪 <b>Магазины (стр. {page + 1})</b>",
        reply_markup=kb.client_shops(page_items, page)
    )
    await call.answer()


# ═══════════════════════════════════════════
#   КАРТОЧКА МАГАЗИНА
# ═══════════════════════════════════════════
@router.callback_query(F.data.startswith("shop_") & ~F.data.startswith("shop_products_") & ~F.data.startswith("shop_hits_") & ~F.data.startswith("shop_reviews_") & ~F.data.startswith("shop_subscribe_"))
async def shop_card(call: CallbackQuery):
    shop_id = int(call.data.split("_")[1])
    async with async_session() as session:
        result = await session.execute(select(Shop).where(Shop.id == shop_id))
        shop = result.scalar_one_or_none()
    if not shop:
        await call.answer("Магазин не найден", show_alert=True)
        return
    text = (
        f"🏪 <b>{shop.name}</b>\n"
        f"⭐ {float(shop.rating or 0):.1f} ({shop.reviews_count})\n"
        f"📍 {shop.address or '—'}\n"
        f"🕒 8:00 – 22:00"
    )
    await call.message.edit_text(text, reply_markup=kb.shop_card(shop_id))
    await call.answer()


@router.callback_query(F.data.startswith("shop_products_"))
async def shop_products(call: CallbackQuery):
    shop_id = int(call.data.split("_")[2])
    async with async_session() as session:
        result = await session.execute(
            select(Product.category, Product.id)
            .where(Product.shop_id == shop_id, Product.is_active == True)
        )
        rows = result.all()

    # Группируем по категориям
    cats_count = {}
    for cat, _ in rows:
        cats_count[cat] = cats_count.get(cat, 0) + 1

    if not cats_count:
        await call.message.edit_text("😔 В магазине пока нет товаров.",
                                     reply_markup=kb.client_back(f"shop_{shop_id}"))
        return

    categories = []
    for key, count in cats_count.items():
        name = helpers.category_name(key)
        categories.append((key, name, count))

    await call.message.edit_text(
        "🗂 <b>Выберите категорию:</b>",
        reply_markup=kb.shop_categories(shop_id, categories)
    )
    await call.answer()


@router.callback_query(F.data.startswith("cat_"))
async def show_category(call: CallbackQuery):
    parts = call.data.split("_")
    shop_id = int(parts[1])
    category = parts[2]

    async with async_session() as session:
        q = select(Product).where(Product.shop_id == shop_id, Product.is_active == True)
        if category != "all":
            q = q.where(Product.category == category)
        result = await session.execute(q.limit(50))
        products = result.scalars().all()

    if not products:
        await call.answer("Пусто", show_alert=True)
        return

    items = [{
        "id": p.id,
        "title": p.title,
        "price": helpers.money(p.client_price),
    } for p in products[:5]]

    await call.message.edit_text(
        f"📦 <b>Товары ({len(products)})</b>",
        reply_markup=kb.products_list(shop_id, category, items, 0)
    )
    await call.answer()


@router.callback_query(F.data.startswith("prods_"))
async def prods_page(call: CallbackQuery):
    parts = call.data.split("_")
    shop_id = int(parts[1])
    category = parts[2]
    page = int(parts[3])

    async with async_session() as session:
        q = select(Product).where(Product.shop_id == shop_id, Product.is_active == True)
        if category != "all":
            q = q.where(Product.category == category)
        result = await session.execute(q.limit(100))
        products = result.scalars().all()

    start = page * 5
    page_items = products[start:start + 5]
    items = [{
        "id": p.id, "title": p.title, "price": helpers.money(p.client_price)
    } for p in page_items]

    await call.message.edit_text(
        f"📦 <b>Товары (стр. {page + 1})</b>",
        reply_markup=kb.products_list(shop_id, category, items, page)
    )
    await call.answer()


# ═══════════════════════════════════════════
#   КАРТОЧКА ТОВАРА
# ═══════════════════════════════════════════
@router.callback_query(F.data.startswith("product_"))
async def product_card(call: CallbackQuery):
    product_id = int(call.data.split("_")[1])
    async with async_session() as session:
        result = await session.execute(select(Product).where(Product.id == product_id))
        product = result.scalar_one_or_none()
        if not product:
            await call.answer("Товар не найден", show_alert=True)
            return

        client = await get_or_create_client(session, call.from_user.id)
        fav_result = await session.execute(
            select(Favorite).where(
                Favorite.client_id == client.id,
                Favorite.product_id == product_id,
            )
        )
        in_fav = fav_result.scalar_one_or_none() is not None

    text = (
        f"💐 <b>{product.title}</b>\n\n"
        f"📝 {product.description or '—'}\n\n"
        f"💰 <b>{helpers.money(product.client_price)}</b>"
    )
    if product.old_price:
        text += f"\n🔥 Старая: {helpers.money(product.old_price)}"

    if product.photo_id:
        await call.message.answer_photo(
            photo=product.photo_id,
            caption=text,
            reply_markup=kb.product_card(product_id, in_fav),
        )
        await call.message.delete()
    else:
        await call.message.edit_text(text, reply_markup=kb.product_card(product_id, in_fav))
    await call.answer()


@router.callback_query(F.data == "noop")
async def noop(call: CallbackQuery):
    await call.answer()


# ═══════════════════════════════════════════
#   КОРЗИНА
# ═══════════════════════════════════════════
@router.callback_query(F.data.startswith("cart_add_"))
async def cart_add(call: CallbackQuery):
    product_id = int(call.data.split("_")[2])
    async with async_session() as session:
        client = await get_or_create_client(session, call.from_user.id)
        p_result = await session.execute(select(Product).where(Product.id == product_id))
        product = p_result.scalar_one_or_none()
        if not product:
            await call.answer("Товар недоступен", show_alert=True)
            return

        # Проверка: не должно быть другого магазина в корзине
        cart_result = await session.execute(
            select(CartItem).where(CartItem.client_id == client.id)
        )
        cart_items = cart_result.scalars().all()

        if cart_items:
            other_shop = cart_items[0].shop_id
            if other_shop != product.shop_id:
                await call.answer(
                    "⚠️ В корзине уже есть товар из другого магазина. Очистите её сначала.",
                    show_alert=True
                )
                return

        # Проверка: уже есть этот товар?
        existing = next((ci for ci in cart_items if ci.product_id == product_id), None)
        if existing:
            existing.quantity += 1
        else:
            session.add(CartItem(
                client_id=client.id,
                product_id=product_id,
                shop_id=product.shop_id,
                quantity=1,
            ))
        await session.commit()

    await call.answer("✅ Добавлено в корзину", show_alert=False)


@router.callback_query(F.data.startswith("fav_toggle_"))
async def fav_toggle(call: CallbackQuery):
    product_id = int(call.data.split("_")[2])
    async with async_session() as session:
        client = await get_or_create_client(session, call.from_user.id)
        result = await session.execute(
            select(Favorite).where(
                Favorite.client_id == client.id,
                Favorite.product_id == product_id,
            )
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


@router.callback_query(F.data == "cart_view")
async def cart_view(call: CallbackQuery):
    async with async_session() as session:
        client = await get_or_create_client(session, call.from_user.id)
        result = await session.execute(
            select(CartItem, Product).join(Product, Product.id == CartItem.product_id)
            .where(CartItem.client_id == client.id)
        )
        rows = result.all()

    if not rows:
        await call.message.edit_text("🛒 Корзина пуста.", reply_markup=kb.cart_empty())
        await call.answer()
        return

    text = "🛒 <b>Ваша корзина</b>\n\n"
    total = Decimal("0")
    for ci, p in rows:
        line = Decimal(str(p.client_price)) * ci.quantity
        total += line
        text += f"• {p.title} × {ci.quantity} = {helpers.money(line)}\n"

    text += f"\n🚚 Доставка: {helpers.money(config.DELIVERY_PRICE)}\n"
    text += f"<b>Итого: {helpers.money(total + Decimal(str(config.DELIVERY_PRICE)))}</b>"

    await call.message.edit_text(text, reply_markup=kb.cart_view())
    await call.answer()


@router.callback_query(F.data == "cart_edit")
async def cart_edit(call: CallbackQuery):
    async with async_session() as session:
        client = await get_or_create_client(session, call.from_user.id)
        result = await session.execute(
            select(CartItem, Product).join(Product, Product.id == CartItem.product_id)
            .where(CartItem.client_id == client.id)
        )
        rows = result.all()

    items = [(ci.id, p.title, ci.quantity) for ci, p in rows]
    await call.message.edit_text("✏️ <b>Изменить количество:</b>",
                                 reply_markup=kb.cart_edit(items))
    await call.answer()


@router.callback_query(F.data.startswith("cart_plus_"))
async def cart_plus(call: CallbackQuery):
    item_id = int(call.data.split("_")[2])
    async with async_session() as session:
        result = await session.execute(select(CartItem).where(CartItem.id == item_id))
        ci = result.scalar_one_or_none()
        if ci:
            ci.quantity += 1
            await session.commit()
    await cart_edit(call)


@router.callback_query(F.data.startswith("cart_minus_"))
async def cart_minus(call: CallbackQuery):
    item_id = int(call.data.split("_")[2])
    async with async_session() as session:
        result = await session.execute(select(CartItem).where(CartItem.id == item_id))
        ci = result.scalar_one_or_none()
        if ci:
            if ci.quantity > 1:
                ci.quantity -= 1
                await session.commit()
            else:
                await session.delete(ci)
                await session.commit()
    await cart_edit(call)


@router.callback_query(F.data == "cart_remove_menu")
async def cart_remove_menu(call: CallbackQuery):
    async with async_session() as session:
        client = await get_or_create_client(session, call.from_user.id)
        result = await session.execute(
            select(CartItem, Product).join(Product, Product.id == CartItem.product_id)
            .where(CartItem.client_id == client.id)
        )
        rows = result.all()

    items = [(ci.id, p.title) for ci, p in rows]
    await call.message.edit_text("🗑 <b>Что удалить?</b>",
                                 reply_markup=kb.cart_remove_menu(items))
    await call.answer()


@router.callback_query(F.data.startswith("cart_del_"))
async def cart_del(call: CallbackQuery):
    item_id = int(call.data.split("_")[2])
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
    await call.message.edit_text("🗑 Корзина очищена.", reply_markup=kb.cart_empty())
    await call.answer()


# ═══════════════════════════════════════════
#   ОФОРМЛЕНИЕ ЗАКАЗА (FSM)
# ═══════════════════════════════════════════
@router.callback_query(F.data == "cart_checkout")
async def cart_checkout(call: CallbackQuery, state: FSMContext):
    async with async_session() as session:
        client = await get_or_create_client(session, call.from_user.id)
        result = await session.execute(
            select(ClientAddress).where(ClientAddress.client_id == client.id)
        )
        addresses = result.scalars().all()

    addr_items = [(a.id, a.title, a.address) for a in addresses]
    await state.set_state(OrderFSM.address)
    await call.message.edit_text(
        "📝 <b>Шаг 1 из 6:</b> Введите адрес доставки\n\n"
        "Или выберите сохранённый:",
        reply_markup=kb.order_addresses(addr_items)
    )
    await call.answer()


@router.callback_query(F.data == "order_cancel", OrderFSM)
async def order_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Оформление отменено.", reply_markup=kb.client_main())
    await call.answer()


@router.message(OrderFSM.address)
async def order_set_address(message: Message, state: FSMContext):
    await state.update_data(address=message.text)
    await state.set_state(OrderFSM.client_name)
    await message.answer(
        "📝 <b>Шаг 2 из 6:</b> Как зовут получателя?",
        reply_markup=kb.order_cancel()
    )


@router.message(OrderFSM.client_name)
async def order_set_name(message: Message, state: FSMContext):
    await state.update_data(client_name=message.text)
    await state.set_state(OrderFSM.client_phone)
    await message.answer(
        "📝 <b>Шаг 3 из 6:</b> Телефон получателя\n"
        "Формат: +79991234567",
        reply_markup=kb.order_cancel()
    )


@router.message(OrderFSM.client_phone)
async def order_set_phone(message: Message, state: FSMContext):
    if not helpers.is_valid_phone(message.text):
        await message.answer("❌ Неверный номер. Введите 10–15 цифр.")
        return
    await state.update_data(client_phone=helpers.clean_phone(message.text))
    await state.set_state(OrderFSM.date)
    await message.answer(
        "📝 <b>Шаг 4 из 6:</b> Когда доставить?",
        reply_markup=kb.order_date()
    )


@router.callback_query(F.data.startswith("order_date_"), OrderFSM.date)
async def order_set_date(call: CallbackQuery, state: FSMContext):
    from datetime import date, timedelta
    part = call.data.split("_")[-1]
    if part == "today":
        d = date.today()
    elif part == "tomorrow":
        d = date.today() + timedelta(days=1)
    else:
        d = date.today() + timedelta(days=2)
    await state.update_data(delivery_date=str(d))
    await state.set_state(OrderFSM.time_period)
    await call.message.edit_text(
        "📝 <b>Шаг 5 из 6:</b> Выберите период:",
        reply_markup=kb.order_time_period()
    )
    await call.answer()


@router.callback_query(F.data.startswith("order_period_"), OrderFSM.time_period)
async def order_set_period(call: CallbackQuery, state: FSMContext):
    period = call.data.split("_")[-1]
    await state.set_state(OrderFSM.time_slot)
    await call.message.edit_text(
        f"🕒 Выберите время:",
        reply_markup=kb.order_time_slot(period)
    )
    await call.answer()


@router.callback_query(F.data == "order_time_back", OrderFSM.time_slot)
async def order_time_back(call: CallbackQuery, state: FSMContext):
    await state.set_state(OrderFSM.time_period)
    await call.message.edit_text(
        "📝 Выберите период:",
        reply_markup=kb.order_time_period()
    )
    await call.answer()


@router.callback_query(F.data.startswith("order_slot_"), OrderFSM.time_slot)
async def order_set_slot(call: CallbackQuery, state: FSMContext):
    parts = call.data.split("_")
    slot = parts[-1]
    await state.update_data(delivery_slot=slot)
    await state.set_state(OrderFSM.promo)
    await call.message.edit_text(
        "🎁 <b>Шаг 6 из 6:</b> Есть промокод?\n"
        "Введите код или пропустите.",
        reply_markup=kb.order_promo()
    )
    await call.answer()


@router.message(OrderFSM.promo)
async def order_set_promo(message: Message, state: FSMContext):
    await state.update_data(promo_code=message.text.strip().upper())
    await show_order_confirm(message, state)


@router.callback_query(F.data == "order_skip_promo", OrderFSM.promo)
async def order_skip_promo(call: CallbackQuery, state: FSMContext):
    await state.update_data(promo_code=None)
    await show_order_confirm(call.message, state, edit=True)
    await call.answer()


async def show_order_confirm(message: Message, state: FSMContext, edit: bool = False):
    data = await state.get_data()
    async with async_session() as session:
        client = await get_or_create_client(session, message.chat.id)
        result = await session.execute(
            select(CartItem, Product).join(Product, Product.id == CartItem.product_id)
            .where(CartItem.client_id == client.id)
        )
        rows = result.all()

    text = "🧾 <b>Проверьте заказ</b>\n\n"
    total = Decimal("0")
    for ci, p in rows:
        line = Decimal(str(p.client_price)) * ci.quantity
        total += line
        text += f"• {p.title} × {ci.quantity} = {helpers.money(line)}\n"

    total += Decimal(str(config.DELIVERY_PRICE))
    text += f"\n🚚 Доставка: {helpers.money(config.DELIVERY_PRICE)}"
    if data.get("promo_code"):
        text += f"\n🎁 Промокод: {data['promo_code']}"
    text += f"\n\n📍 {data.get('address')}\n👤 {data.get('client_name')}\n📞 {data.get('client_phone')}"
    text += f"\n📅 {data.get('delivery_date')} | 🕒 {data.get('delivery_slot')}"
    text += f"\n\n<b>Итого: {helpers.money(total)}</b>"

    await state.set_state(OrderFSM.confirm)
    if edit:
        await message.edit_text(text, reply_markup=kb.order_confirm())
    else:
        await message.answer(text, reply_markup=kb.order_confirm())


@router.callback_query(F.data == "order_pay", OrderFSM.confirm)
async def order_pay(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    text = (
        f"💳 <b>Оплата заказа</b>\n\n"
        f"Переведите сумму на карту:\n"
        f"<code>{config.CARD_NUMBER}</code>\n"
        f"Получатель: {config.CARD_HOLDER}\n"
        f"Банк: {config.BANK_NAME}\n\n"
        f"⚠️ <b>В комментарии укажите ваш Telegram ID:</b>\n"
        f"<code>{call.from_user.id}</code>\n\n"
        f"После оплаты нажмите «Я оплатил»."
    )
    await state.set_state(OrderFSM.payment)
    await call.message.edit_text(text, reply_markup=kb.order_payment())
    await call.answer()


@router.callback_query(F.data == "order_paid", OrderFSM.payment)
async def order_paid(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    async with async_session() as session:
        client = await get_or_create_client(session, call.from_user.id)

        order = await orders_service.create_order_from_cart(
            session=session,
            client_id=client.id,
            address=data.get("address"),
            client_name=data.get("client_name"),
            client_phone=data.get("client_phone"),
            delivery_date=__import__("datetime").date.fromisoformat(data.get("delivery_date")),
            delivery_slot=data.get("delivery_slot"),
            promo_code=data.get("promo_code"),
        )

    await state.clear()
    if not order:
        await call.message.edit_text("❌ Не удалось создать заказ. Обратитесь в поддержку.",
                                     reply_markup=kb.client_main())
        await call.answer()
        return

    await call.message.edit_text(
        f"✅ <b>Заказ #{order.id} создан!</b>\n\n"
        f"💳 Ожидаем подтверждения оплаты администратором.\n"
        f"Как только оплата поступит — заказ уйдёт магазину.",
        reply_markup=kb.client_main()
    )
    await call.answer()


# ═══════════════════════════════════════════
#   МОИ ЗАКАЗЫ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "client_orders")
async def my_orders(call: CallbackQuery):
    async with async_session() as session:
        client = await get_or_create_client(session, call.from_user.id)
        orders = await orders_service.get_client_orders(session, client.id)

    if not orders:
        await call.message.edit_text("📦 У вас пока нет заказов.",
                                     reply_markup=kb.client_back())
        await call.answer()
        return

    text = f"📦 <b>Мои заказы ({len(orders)})</b>\n\n"
    for o in orders[:10]:
        em = helpers.status_emoji(o.status)
        st = helpers.status_text(o.status)
        text += f"{em} #{o.id} — {st} — {helpers.money(o.total_price)}\n"

    await call.message.edit_text(text, reply_markup=kb.client_back())
    await call.answer()


# ═══════════════════════════════════════════
#   ИЗБРАННОЕ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "client_favorites")
async def favorites(call: CallbackQuery):
    async with async_session() as session:
        client = await get_or_create_client(session, call.from_user.id)
        result = await session.execute(
            select(Product).join(Favorite, Favorite.product_id == Product.id)
            .where(Favorite.client_id == client.id)
        )
        products = result.scalars().all()

    if not products:
        await call.message.edit_text("❤️ В избранном пусто.", reply_markup=kb.client_back())
        await call.answer()
        return

    items = [{"id": p.id, "title": p.title} for p in products]
    await call.message.edit_text(
        f"❤️ <b>Избранное ({len(items)})</b>",
        reply_markup=kb.favorites_list(items)
    )
    await call.answer()


# ═══════════════════════════════════════════
#   БАЛАНС
# ═══════════════════════════════════════════
@router.callback_query(F.data == "client_balance")
async def balance(call: CallbackQuery):
    async with async_session() as session:
        client = await get_or_create_client(session, call.from_user.id)
        txs = await payments_service.get_user_transactions(session, "client", client.id, 5)

    text = f"💰 <b>Мой баланс: {helpers.money(client.balance)}</b>\n\n"
    if txs:
        text += "Последние операции:\n"
        for t in txs:
            sign = "+" if float(t.amount) >= 0 else ""
            text += f"{sign}{helpers.money(t.amount)} — {t.type}\n"

    await call.message.edit_text(text, reply_markup=kb.client_balance())
    await call.answer()


# ═══════════════════════════════════════════
#   ПОДДЕРЖКА
# ═══════════════════════════════════════════
@router.callback_query(F.data == "client_support")
async def support(call: CallbackQuery):
    await call.message.edit_text(
        f"🆘 <b>Поддержка</b>\n\n"
        f"Напишите ваш вопрос — мы ответим.\n"
        f"Или свяжитесь: {config.SUPPORT_TG}",
        reply_markup=kb.client_back()
    )
    await call.answer()
