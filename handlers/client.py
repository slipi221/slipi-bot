# -*- coding: utf-8 -*-
"""
SLIPI — бот клиента
"""
from datetime import date, datetime, timedelta
from decimal import Decimal

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
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
)
from services import orders as orders_service
from services import geo as geo_service
from services import payments as payments_service
from utils import helpers
from bots import bot_admin

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
        reply_markup=kb.client_back()
    )
    await call.answer()

# ═══════════════════════════════════════════
#   КАТАЛОГ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "client_catalog")
async def catalog(call: CallbackQuery):
    await call.message.edit_text(
        "📍 Чтобы показать ближайшие магазины, поделитесь геолокацией.",
        reply_markup=kb.client_geo()
    )
    await call.answer()

@router.callback_query(F.data == "client_all_shops")
async def all_shops(call: CallbackQuery):
    async with async_session() as session:
        shops = await geo_service.get_all_shops(session, limit=20)
        items = [{"id": s.id, "name": s.name, "rating": float(s.rating or 0)} for s in shops]
    if not items:
        await call.message.edit_text("😔 Пока нет активных магазинов.", reply_markup=kb.client_back())
        await call.answer()
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
        shops = await geo_service.find_nearby_shops(session, message.location.latitude, message.location.longitude)

    if not shops:
        await message.answer("😔 Рядом нет магазинов. Попробуйте «Показать все».", reply_markup=kb.client_geo())
        return

    items = [{"id": s["id"], "name": s["name"], "rating": s["rating"]} for s in shops]
    await message.answer(f"📍 <b>Ближайшие к вам ({len(items)})</b>", reply_markup=kb.client_shops(items, 0))

@router.callback_query(F.data.startswith("shops_page_"))
async def shops_page(call: CallbackQuery):
    page = int(call.data.split("_")[-1])
    async with async_session() as session:
        shops = await geo_service.get_all_shops(session, limit=100)
    items = [{"id": s.id, "name": s.name, "rating": float(s.rating or 0)} for s in shops]
    page_items = items[page * 5:(page * 5) + 5]
    await call.message.edit_text(f"🏪 <b>Магазины (стр. {page + 1})</b>", reply_markup=kb.client_shops(page_items, page))
    await call.answer()

# ═══════════════════════════════════════════
#   КАРТОЧКА МАГАЗИНА И ТОВАРЫ
# ═══════════════════════════════════════════
@router.callback_query(F.data.startswith("shop_") & ~F.data.startswith("shop_products_") & ~F.data.startswith("shop_hits_") & ~F.data.startswith("shop_reviews_") & ~F.data.startswith("shop_call_") & ~F.data.startswith("shop_subscribe_"))
async def shop_card(call: CallbackQuery):
    try: shop_id = int(call.data.split("_")[1])
    except (IndexError, ValueError): return

    async with async_session() as session:
        result = await session.execute(select(Shop).where(Shop.id == shop_id))
        shop = result.scalar_one_or_none()
        if not shop: return

        client = await get_or_create_client(session, call.from_user.id)
        sub_result = await session.execute(select(ShopSubscription).where(ShopSubscription.client_id == client.id, ShopSubscription.shop_id == shop_id))
        is_subscribed = sub_result.scalar_one_or_none() is not None

    text = f"🏪 <b>{shop.name}</b>\n⭐ {float(shop.rating or 0):.1f} ({shop.reviews_count})\n📍 {shop.address or '—'}\n🕒 {shop.work_start} – {shop.work_end}"
    await call.message.edit_text(text, reply_markup=kb.shop_card(shop_id, is_subscribed))
    await call.answer()

@router.callback_query(F.data.startswith("shop_subscribe_"))
async def shop_subscribe(call: CallbackQuery):
    shop_id = int(call.data.split("_")[2])
    async with async_session() as session:
        client = await get_or_create_client(session, call.from_user.id)
        result = await session.execute(select(ShopSubscription).where(ShopSubscription.client_id == client.id, ShopSubscription.shop_id == shop_id))
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

