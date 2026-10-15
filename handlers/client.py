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

from sqlalchemy import select, delete, update

import config
import keyboards as kb
from states import OrderFSM, ClientFSM
from database import async_session
from models import (
    Client, Shop, Product, CartItem, Favorite, Order,
    ClientAddress, ClientEvent, Courier, ChatMessage,
)
from services import orders as orders_service
from services import geo as geo_service
from services import payments as payments_service
from utils import helpers

from bots import bot_client, bot_shop, bot_courier, bot_admin

router = Router(name="client")


# ═══════════════════════════════════════════
#   ХЕЛПЕР
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


@router.callback_query(F.data == "client_support")
async def support(call: CallbackQuery):
    await call.message.edit_text(
        f"🆘 <b>Поддержка</b>\n\n"
        f"Напишите ваш вопрос — мы ответим.\n"
        f"Или свяжитесь: {config.SUPPORT_TG}\n"
        f"📞 {config.SUPPORT_PHONE}",
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
        await message.answer(
            "😔 Рядом нет магазинов. Попробуйте «Показать все».",
            reply_markup=kb.client_geo()
        )
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
@router.callback_query(F.data.startswith("shop_")
                     & ~F.data.startswith("shop_products_")
                     & ~F.data.startswith("shop_hits_")
                     & ~F.data.startswith("shop_reviews_")
                     & ~F.data.startswith("shop_call_"))
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
        f"🕒 {shop.work_start} – {shop.work_end}"
    )
    await call.message.edit_text(text, reply_markup=kb.shop_card(shop_id))
    await call.answer()


@router.callback_query(F.data.startswith("shop_call_"))
async def shop_call(call: CallbackQuery):
    shop_id = int(call.data.split("_")[2])
    async with async_session() as session:
        result = await session.execute(select(Shop).where(Shop.id == shop_id))
        shop = result.scalar_one_or_none()
    if shop and shop.phone:
        await call.message.answer(f"📞 Телефон магазина: <code>{shop.phone}</code>")
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

    cats_count = {}
    for cat, _ in rows:
        cats_count[cat] = cats_count.get(cat, 0) + 1

    if not cats_count:
        await call.message.edit_text(
            "😔 В магазине пока нет товаров.",
            reply_markup=kb.client_back(f"shop_{shop_id}")
        )
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

    items = [{"id": p.id, "title": p.title, "price": helpers.money(p.client_price)}
             for p in products[:5]]

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
    items = [{"id": p.id, "title": p.title, "price": helpers.money(p.client_price)}
             for p in page_items]

    await call.message.edit_text(
        f"📦 <b>Товары (стр. {page + 1})</b>",
        reply_markup=kb.products_list(shop_id, category, items, page)
    )
    await call.answer()


@router.callback_query(F.data.startswith("shop_hits_"))
async def shop_hits(call: CallbackQuery):
    shop_id = int(call.data.split("_")[2])
    async with async_session() as session:
        result = await session.execute(
            select(Product).where(
                Product.shop_id == shop_id,
                Product.is_active == True,
                Product.order_count >= 5,
            ).order_by(Product.order_count.desc()).limit(5)
        )
        products = result.scalars().all()

    if not products:
        await call.answer("Хитов пока нет", show_alert=True)
        return

    items = [{"id": p.id, "title": p.title, "price": helpers.money(p.client_price)}
             for p in products]
    await call.message.edit_text(
        f"🔥 <b>Хиты продаж ({len(items)})</b>",
        reply_markup=kb.products_list(shop_id, "hits", items, 0)
    )
    await call.answer()