@router.callback_query(F.data.startswith("shop_products_"))
async def shop_products(call: CallbackQuery):
    shop_id = int(call.data.split("_")[2])
    async with async_session() as session:
        result = await session.execute(select(Product.category, Product.id).where(Product.shop_id == shop_id, Product.is_active == True, Product.is_draft == False))
        rows = result.all()

    cats_count = {}
    for cat, _ in rows: cats_count[cat] = cats_count.get(cat, 0) + 1
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
        if category != "all": q = q.where(Product.category == category)
        result = await session.execute(q.limit(50))
        products = result.scalars().all()

    if not products:
        await call.answer("Пусто", show_alert=True)
        return

    items = [{"id": p.id, "title": p.title, "price": helpers.money(p.client_price)} for p in products[:5]]
    await call.message.edit_text(f"📦 <b>Товары ({len(products)})</b>", reply_markup=kb.products_list(shop_id, category, items, 0))
    await call.answer()

@router.callback_query(F.data.startswith("prods_"))
async def prods_page(call: CallbackQuery):
    parts = call.data.split("_")
    shop_id, category, page = int(parts[1]), parts[2], int(parts[3])

    async with async_session() as session:
        q = select(Product).where(Product.shop_id == shop_id, Product.is_active == True, Product.is_draft == False)
        if category != "all": q = q.where(Product.category == category)
        result = await session.execute(q.limit(100))
        products = result.scalars().all()

    page_items = products[page * 5:(page * 5) + 5]
    items = [{"id": p.id, "title": p.title, "price": helpers.money(p.client_price)} for p in page_items]
    await call.message.edit_text(f"📦 <b>Товары (стр. {page + 1})</b>", reply_markup=kb.products_list(shop_id, category, items, page))
    await call.answer()

@router.callback_query(F.data.startswith("product_"))
async def product_card(call: CallbackQuery):
    try: product_id = int(call.data.split("_")[1])
    except (IndexError, ValueError): return

    async with async_session() as session:
        result = await session.execute(select(Product).where(Product.id == product_id))
        product = result.scalar_one_or_none()
        if not product: return

        client = await get_or_create_client(session, call.from_user.id)
        fav_result = await session.execute(select(Favorite).where(Favorite.client_id == client.id, Favorite.product_id == product_id))
        in_fav = fav_result.scalar_one_or_none() is not None

    text = f"💐 <b>{product.title}</b>\n\n📝 {product.description or '—'}\n\n💰 <b>{helpers.money(product.client_price)}</b>"
    markup = kb.product_card(product_id, in_fav)

    # ИСПРАВЛЕНО (Баг #12): Защита от падения при редактировании сообщения с фото
    try:
        await call.message.delete() # Удаляем старое сообщение (текст или фото)
    except TelegramBadRequest:
        pass

    if product.photo_id:
        await call.message.answer_photo(photo=product.photo_id, caption=text, reply_markup=markup)
    else:
        await call.message.answer(text, reply_markup=markup)
    await call.answer()

@router.callback_query(F.data.startswith("fav_toggle_"))
async def fav_toggle(call: CallbackQuery):
    product_id = int(call.data.split("_")[2])
    async with async_session() as session:
        client = await get_or_create_client(session, call.from_user.id)
        result = await session.execute(select(Favorite).where(Favorite.client_id == client.id, Favorite.product_id == product_id))
        fav = result.scalar_one_or_none()
        if fav:
            await session.delete(fav)
            await session.commit()
            await call.answer("💔 Удалено")
        else:
            session.add(Favorite(client_id=client.id, product_id=product_id))
            await session.commit()
            await call.answer("❤️ Добавлено")

# ═══════════════════════════════════════════
#   КОРЗИНА
# ═══════════════════════════════════════════
@router.callback_query(F.data == "client_cart")
async def open_cart(call: CallbackQuery):
    await cart_view(call)