@router.callback_query(F.data.startswith("shop_reviews_"))
async def shop_reviews(call: CallbackQuery):
    shop_id = int(call.data.split("_")[2])
    from models import Review
    async with async_session() as session:
        result = await session.execute(
            select(Review).where(
                Review.target_type == "shop",
                Review.target_id == shop_id,
            ).order_by(Review.id.desc()).limit(5)
        )
        reviews = result.scalars().all()

    if not reviews:
        await call.message.edit_text(
            "⭐ <b>Отзывов пока нет.</b>",
            reply_markup=kb.client_back(f"shop_{shop_id}")
        )
        return

    text = "⭐ <b>Последние отзывы:</b>\n\n"
    for r in reviews:
        stars = "⭐" * r.rating
        text += f"{stars}\n"
        if r.comment:
            text += f"💬 {r.comment[:100]}\n"
        text += "\n"

    await call.message.edit_text(text, reply_markup=kb.client_back(f"shop_{shop_id}"))
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

    if product.photo_id:
        await call.message.answer_photo(
            photo=product.photo_id,
            caption=text,
            reply_markup=kb.product_card(product_id, in_fav),
        )
        try:
            await call.message.delete()
        except Exception:
            pass
    else:
        await call.message.edit_text(text, reply_markup=kb.product_card(product_id, in_fav))
    await call.answer()


@router.callback_query(F.data == "noop")
async def noop(call: CallbackQuery):
    await call.answer()


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

        cart_result = await session.execute(
            select(CartItem).where(CartItem.client_id == client.id)
        )
        cart_items = cart_result.scalars().all()

        if cart_items:
            other_shop = cart_items[0].shop_id
            if other_shop != product.shop_id:
                await call.answer(
                    "⚠️ В корзине уже есть товар из другого магазина.",
                    show_alert=True
                )
                return

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

    await call.answer("✅ Добавлено в корзину")


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

    text += f"\n🚚 Доставка рассчитывается по адресу"
    text += f"\n<b>Итого (без доставки): {helpers.money(total)}</b>"

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
#   ОФОРМЛЕНИЕ ЗАКАЗА
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
        "📝 <b>Шаг 1 из 8:</b> Введите адрес доставки\n\n"
        "Или выберите сохранённый:",
        reply_markup=kb.order_addresses(addr_items)
    )
    await call.answer()


@router.callback_query(F.data == "order_cancel", OrderFSM)
async def order_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Оформление отменено.", reply_markup=kb.client_main())
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
    await call.message.edit_text(
        "📝 <b>Шаг 2 из 8:</b> Как зовут получателя?",
        reply_markup=kb.order_cancel()
    )
    await call.answer()


@router.message(OrderFSM.address)
async def order_set_address(message: Message, state: FSMContext):
    address = message.text.strip()

    # Проверяем расстояние от магазина до клиента
    async with async_session() as session:
        client = await get_or_create_client(session, message.from_user.id)
        cart_result = await session.execute(
            select(CartItem).where(CartItem.client_id == client.id).limit(1)
        )
        cart_item = cart_result.scalar_one_or_none()

        shop = None
        if cart_item:
            shop_r = await session.execute(select(Shop).where(Shop.id == cart_item.shop_id))
            shop = shop_r.scalar_one_or_none()

    distance_km = 0
    if shop and shop.lat and shop.lon and client.lat and client.lon:
        distance_km = helpers.distance_km(
            float(shop.lat), float(shop.lon),
            float(client.lat), float(client.lon),
        )

    if distance_km > config.MAX_DELIVERY_RADIUS:
        await message.answer(
            "🌷 <b>Извините, мы не можем доставить сюда букет.</b>\n\n"
            f"Этот адрес <b>дальше {config.MAX_DELIVERY_RADIUS} км</b> от наших магазинов. "
            "Мы хотим, чтобы букет приехал к вам свежим и вовремя — а не уставшим в пути 🌸\n\n"
            "📍 Попробуйте <b>выбрать другой адрес</b>.\n"
            f"📞 Или напишите в поддержку: {config.SUPPORT_TG} — обязательно что-нибудь придумаем!",
            reply_markup=kb.client_main()
        )
        await state.clear()
        return

    await state.update_data(address=address, distance_km=distance_km)
    await state.set_state(OrderFSM.save_address)
    await message.answer(
        "💾 <b>Сохранить этот адрес?</b>",
        reply_markup=kb.order_save_address()
    )