@router.callback_query(F.data.startswith("cart_add_"))
async def cart_add(call: CallbackQuery):
    product_id = int(call.data.split("_")[2])
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
        if existing: existing.quantity += 1
        else: session.add(CartItem(client_id=client.id, product_id=product_id, shop_id=product.shop_id, quantity=1))
        await session.commit()

    await call.answer("✅ Добавлено в корзину")

@router.callback_query(F.data == "cart_view")
async def cart_view(call: CallbackQuery):
    async with async_session() as session:
        client = await get_or_create_client(session, call.from_user.id)
        result = await session.execute(select(CartItem, Product).join(Product, Product.id == CartItem.product_id).where(CartItem.client_id == client.id))
        rows = result.all()

    if not rows:
        await call.message.edit_text("🛒 Корзина пуста.", reply_markup=kb.cart_empty())
        return

    text = "🛒 <b>Ваша корзина</b>\n\n"
    total = Decimal("0")
    for ci, p in rows:
        line = Decimal(str(p.client_price)) * ci.quantity
        total += line
        text += f"• {p.title} × {ci.quantity} = {helpers.money(line)}\n"

    text += f"\n🚚 Доставка рассчитывается по адресу"
    text += f"\n<b>Итого (без доставки): {helpers.money(total)}</b>"
    await call.message.edit_text(text, reply_markup=kb.cart_view())
    await call.answer()

@router.callback_query(F.data == "cart_edit")
async def cart_edit(call: CallbackQuery):
    async with async_session() as session:
        client = await get_or_create_client(session, call.from_user.id)
        result = await session.execute(select(CartItem, Product).join(Product, Product.id == CartItem.product_id).where(CartItem.client_id == client.id))
        rows = result.all()

    items = [(ci.id, p.title, ci.quantity) for ci, p in rows]
    await call.message.edit_text("✏️ <b>Изменить количество:</b>", reply_markup=kb.cart_edit(items))
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
            if ci.quantity > 1: ci.quantity -= 1
            else: await session.delete(ci)
            await session.commit()
    await cart_edit(call)

@router.callback_query(F.data == "cart_remove_menu")
async def cart_remove_menu(call: CallbackQuery):
    async with async_session() as session:
        client = await get_or_create_client(session, call.from_user.id)
        result = await session.execute(select(CartItem, Product).join(Product, Product.id == CartItem.product_id).where(CartItem.client_id == client.id))
        rows = result.all()

    items = [(ci.id, p.title) for ci, p in rows]
    await call.message.edit_text("🗑 <b>Что удалить?</b>", reply_markup=kb.cart_remove_menu(items))
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

# ═══════════════════════════════════════════
#   ОФОРМЛЕНИЕ ЗАКАЗА
# ═══════════════════════════════════════════
@router.callback_query(F.data == "cart_checkout")
async def cart_checkout(call: CallbackQuery, state: FSMContext):
    async with async_session() as session:
        client = await get_or_create_client(session, call.from_user.id)
        result = await session.execute(select(ClientAddress).where(ClientAddress.client_id == client.id))
        addresses = result.scalars().all()

    addr_items = [(a.id, a.title, a.address) for a in addresses]
    await state.set_state(OrderFSM.address)
    await call.message.edit_text("📝 <b>Шаг 1 из 8:</b> Введите адрес доставки\n\nИли выберите сохранённый:", reply_markup=kb.order_addresses(addr_items))
    await call.answer()

@router.callback_query(F.data == "order_cancel", OrderFSM)
async def order_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Оформление отменено.", reply_markup=kb.client_main())
    await call.answer()

@router.callback_query(F.data == "order_new_addr", OrderFSM.address)
async def order_new_addr(call: CallbackQuery, state: FSMContext):
    # ИСПРАВЛЕНО (Баг #9): Кнопка нового адреса теперь просто просит ввести текст
    await call.message.edit_text("📝 Введите адрес текстом:", reply_markup=kb.order_cancel())
    await call.answer()