@router.callback_query(F.data.startswith("save_addr_") & ~F.data.startswith("save_addr_custom") & ~F.data.startswith("save_addr_no"), OrderFSM.save_address)
async def order_save_addr(call: CallbackQuery, state: FSMContext):
    title = call.data.replace("save_addr_", "")
    data = await state.get_data()
    async with async_session() as session:
        client = await get_or_create_client(session, call.from_user.id)
        session.add(ClientAddress(
            client_id=client.id,
            title=title,
            address=data["address"],
        ))
        await session.commit()

    await state.set_state(OrderFSM.client_name)
    await call.message.edit_text(
        f"✅ Адрес сохранён как «{title}».\n\n"
        "📝 <b>Шаг 2 из 8:</b> Как зовут получателя?",
        reply_markup=kb.order_cancel()
    )
    await call.answer()


@router.callback_query(F.data == "save_addr_custom", OrderFSM.save_address)
async def order_save_custom(call: CallbackQuery, state: FSMContext):
    await state.set_state(OrderFSM.address_title)
    await call.message.edit_text(
        "✏️ Введите название адреса (Дом, Работа, Дача):",
        reply_markup=kb.order_cancel()
    )
    await call.answer()


@router.message(OrderFSM.address_title)
async def order_save_custom_title(message: Message, state: FSMContext):
    title = message.text.strip()[:50]
    data = await state.get_data()
    async with async_session() as session:
        client = await get_or_create_client(session, message.from_user.id)
        session.add(ClientAddress(
            client_id=client.id,
            title=title,
            address=data["address"],
        ))
        await session.commit()

    await state.set_state(OrderFSM.client_name)
    await message.answer(
        f"✅ Адрес сохранён как «{title}».\n\n"
        "📝 <b>Шаг 2 из 8:</b> Как зовут получателя?",
        reply_markup=kb.order_cancel()
    )


@router.callback_query(F.data == "save_addr_no", OrderFSM.save_address)
async def order_save_no(call: CallbackQuery, state: FSMContext):
    await state.set_state(OrderFSM.client_name)
    await call.message.edit_text(
        "📝 <b>Шаг 2 из 8:</b> Как зовут получателя?",
        reply_markup=kb.order_cancel()
    )
    await call.answer()


@router.message(OrderFSM.client_name)
async def order_set_name(message: Message, state: FSMContext):
    await state.update_data(client_name=message.text.strip())
    await state.set_state(OrderFSM.client_phone)
    await message.answer(
        "📝 <b>Шаг 3 из 8:</b> Телефон получателя\n"
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
        "📝 <b>Шаг 4 из 8:</b> Когда доставить?",
        reply_markup=kb.order_date()
    )


@router.callback_query(F.data.startswith("order_date_"), OrderFSM.date)
async def order_set_date(call: CallbackQuery, state: FSMContext):
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
        "📝 <b>Шаг 5 из 8:</b> Выберите период:",
        reply_markup=kb.order_time_period()
    )
    await call.answer()


@router.callback_query(F.data.startswith("order_period_"), OrderFSM.time_period)
async def order_set_period(call: CallbackQuery, state: FSMContext):
    period = call.data.split("_")[-1]
    await state.set_state(OrderFSM.time_slot)
    await call.message.edit_text(
        "🕒 Выберите время:",
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
        "🎁 <b>Шаг 6 из 8:</b> Есть промокод?\n"
        "Введите код или пропустите.",
        reply_markup=kb.order_promo()
    )
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
    text = (
        "📸 <b>Шаг 7 из 8: Фото вручения</b>\n\n"
        "Нужно ли курьеру сфотографировать момент передачи букета получателю?\n\n"
        "Это защитит вас, если получатель скажет, что букет не дошёл."
    )
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


async def show_order_confirm(message: Message, state: FSMContext, edit: bool = False):
    data = await state.get_data()
    distance_km = float(data.get("distance_km", 0))

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

    # Доставка по зонам
    zone = config.get_delivery_zone(distance_km)
    if zone is None:
        await message.answer("❌ Ошибка: расстояние больше допустимого.")
        await state.clear()
        return

    delivery_price = Decimal(str(zone["client_pays"]))
    total_with_delivery = total + delivery_price

    text += f"\n🚚 Доставка: {helpers.money(delivery_price)}"
    if data.get("promo_code"):
        text += f"\n🎁 Промокод: {data['promo_code']}"

    text += f"\n\n📍 {data.get('address')}\n👤 {data.get('client_name')}\n📞 {data.get('client_phone')}"
    text += f"\n📅 {data.get('delivery_date')} | 🕒 {data.get('delivery_slot')}"

    need_photo = data.get("need_photo", True)
    text += f"\n📸 Фото вручения: {'Да' if need_photo else 'Нет'}"
    text += f"\n\n<b>Итого: {helpers.money(total_with_delivery)}</b>"

    await state.set_state(OrderFSM.confirm)
    if edit:
        await message.edit_text(text, reply_markup=kb.order_confirm())
    else:
        await message.answer(text, reply_markup=kb.order_confirm())