@router.callback_query(F.data.startswith("order_addr_"), OrderFSM.address)
async def order_use_addr(call: CallbackQuery, state: FSMContext):
    addr_id = int(call.data.split("_")[2])
    async with async_session() as session:
        result = await session.execute(select(ClientAddress).where(ClientAddress.id == addr_id))
        addr = result.scalar_one_or_none()
    if not addr:
        await call.answer("Не найдено", show_alert=True)
        return

    await state.update_data(address=addr.address)
    await state.set_state(OrderFSM.client_name)
    await call.message.edit_text("📝 <b>Шаг 2 из 8:</b> Как зовут получателя?", reply_markup=kb.order_cancel())
    await call.answer()

@router.message(OrderFSM.address)
async def order_set_address(message: Message, state: FSMContext):
    address = message.text.strip()
    async with async_session() as session:
        client = await get_or_create_client(session, message.from_user.id)
        cart_result = await session.execute(select(CartItem).where(CartItem.client_id == client.id).limit(1))
        cart_item = cart_result.scalar_one_or_none()
        shop = None
        if cart_item:
            shop_r = await session.execute(select(Shop).where(Shop.id == cart_item.shop_id))
            shop = shop_r.scalar_one_or_none()

    distance_km = 0
    if shop and shop.lat and shop.lon and client.lat and client.lon:
        distance_km = helpers.distance_km(float(shop.lat), float(shop.lon), float(client.lat), float(client.lon))

    if distance_km > config.MAX_DELIVERY_RADIUS:
        await message.answer(f"🌷 <b>Извините, мы не можем доставить сюда букет.</b>\nЭтот адрес дальше {config.MAX_DELIVERY_RADIUS} км от магазинов.\n📍 Попробуйте другой адрес.\n📞 Поддержка: {config.SUPPORT_TG}", reply_markup=kb.client_main())
        await state.clear()
        return

    await state.update_data(address=address, distance_km=distance_km)
    await state.set_state(OrderFSM.save_address)
    await message.answer("💾 <b>Сохранить этот адрес?</b>", reply_markup=kb.order_save_address())

@router.callback_query(F.data.startswith("save_addr_") & ~F.data.startswith("save_addr_custom") & ~F.data.startswith("save_addr_no"), OrderFSM.save_address)
async def order_save_addr(call: CallbackQuery, state: FSMContext):
    title = call.data.replace("save_addr_", "")
    data = await state.get_data()
    async with async_session() as session:
        client = await get_or_create_client(session, call.from_user.id)
        session.add(ClientAddress(client_id=client.id, title=title, address=data["address"]))
        await session.commit()

    await state.set_state(OrderFSM.client_name)
    await call.message.edit_text(f"✅ Адрес сохранён как «{title}».\n\n📝 <b>Шаг 2 из 8:</b> Как зовут получателя?", reply_markup=kb.order_cancel())
    await call.answer()

@router.callback_query(F.data == "save_addr_custom", OrderFSM.save_address)
async def order_save_custom(call: CallbackQuery, state: FSMContext):
    await state.set_state(OrderFSM.address_title)
    await call.message.edit_text("✏️ Введите название адреса:", reply_markup=kb.order_cancel())
    await call.answer()

@router.message(OrderFSM.address_title)
async def order_save_custom_title(message: Message, state: FSMContext):
    title = message.text.strip()[:50]
    data = await state.get_data()
    async with async_session() as session:
        client = await get_or_create_client(session, message.from_user.id)
        session.add(ClientAddress(client_id=client.id, title=title, address=data["address"]))
        await session.commit()

    await state.set_state(OrderFSM.client_name)
    await message.answer(f"✅ Адрес сохранён как «{title}».\n\n📝 <b>Шаг 2 из 8:</b> Как зовут получателя?", reply_markup=kb.order_cancel())

@router.callback_query(F.data == "save_addr_no", OrderFSM.save_address)
async def order_save_no(call: CallbackQuery, state: FSMContext):
    await state.set_state(OrderFSM.client_name)
    await call.message.edit_text("📝 <b>Шаг 2 из 8:</b> Как зовут получателя?", reply_markup=kb.order_cancel())
    await call.answer()

@router.message(OrderFSM.client_name)
async def order_set_name(message: Message, state: FSMContext):
    await state.update_data(client_name=message.text.strip())
    await state.set_state(OrderFSM.client_phone)
    await message.answer("📝 <b>Шаг 3 из 8:</b> Телефон получателя\nФормат: +79991234567", reply_markup=kb.order_cancel())

@router.message(OrderFSM.client_phone)
async def order_set_phone(message: Message, state: FSMContext):
    if not helpers.is_valid_phone(message.text):
        await message.answer("❌ Неверный номер.")
        return
    await state.update_data(client_phone=helpers.clean_phone(message.text))
    await state.set_state(OrderFSM.date)
    await message.answer("📝 <b>Шаг 4 из 8:</b> Когда доставить?", reply_markup=kb.order_date())

@router.callback_query(F.data.startswith("order_date_"), OrderFSM.date)
async def order_set_date(call: CallbackQuery, state: FSMContext):
    part = call.data.split("_")[-1]
    if part == "today": d = date.today()
    elif part == "tomorrow": d = date.today() + timedelta(days=1)
    else: d = date.today() + timedelta(days=2)
    await state.update_data(delivery_date=str(d))
    await state.set_state(OrderFSM.time_period)
    await call.message.edit_text("📝 <b>Шаг 5 из 8:</b> Выберите период:", reply_markup=kb.order_time_period())
    await call.answer()

@router.callback_query(F.data.startswith("order_period_"), OrderFSM.time_period)
async def order_set_period(call: CallbackQuery, state: FSMContext):
    period = call.data.split("_")[-1]
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
    await call.message.edit_text("🎁 <b>Шаг 6 из 8:</b> Есть промокод?\nВведите код или пропустите.", reply_markup=kb.order_promo())
    await call.answer()

@router.message(OrderFSM.promo)
async def order_set_promo(message: Message, state: FSMContext):
    await state.update_data(promo_code=message.text.strip().upper())
    await order_ask_photo(message, state)

@router.callback_query(F.data == "order_skip_promo", OrderFSM.promo)
async def order_skip_promo(call: CallbackQuery, state: FSMContext):
    await state.update_data(promo_code=None)
    await order_ask_photo(call.message, state, edit=True)
    await call.answer()

async def order_ask_photo(message: Message, state: FSMContext, edit: bool = False):
    await state.set_state(OrderFSM.delivery_photo)
    text = "📸 <b>Шаг 7 из 8: Фото вручения</b>\n\nНужно ли курьеру сфотографировать момент передачи букета?"
    if edit: await message.edit_text(text, reply_markup=kb.order_delivery_photo())
    else: await message.answer(text, reply_markup=kb.order_delivery_photo())

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

# ФУНКЦИЯ ПОДСЧЕТА ИТОГА (С УЧЕТОМ СКИДКИ)
async def get_cart_totals(session, client_id: int, distance_km: float):
    result = await session.execute(select(CartItem, Product).join(Product, Product.id == CartItem.product_id).where(CartItem.client_id == client_id))
    rows = result.all()
    
    items = [{"product": p, "quantity": ci.quantity} for ci, p in rows]
    totals = orders_service.calculate_cart_total(items, distance_km)
    return rows, totals