@router.callback_query(F.data == "order_pay", OrderFSM.confirm)
async def order_pay(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    distance_km = float(data.get("distance_km", 0))

    async with async_session() as session:
        client = await get_or_create_client(session, call.from_user.id)
        result = await session.execute(
            select(CartItem, Product).join(Product, Product.id == CartItem.product_id)
            .where(CartItem.client_id == client.id)
        )
        rows = result.all()

    total = Decimal("0")
    for ci, p in rows:
        total += Decimal(str(p.client_price)) * ci.quantity

    zone = config.get_delivery_zone(distance_km)
    delivery_price = Decimal(str(zone["client_pays"])) if zone else Decimal("0")
    total_with_delivery = total + delivery_price

    text = (
        f"💳 <b>Оплата заказа</b>\n\n"
        f"Сумма: <b>{helpers.money(total_with_delivery)}</b>\n\n"
        f"Переведите на карту:\n"
        f"<code>{config.CARD_NUMBER}</code>\n"
        f"Получатель: {config.CARD_HOLDER}\n"
        f"Банк: {config.BANK_NAME}\n\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"📝 <b>В комментарии к переводу укажите номер заказа, который придёт ниже.</b>\n\n"
        f"⚠️ Без номера мы не найдём ваш платёж!\n\n"
        f"━━━━━━━━━━━━━━━\n\n"
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
            session=session,
            client_id=client.id,
            address=data.get("address"),
            client_name=data.get("client_name"),
            client_phone=data.get("client_phone"),
            delivery_date=date.fromisoformat(data.get("delivery_date")),
            delivery_slot=data.get("delivery_slot"),
            promo_code=data.get("promo_code"),
            need_photo=data.get("need_photo", True),
            distance_km=float(data.get("distance_km", 0)),
        )

    await state.clear()
    if not order:
        await call.message.edit_text(
            "❌ Не удалось создать заказ. Обратитесь в поддержку.",
            reply_markup=kb.client_main()
        )
        await call.answer()
        return

    await call.message.edit_text(
        f"✅ <b>Заказ #{order.id} создан!</b>\n\n"
        f"💳 <b>В комментарии к переводу укажите:</b>\n"
        f"<code>{order.id}</code>\n\n"
        f"Ожидаем подтверждения оплаты администратором.\n"
        f"Как только оплата поступит — заказ уйдёт магазину.",
        reply_markup=kb.client_main()
    )

    # Админу
    try:
        await bot_admin.send_message(
            config.ADMIN_ID,
            f"💳 <b>Новый платёж!</b>\n\n"
            f"📦 Заказ #{order.id}\n"
            f"💰 Сумма: {helpers.money(order.total_price)}\n"
            f"👤 Клиент: {client.name or 'без имени'}\n"
            f"📞 {client.phone or '—'}"
        )
    except Exception:
        pass

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
        await call.message.edit_text("📦 У вас пока нет заказов.", reply_markup=kb.client_back())
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
        balance_val = client.balance

    text = f"💰 <b>Мой баланс: {helpers.money(balance_val)}</b>\n\n"
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
        await call.message.edit_text("📜 История пуста.",
                                     reply_markup=kb.client_back("client_balance"))
        await call.answer()
        return

    text = "📜 <b>История операций:</b>\n\n"
    for t in txs:
        sign = "+" if float(t.amount) >= 0 else ""
        text += f"{helpers.format_dt(t.created_at)} — {sign}{helpers.money(t.amount)} — {t.type}\n"

    await call.message.edit_text(text, reply_markup=kb.client_back("client_balance"))
    await call.answer()


@router.callback_query(F.data == "balance_withdraw")
async def balance_withdraw(call: CallbackQuery, state: FSMContext):
    async with async_session() as session:
        client = await get_or_create_client(session, call.from_user.id)
        if float(client.balance) < config.CLIENT_MIN_WITHDRAW:
            await call.answer(f"Минимум {config.CLIENT_MIN_WITHDRAW} ₽", show_alert=True)
            return

    await state.set_state(ClientFSM.withdraw_amount)
    await call.message.edit_text(
        f"💸 <b>Вывод на карту</b>\n\n"
        f"💰 Баланс: {helpers.money(client.balance)}\n"
        f"💳 Комиссия: {config.CLIENT_WITHDRAW_COMMISSION}%\n"
        f"💵 Минимум: {config.CLIENT_MIN_WITHDRAW} ₽\n\n"
        f"Введите сумму:",
        reply_markup=kb.cancel_kb("client_balance")
    )
    await call.answer()


@router.message(ClientFSM.withdraw_amount)
async def process_withdraw(message: Message, state: FSMContext):
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
            await message.answer(f"❌ Больше баланса. У вас {helpers.money(client.balance)}")
            return

    await state.update_data(withdraw_amount=float(amount))
    await state.set_state(ClientFSM.withdraw_card)
    await message.answer(
        "💳 Введите номер карты для вывода (16 цифр):",
        reply_markup=kb.cancel_kb("client_balance")
    )


@router.message(ClientFSM.withdraw_card)
async def process_withdraw_card(message: Message, state: FSMContext):
    if not helpers.is_valid_card(message.text):
        await message.answer("❌ Неверный номер карты. 16 цифр.")
        return

    data = await state.get_data()
    amount = Decimal(str(data["withdraw_amount"]))
    card = helpers.clean_phone(message.text)

    async with async_session() as session:
        client = await get_or_create_client(session, message.from_user.id)
        await payments_service.create_payout(
            session=session,
            user_type="client",
            user_id=client.id,
            amount=amount,
            card_number=card,
        )

    await state.clear()
    commission = amount * Decimal(str(config.CLIENT_WITHDRAW_COMMISSION)) / 100
    await message.answer(
        f"✅ <b>Заявка на вывод создана.</b>\n\n"
        f"💰 Сумма: {helpers.money(amount)}\n"
        f"📉 Комиссия {config.CLIENT_WITHDRAW_COMMISSION}%: -{helpers.money(commission)}\n"
        f"💵 К получению: {helpers.money(amount - commission)}\n\n"
        f"Админ переведёт в течение 24 часов.",
        reply_markup=kb.client_main()
    )


# ═══════════════════════════════════════════
#   ПРОМОКОД
# ═══════════════════════════════════════════
@router.callback_query(F.data == "client_promo")
async def promo_menu(call: CallbackQuery, state: FSMContext):
    await state.set_state(ClientFSM.promo_input)
    await call.message.edit_text(
        "🎁 <b>Активация промокода</b>\n\n"
        "Введите код:\n\n"
        "<i>Например: SLIPI10</i>",
        reply_markup=kb.client_back()
    )
    await call.answer()


@router.message(ClientFSM.promo_input)
async def promo_apply(message: Message, state: FSMContext):
    code = message.text.strip().upper()
    async with async_session() as session:
        client = await get_or_create_client(session, message.from_user.id)
        promo = await orders_service.check_promo(session, code)

    if not promo:
        await message.answer("❌ Промокод не найден.", reply_markup=kb.client_main())
        await state.clear()
        return

    if promo.valid_until and promo.valid_until < date.today():
        await message.answer("❌ Промокод истёк.", reply_markup=kb.client_main())
        await state.clear()
        return

    if promo.max_uses > 0 and promo.used_count >= promo.max_uses:
        await message.answer("❌ Промокод больше не действует.", reply_markup=kb.client_main())
        await state.clear()
        return

    async with async_session() as session:
        client = await get_or_create_client(session, message.from_user.id)
        client.active_promo = code
        await session.commit()

    if promo.discount_type == "percent":
        d = f"скидка {int(promo.discount_value)}%"
    else:
        d = f"скидка {helpers.money(promo.discount_value)}"

    await state.clear()
    await message.answer(
        f"✅ <b>Промокод активирован!</b>\n\n"
        f"🎁 {code} — {d}\n\n"
        f"Применится автоматически при следующем заказе.",
        reply_markup=kb.client_main()
    )


# ═══════════════════════════════════════════
#   СОБЫТИЯ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "client_events")
async def events(call: CallbackQuery):
    async with async_session() as session:
        client = await get_or_create_client(session, call.from_user.id)
        result = await session.execute(
            select(ClientEvent).where(ClientEvent.client_id == client.id)
            .order_by(ClientEvent.event_date.asc())
        )
        events_list = result.scalars().all()

    if not events_list:
        text = "📅 <b>Мои события</b>\n\nВы пока не добавили ни одного события."
    else:
        text = f"📅 <b>Мои события ({len(events_list)})</b>\n\n"
        for e in events_list:
            text += f"• {helpers.format_date(e.event_date)} — {e.title}\n"

    await call.message.edit_text(text, reply_markup=kb.events_menu())
    await call.answer()


@router.callback_query(F.data == "event_add")
async def event_add(call: CallbackQuery, state: FSMContext):
    await state.set_state(ClientFSM.event_whom)
    await call.message.edit_text("📅 <b>Кому напомнить?</b>",
                                 reply_markup=kb.event_whom())
    await call.answer()


@router.callback_query(F.data.startswith("event_whom_") & ~F.data.startswith("event_whom_custom"), ClientFSM.event_whom)
async def event_set_whom(call: CallbackQuery, state: FSMContext):
    whom = call.data.replace("event_whom_", "")
    await state.update_data(event_whom=whom)
    await state.set_state(ClientFSM.event_date)
    await call.message.edit_text(
        "📅 <b>Когда?</b>\n\n"
        "Введите дату в формате ДД.ММ.ГГГГ\n"
        "Пример: 15.05.1990",
        reply_markup=kb.cancel_kb("client_main")
    )
    await call.answer()


@router.callback_query(F.data == "event_whom_custom", ClientFSM.event_whom)
async def event_custom_whom(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text(
        "✏️ Введите имя:",
        reply_markup=kb.cancel_kb("client_main")
    )
    await call.answer()


@router.message(ClientFSM.event_whom)
async def event_set_custom_whom(message: Message, state: FSMContext):
    await state.update_data(event_whom=message.text.strip())
    await state.set_state(ClientFSM.event_date)
    await message.answer(
        "📅 <b>Когда?</b>\n\n"
        "Введите дату в формате ДД.ММ.ГГГГ\n"
        "Пример: 15.05.1990",
        reply_markup=kb.cancel_kb("client_main")
    )


@router.message(ClientFSM.event_date)
async def event_set_date(message: Message, state: FSMContext):
    try:
        d = datetime.strptime(message.text.strip(), "%d.%m.%Y").date()
    except Exception:
        await message.answer("❌ Неверный формат. Пример: 15.05.1990")
        return
    await state.update_data(event_date=str(d))
    await state.set_state(ClientFSM.event_type)
    await message.answer(
        "🎉 <b>Что за событие?</b>",
        reply_markup=kb.event_type()
    )


@router.callback_query(F.data.startswith("event_type_") & ~F.data.startswith("event_type_custom"), ClientFSM.event_type)
async def event_set_type(call: CallbackQuery, state: FSMContext):
    etype = call.data.replace("event_type_", "")
    data = await state.get_data()
    title = f"{etype} {data.get('event_whom', '')}".strip()

    async with async_session() as session:
        client = await get_or_create_client(session, call.from_user.id)
        session.add(ClientEvent(
            client_id=client.id,
            title=title,
            event_type=etype,
            event_date=datetime.strptime(data["event_date"], "%Y-%m-%d").date(),
        ))
        await session.commit()

    await state.clear()
    await call.message.edit_text(
        f"✅ <b>Событие добавлено!</b>\n\n"
        f"📅 {data['event_date']} — {title}\n\n"
        f"Напомним за 3 дня и за 1 день.",
        reply_markup=kb.client_main()
    )
    await call.answer()


@router.callback_query(F.data == "event_type_custom", ClientFSM.event_type)
async def event_custom_type(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text(
        "✏️ Введите название события:",
        reply_markup=kb.cancel_kb("client_main")
    )
    await call.answer()


@router.message(ClientFSM.event_type)
async def event_set_custom_type(message: Message, state: FSMContext):
    data = await state.get_data()
    title = message.text.strip()

    async with async_session() as session:
        client = await get_or_create_client(session, message.from_user.id)
        session.add(ClientEvent(
            client_id=client.id,
            title=title,
            event_type="other",
            event_date=datetime.strptime(data["event_date"], "%Y-%m-%d").date(),
        ))
        await session.commit()

    await state.clear()
    await message.answer(
        f"✅ <b>Событие добавлено!</b>\n\n"
        f"📅 {data['event_date']} — {title}",
        reply_markup=kb.client_main()
    )


# ═══════════════════════════════════════════
#   ТРЕКИНГ ЗАКАЗА
# ═══════════════════════════════════════════
@router.callback_query(F.data.startswith("track_refresh_"))
async def track_refresh(call: CallbackQuery):
    order_id = int(call.data.split("_")[2])
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
            c_result = await session.execute(
                select(Courier).where(Courier.id == order.courier_id)
            )
            courier = c_result.scalar_one_or_none()

    status_map = {
        "pending":    "⏳ Ожидает подтверждения оплаты",
        "wait":       "🔍 Ищем курьера",
        "going":      "🚴 Курьер едет в магазин",
        "picked":     "📦 Курьер забрал букет",
        "delivering": "🚴 Курьер везёт вам",
        "at_client":  "📍 Курьер у вас",
        "done":       "✅ Доставлено",
        "cancel":     "❌ Отменено",
    }

    status_text = status_map.get(order.status, order.status)

    text = (
        f"📦 <b>Заказ #{order.id}</b>\n\n"
        f"📍 {order.address}\n"
        f"💰 {helpers.money(order.total_price)}\n"
        f"🕒 {helpers.format_date(order.delivery_date)} {order.delivery_slot or ''}\n\n"
        f"━━━━━━━━━━━━━━━\n"
        f"<b>{status_text}</b>\n"
    )

    if courier and order.status in ("going", "picked", "delivering", "at_client"):
        text += f"\n👤 Курьер: {courier.name}\n⭐ {float(courier.rating or 0):.1f}"

    markup = kb.track_order(
        order_id,
        order.status,
        courier.phone if courier else None,
        float(courier.lat) if courier and courier.lat else None,
        float(courier.lon) if courier and courier.lon else None,
    )

    if edit:
        try:
            await message.edit_text(text, reply_markup=markup)
        except Exception:
            pass
    else:
        await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("track_cancel_") & ~F.data.startswith("track_cancel_yes_"))
async def track_cancel(call: CallbackQuery):
    order_id = int(call.data.split("_")[2])
    async with async_session() as session:
        result = await session.execute(select(Order).where(Order.id == order_id))
        order = result.scalar_one_or_none()

    if not order:
        await call.answer("Заказ не найден", show_alert=True)
        return

    if order.status not in ("pending",):
        await call.answer("❌ Заказ уже в работе. Отмена невозможна.", show_alert=True)
        return

    await call.message.edit_text(
        f"❌ <b>Отменить заказ #{order_id}?</b>\n\n"
        f"Деньги вернутся на ваш баланс.",
        reply_markup=kb.cancel_confirm(order_id)
    )
    await call.answer()


@router.callback_query(F.data.startswith("track_cancel_yes_"))
async def track_cancel_yes(call: CallbackQuery):
    order_id = int(call.data.split("_")[3])
    async with async_session() as session:
        order = await orders_service.cancel_order(
            session, order_id,
            reason="client_cancelled",
            cancelled_by="client",
            refund=True,
        )

    await call.message.edit_text(
        f"✅ <b>Заказ #{order_id} отменён.</b>\n\n"
        f"💰 Деньги вернулись на ваш баланс.",
        reply_markup=kb.client_main()
    )
    await call.answer()


# ═══════════════════════════════════════════
#   ОТЗЫВ
# ═══════════════════════════════════════════
@router.callback_query(F.data.startswith("rate_") & ~F.data.startswith("rate_skip_"))
async def process_rating(call: CallbackQuery, state: FSMContext):
    parts = call.data.split("_")
    target = parts[1]
    order_id = int(parts[2])
    rating = int(parts[3])

    from models import Review

    async with async_session() as session:
        client = await get_or_create_client(session, call.from_user.id)

        target_id = None
        if target == "shop":
            o_r = await session.execute(select(Order).where(Order.id == order_id))
            order = o_r.scalar_one_or_none()
            target_id = order.shop_id if order else None
        elif target == "courier":
            o_r = await session.execute(select(Order).where(Order.id == order_id))
            order = o_r.scalar_one_or_none()
            target_id = order.courier_id if order else None

        session.add(Review(
            order_id=order_id,
            from_tg_id=call.from_user.id,
            target_type=target,
            target_id=target_id or 0,
            rating=rating,
        ))
        await session.commit()

        # Пересчёт рейтинга
        from sqlalchemy import func as sqlfunc
        if target == "shop" and target_id:
            r = await session.execute(
                select(sqlfunc.avg(Review.rating), sqlfunc.count(Review.id))
                .where(Review.target_type == "shop", Review.target_id == target_id)
            )
            row = r.first()
            if row and row[0]:
                sr = await session.execute(select(Shop).where(Shop.id == target_id))
                shop = sr.scalar_one_or_none()
                if shop:
                    shop.rating = round(float(row[0]), 2)
                    shop.reviews_count = row[1]
                    await session.commit()

        if target == "courier" and target_id:
            r = await session.execute(
                select(sqlfunc.avg(Review.rating), sqlfunc.count(Review.id))
                .where(Review.target_type == "courier", Review.target_id == target_id)
            )
            row = r.first()
            if row and row[0]:
                cr = await session.execute(select(Courier).where(Courier.id == target_id))
                courier = cr.scalar_one_or_none()
                if courier:
                    courier.rating = round(float(row[0]), 2)
                    courier.reviews_count = row[1]
                    await session.commit()

    if target == "shop":
        await call.message.edit_text(
            f"⭐ Магазин: {rating} звёзд\n\nТеперь оцените курьера:",
            reply_markup=kb.rating_kb("courier", order_id)
        )
    elif target == "courier":
        await call.message.edit_text(
            f"⭐ Курьер: {rating} звёзд\n\n💬 Напишите комментарий (или /skip):",
            reply_markup=kb.skip_comment()
        )
        await state.set_state(ClientFSM.review_comment)
        await state.update_data(review_order_id=order_id)

    await call.answer()


@router.callback_query(F.data.startswith("rate_skip_"))
async def rate_skip(call: CallbackQuery, state: FSMContext):
    parts = call.data.split("_")
    target = parts[2]
    order_id = parts[3]

    if target == "shop":
        await call.message.edit_text(
            "⭐ Оцените курьера:",
            reply_markup=kb.rating_kb("courier", int(order_id))
        )
    else:
        await state.clear()
        await call.message.edit_text(
            "✅ Спасибо за заказ! Ждём снова 🌸",
            reply_markup=kb.client_main()
        )
    await call.answer()


@router.message(ClientFSM.review_comment)
async def review_comment(message: Message, state: FSMContext):
    data = await state.get_data()
    text = "" if message.text.startswith("/skip") else message.text[:500]

    if text:
        from models import Review
        async with async_session() as session:
            r = await session.execute(
                select(Review).where(
                    Review.order_id == data.get("review_order_id"),
                    Review.target_type == "courier",
                ).order_by(Review.id.desc()).limit(1)
            )
            rev = r.scalar_one_or_none()
            if rev:
                rev.comment = text
                await session.commit()

    await state.clear()
    await message.answer(
        "✅ <b>Спасибо за отзыв!</b>\n\nЖдём вас снова 🌸",
        reply_markup=kb.client_main()
            )