async def show_order_confirm(message: Message, state: FSMContext, edit: bool = False):
    data = await state.get_data()
    distance_km = float(data.get("distance_km", 0))

    async with async_session() as session:
        client = await get_or_create_client(session, message.chat.id)
        rows, totals = await get_cart_totals(session, client.id, distance_km)

    text = "🧾 <b>Проверьте заказ</b>\n\n"
    for ci, p in rows:
        text += f"• {p.title} × {ci.quantity} = {helpers.money(Decimal(str(p.client_price)) * ci.quantity)}\n"

    if totals["discount"] > 0:
        text += f"\n🎁 Скидка 3%: -{helpers.money(totals['discount'])}"
    text += f"\n🚚 Доставка: {helpers.money(totals['delivery'])}"
    if data.get("promo_code"):
        text += f"\n🏷 Промокод: {data['promo_code']}"
    
    text += f"\n\n📍 {data.get('address')}\n👤 {data.get('client_name')}\n📞 {data.get('client_phone')}"
    text += f"\n📅 {data.get('delivery_date')} | 🕒 {data.get('delivery_slot')}"
    text += f"\n📸 Фото вручения: {'Да' if data.get('need_photo') else 'Нет'}"
    
    # ВАЖНО: Показываем итоговую сумму со скидкой (Баг #5)
    text += f"\n\n<b>Итого: {helpers.money(totals['total'])}</b>"

    await state.set_state(OrderFSM.confirm)
    if edit: await message.edit_text(text, reply_markup=kb.order_confirm())
    else: await message.answer(text, reply_markup=kb.order_confirm())

@router.callback_query(F.data == "order_edit", OrderFSM.confirm)
async def order_edit(call: CallbackQuery, state: FSMContext):
    # ИСПРАВЛЕНО (Баг #10): Возвращаем в начало оформления
    await state.set_state(OrderFSM.address)
    await call.message.edit_text("📝 <b>Шаг 1 из 8:</b> Введите адрес доставки заново или выберите сохраненный:", reply_markup=kb.order_cancel())
    await call.answer()

@router.callback_query(F.data == "order_pay", OrderFSM.confirm)
async def order_pay(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    distance_km = float(data.get("distance_km", 0))

    async with async_session() as session:
        client = await get_or_create_client(session, call.from_user.id)
        rows, totals = await get_cart_totals(session, client.id, distance_km)

    text = (
        f"💳 <b>Оплата заказа</b>\n\n"
        f"Сумма: <b>{helpers.money(totals['total'])}</b>\n\n"
        f"Переведите на карту:\n<code>{config.CARD_NUMBER}</code>\n"
        f"Получатель: {config.CARD_HOLDER}\nБанк: {config.BANK_NAME}\n\n"
        f"📝 <b>В комментарии укажите номер заказа (придёт ниже).</b>\n\n"
        f"После оплаты нажмите «✅ Я оплатил»."
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
            session=session, client_id=client.id,
            address=data.get("address"), client_name=data.get("client_name"), client_phone=data.get("client_phone"),
            delivery_date=date.fromisoformat(data.get("delivery_date")), delivery_slot=data.get("delivery_slot"),
            promo_code=data.get("promo_code"), need_photo=data.get("need_photo", True), distance_km=float(data.get("distance_km", 0)),
        )

    await state.clear()
    if not order:
        await call.message.edit_text("❌ Не удалось создать заказ.", reply_markup=kb.client_main())
        return

    await call.message.edit_text(
        f"✅ <b>Заказ #{order.id} создан!</b>\n\n💳 В комментарии укажите: <code>{order.id}</code>\n\nОжидаем подтверждения оплаты.",
        reply_markup=kb.client_main()
    )

    try:
        # Отправляем админу с кнопками (Баг #14)
        await bot_admin.send_message(
            config.ADMIN_ID,
            f"💳 <b>Новый платёж!</b>\n\n📦 Заказ #{order.id}\n💰 Сумма: {helpers.money(order.total_price)}",
            reply_markup=kb.admin_confirm_payment(order.id)
        )
    except Exception: pass
    await call.answer()
