# -*- coding: utf-8 -*-
"""
SLIPI — бот магазина
"""
from datetime import date
from decimal import Decimal

from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from sqlalchemy import select, update, func

import config
import keyboards as kb
from states import ShopReg, ShopProduct, ShopEdit
from database import async_session
from models import (
    Shop, Product, ShopCategory, Order, OrderItem, Client, ChatMessage,
)
from services import orders as orders_service
from services import payments as payments_service
from utils import helpers

router = Router(name="shop")


# ═══════════════════════════════════════════
#   ХЕЛПЕР
# ═══════════════════════════════════════════
async def get_shop(session, tg_id: int):
    result = await session.execute(select(Shop).where(Shop.tg_id == tg_id))
    return result.scalar_one_or_none()


async def show_shop_menu(message: Message, shop: Shop, edit: bool = False):
    text = (
        f"🏪 <b>{shop.name}</b>\n"
        f"⭐ {float(shop.rating or 0):.1f} | Заказов: {shop.total_orders}"
    )
    if edit:
        await message.edit_text(text, reply_markup=kb.shop_main())
    else:
        await message.answer(text, reply_markup=kb.shop_main())


# ═══════════════════════════════════════════
#   /start
# ═══════════════════════════════════════════
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        shop = await get_shop(session, message.from_user.id)

    if not shop:
        await message.answer(
            "🏪 <b>Стать партнёром SLIPI</b>\n\n"
            "Отправьте команду /register чтобы зарегистрироваться."
        )
        return

    if shop.status == "pending":
        await message.answer("⏳ Ваша заявка на рассмотрении.")
        return

    if shop.status == "blocked":
        await message.answer("🚫 Доступ закрыт. Обратитесь к админу.")
        return

    await show_shop_menu(message, shop)


@router.callback_query(F.data == "shop_main")
async def back_main(call: CallbackQuery, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        shop = await get_shop(session, call.from_user.id)
    if not shop:
        await call.answer("Ошибка", show_alert=True)
        return
    await show_shop_menu(call.message, shop, edit=True)
    await call.answer()


# ═══════════════════════════════════════════
#   РЕГИСТРАЦИЯ
# ═══════════════════════════════════════════
@router.message(Command("register"))
async def shop_register(message: Message, state: FSMContext):
    async with async_session() as session:
        existing = await get_shop(session, message.from_user.id)
        if existing:
            await message.answer("Вы уже зарегистрированы.")
            return

    await state.set_state(ShopReg.name)
    await message.answer(
        "📝 <b>Шаг 1/7:</b> Название магазина",
        reply_markup=kb.cancel_kb()
    )


@router.message(ShopReg.name)
async def reg_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(ShopReg.address)
    await message.answer("📝 <b>Шаг 2/7:</b> Адрес магазина", reply_markup=kb.cancel_kb())


@router.message(ShopReg.address)
async def reg_address(message: Message, state: FSMContext):
    await state.update_data(address=message.text.strip())
    await state.set_state(ShopReg.phone)
    await message.answer("📝 <b>Шаг 3/7:</b> Телефон (11 цифр)", reply_markup=kb.cancel_kb())


@router.message(ShopReg.phone)
async def reg_phone(message: Message, state: FSMContext):
    if not helpers.is_valid_phone(message.text):
        await message.answer("❌ Неверный номер. Введите 10–15 цифр.")
        return
    await state.update_data(phone=helpers.clean_phone(message.text))
    await state.set_state(ShopReg.telegram)
    await message.answer("📝 <b>Шаг 4/7:</b> Ваш Telegram (@username) или /skip",
                         reply_markup=kb.cancel_kb())


@router.message(ShopReg.telegram)
async def reg_tg(message: Message, state: FSMContext):
    tg = None if message.text.startswith("/skip") else (
        message.text if message.text.startswith("@") else "@" + message.text
    )
    await state.update_data(telegram=tg)
    await state.set_state(ShopReg.vk)
    await message.answer("📝 <b>Шаг 5/7:</b> ВК (ссылка) или /skip", reply_markup=kb.cancel_kb())


@router.message(ShopReg.vk)
async def reg_vk(message: Message, state: FSMContext):
    vk = None if message.text.startswith("/skip") else message.text.strip()
    await state.update_data(vk_link=vk)
    await state.set_state(ShopReg.owner_name)
    await message.answer("📝 <b>Шаг 6/7:</b> Ваше имя", reply_markup=kb.cancel_kb())


@router.message(ShopReg.owner_name)
async def reg_owner(message: Message, state: FSMContext):
    await state.update_data(owner_name=message.text.strip())
    await state.set_state(ShopReg.geo)
    await message.answer(
        "📝 <b>Шаг 7/7:</b> Отправьте геолокацию магазина (📍 скрепка → Геолокация)",
        reply_markup=kb.cancel_kb()
    )


@router.message(ShopReg.geo, F.location)
async def reg_geo(message: Message, state: FSMContext):
    data = await state.get_data()
    async with async_session() as session:
        shop = Shop(
            tg_id=message.from_user.id,
            name=data["name"],
            address=data["address"],
            phone=data["phone"],
            telegram=data.get("telegram"),
            vk_link=data.get("vk_link"),
            owner_name=data.get("owner_name"),
            lat=message.location.latitude,
            lon=message.location.longitude,
            status="pending",
        )
        session.add(shop)
        await session.commit()

    await state.clear()
    await message.answer(
        "✅ <b>Заявка отправлена!</b>\nЖдём одобрения админа.",
        reply_markup=kb.cancel_kb()
    )

    try:
        await message.bot.send_message(
            config.ADMIN_ID,
            f"🏪 <b>Новая заявка магазина</b>\n\n"
            f"📛 {data['name']}\n"
            f"📍 {data['address']}\n"
            f"📞 {data['phone']}\n"
            f"👤 {data.get('owner_name', '—')}"
        )
    except Exception:
        pass


# ═══════════════════════════════════════════
#   МОИ ТОВАРЫ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "shop_my_products")
async def my_products(call: CallbackQuery):
    async with async_session() as session:
        shop = await get_shop(session, call.from_user.id)
        if not shop:
            await call.answer("Ошибка", show_alert=True)
            return
        result = await session.execute(
            select(Product).where(Product.shop_id == shop.id).order_by(Product.id.desc())
        )
        products = result.scalars().all()

    if not products:
        await call.message.edit_text(
            "📦 У вас пока нет товаров.",
            reply_markup=kb.shop_products_menu()
        )
        await call.answer()
        return

    text = f"📦 <b>Ваши товары ({len(products)})</b>\n\n"
    for i, p in enumerate(products[:10], start=1):
        active = "✅" if p.is_active else "⏸"
        text += f"{active} {i}. {p.title} — {helpers.money(p.shop_price)}\n"

    await call.message.edit_text(text, reply_markup=kb.shop_products_menu())
    await call.answer()


@router.callback_query(F.data == "shop_add_product")
async def add_product_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(ShopProduct.photo)
    await call.message.edit_text(
        "📸 <b>Шаг 1/5:</b> Отправьте фото товара",
        reply_markup=kb.cancel_kb()
    )
    await call.answer()


@router.message(ShopProduct.photo, F.photo)
async def add_product_photo(message: Message, state: FSMContext):
    await state.update_data(photo_id=message.photo[-1].file_id)
    await state.set_state(ShopProduct.title)
    await message.answer("📝 <b>Шаг 2/5:</b> Название товара", reply_markup=kb.cancel_kb())


@router.message(ShopProduct.title)
async def add_product_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await state.set_state(ShopProduct.description)
    await message.answer("📝 <b>Шаг 3/5:</b> Описание", reply_markup=kb.cancel_kb())


@router.message(ShopProduct.description)
async def add_product_desc(message: Message, state: FSMContext):
    await state.update_data(description=message.text.strip())
    await state.set_state(ShopProduct.price)
    await message.answer("💰 <b>Шаг 4/5:</b> Ваша цена (в рублях)", reply_markup=kb.cancel_kb())


@router.message(ShopProduct.price)
async def add_product_price(message: Message, state: FSMContext):
    try:
        price = float(message.text.replace(",", ".").replace(" ", ""))
        if price <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите число больше 0.")
        return

    markup = config.get_markup(price)
    client_price = price + markup

    await state.update_data(shop_price=price, markup=markup, client_price=client_price)
    await state.set_state(ShopProduct.category)

    rows = []
    for key, info in config.CATEGORIES.items():
        rows.append([kb.btn(info["name"], f"shop_prod_cat_{key}")])
    rows.append([kb.btn("❌ Отмена", "shop_main")])

    await message.answer(
        f"💰 Ваша: {helpers.money(price)}\n"
        f"💰 Клиент: {helpers.money(client_price)} (наценка {helpers.money(markup)})\n\n"
        f"<b>Шаг 5/5:</b> Выберите категорию:",
        reply_markup=kb.kb(rows)
    )


@router.callback_query(F.data.startswith("shop_prod_cat_"), ShopProduct.category)
async def add_product_category(call: CallbackQuery, state: FSMContext):
    cat = call.data.replace("shop_prod_cat_", "")
    data = await state.get_data()

    async with async_session() as session:
        shop = await get_shop(session, call.from_user.id)
        if not shop:
            await call.answer("Ошибка", show_alert=True)
            return

        product = Product(
            shop_id=shop.id,
            category=cat,
            title=data["title"],
            description=data.get("description"),
            photo_id=data["photo_id"],
            shop_price=data["shop_price"],
            markup=data["markup"],
            client_price=data["client_price"],
            is_active=True,
        )
        session.add(product)

        cat_check = await session.execute(
            select(ShopCategory).where(
                ShopCategory.shop_id == shop.id,
                ShopCategory.category == cat,
            )
        )
        if not cat_check.scalar_one_or_none():
            session.add(ShopCategory(shop_id=shop.id, category=cat))

        await session.commit()

    await state.clear()
    await call.message.edit_text(
        f"✅ Товар «{data['title']}» добавлен!",
        reply_markup=kb.shop_main()
    )
    await call.answer()


# ═══════════════════════════════════════════
#   КАТЕГОРИИ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "shop_my_categories")
async def my_categories(call: CallbackQuery):
    async with async_session() as session:
        shop = await get_shop(session, call.from_user.id)
        if not shop:
            await call.answer("Ошибка", show_alert=True)
            return
        result = await session.execute(
            select(ShopCategory).where(ShopCategory.shop_id == shop.id)
        )
        cats = result.scalars().all()

    text = f"🏷 <b>Ваши категории ({len(cats)})</b>\n\n"
    for c in cats:
        name = helpers.category_name(c.category)
        text += f"✅ {name}\n"

    if not cats:
        text = "🏷 <b>У вас нет активных категорий.</b>\n\nДобавьте хотя бы одну."

    await call.message.edit_text(text, reply_markup=kb.shop_categories_menu())
    await call.answer()


@router.callback_query(F.data == "shop_cat_add")
async def shop_cat_add(call: CallbackQuery):
    async with async_session() as session:
        shop = await get_shop(session, call.from_user.id)
        result = await session.execute(
            select(ShopCategory).where(ShopCategory.shop_id == shop.id)
        )
        active = [c.category for c in result.scalars().all()]

    await call.message.edit_text(
        "🏷 <b>Выберите категории:</b>\n\nОтметьте нужные, потом «Сохранить»",
        reply_markup=kb.shop_categories_choice(active, config.CATEGORIES)
    )
    await call.answer()


@router.callback_query(F.data.startswith("shop_cat_toggle_"))
async def shop_cat_toggle(call: CallbackQuery):
    cat = call.data.replace("shop_cat_toggle_", "")
    async with async_session() as session:
        shop = await get_shop(session, call.from_user.id)
        result = await session.execute(
            select(ShopCategory).where(
                ShopCategory.shop_id == shop.id,
                ShopCategory.category == cat,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            await session.delete(existing)
            await session.commit()
        else:
            session.add(ShopCategory(shop_id=shop.id, category=cat))
            await session.commit()

        result = await session.execute(
            select(ShopCategory).where(ShopCategory.shop_id == shop.id)
        )
        active = [c.category for c in result.scalars().all()]

    await call.message.edit_reply_markup(
        reply_markup=kb.shop_categories_choice(active, config.CATEGORIES)
    )
    await call.answer()


@router.callback_query(F.data == "shop_cat_save")
async def shop_cat_save(call: CallbackQuery):
    await call.answer("✅ Сохранено", show_alert=True)
    await my_categories(call)


# ═══════════════════════════════════════════
#   НОВЫЕ ЗАКАЗЫ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "shop_new_orders")
async def new_orders(call: CallbackQuery):
    async with async_session() as session:
        shop = await get_shop(session, call.from_user.id)
        if not shop:
            await call.answer("Ошибка", show_alert=True)
            return
        result = await session.execute(
            select(Order).where(
                Order.shop_id == shop.id,
                Order.status == "wait",
                Order.payment_status == "confirmed",
            ).order_by(Order.id.asc())
        )
        orders = result.scalars().all()

    if not orders:
        await call.message.edit_text("📋 Нет новых заказов.", reply_markup=kb.shop_main())
        await call.answer()
        return

    for o in orders[:5]:
        items_result_text = ""
        async with async_session() as session:
            r = await session.execute(
                select(OrderItem).where(OrderItem.order_id == o.id)
            )
            items = r.scalars().all()
            for it in items:
                items_result_text += f"• {it.title} × {it.quantity}\n"

        text = (
            f"🔔 <b>НОВЫЙ ЗАКАЗ #{o.id}</b>\n\n"
            f"{items_result_text}\n"
            f"📍 {o.address}\n"
            f"👤 {o.client_name}, {o.client_phone}\n"
            f"📅 {helpers.format_date(o.delivery_date)} | 🕒 {o.delivery_slot or '—'}\n"
            f"💰 Оплачено: {helpers.money(o.total_price)}"
        )
        try:
            await call.message.answer(text, reply_markup=kb.shop_order_new(o.id))
        except Exception:
            pass

    await call.answer()


@router.callback_query(F.data.startswith("shop_accept_"))
async def shop_accept(call: CallbackQuery):
    order_id = int(call.data.split("_")[2])
    async with async_session() as session:
        shop = await get_shop(session, call.from_user.id)
        if not shop:
            await call.answer("Ошибка", show_alert=True)
            return
        order = await orders_service.update_order_status(session, order_id, "wait")

        o_r = await session.execute(select(Order).where(Order.id == order_id))
        order = o_r.scalar_one_or_none()
        c_r = await session.execute(select(Client).where(Client.id == order.client_id))
        client = c_r.scalar_one_or_none()

    await call.message.edit_text(f"✅ Заказ #{order_id} принят! Ищем курьера.")

    if client and client.tg_id:
        try:
            await call.bot.send_message(
                client.tg_id,
                f"🟢 <b>Магазин принял ваш заказ #{order_id}!</b>\n\n"
                f"Собираем букет и ищем курьера 🚴"
            )
        except Exception:
            pass

    await call.answer()


@router.callback_query(F.data.startswith("shop_reject_") & ~F.data.startswith("shop_reject_reason_"))
async def shop_reject(call: CallbackQuery):
    order_id = int(call.data.split("_")[2])
    await call.message.edit_text(
        f"❌ Почему отклоняете заказ #{order_id}?",
        reply_markup=kb.shop_reject_reasons(order_id)
    )
    await call.answer()


@router.callback_query(F.data.startswith("shop_reject_reason_"))
async def shop_reject_reason(call: CallbackQuery):
    parts = call.data.split("_")
    order_id = int(parts[3])
    reason = parts[4]

    async with async_session() as session:
        o_r = await session.execute(select(Order).where(Order.id == order_id))
        order = o_r.scalar_one_or_none()

        await orders_service.cancel_order(
            session, order_id,
            reason=reason,
            cancelled_by="shop",
            refund=True,
        )

        # Автоскрытие товара, если нет в наличии
        if reason == "out_of_stock" and order:
            items_r = await session.execute(
                select(OrderItem).where(OrderItem.order_id == order_id)
            )
            for oi in items_r.scalars().all():
                p_r = await session.execute(select(Product).where(Product.id == oi.product_id))
                p = p_r.scalar_one_or_none()
                if p:
                    p.is_active = False
            await session.commit()

        client = None
        if order:
            c_r = await session.execute(select(Client).where(Client.id == order.client_id))
            client = c_r.scalar_one_or_none()

    await call.message.edit_text(f"❌ Заказ #{order_id} отклонён.")

    if order and client and client.tg_id:
        reason_text = {
            "out_of_stock": "💐 Нет в наличии",
            "too_long": "⏰ Не успеваем собрать",
            "tech": "🚫 Технические проблемы",
            "other": "💬 Другая причина",
        }.get(reason, reason)

        try:
            await call.bot.send_message(
                client.tg_id,
                f"😔 <b>Магазин отклонил заказ #{order_id}</b>\n\n"
                f"Причина: {reason_text}\n\n"
                f"💰 Деньги вернутся на ваш баланс."
            )
        except Exception:
            pass

    await call.answer()


# ═══════════════════════════════════════════
#   СТАТИСТИКА
# ═══════════════════════════════════════════
@router.callback_query(F.data == "shop_stats")
async def stats(call: CallbackQuery):
    async with async_session() as session:
        shop = await get_shop(session, call.from_user.id)
        if not shop:
            await call.answer("Ошибка", show_alert=True)
            return
        orders = await orders_service.get_shop_orders(session, shop.id)

    done = sum(1 for o in orders if o.status == "done")
    cancel = sum(1 for o in orders if o.status == "cancel")
    total_sum = sum(float(o.total_price) for o in orders if o.status == "done")

    text = (
        f"📊 <b>Статистика</b>\n\n"
        f"📦 Заказов всего: {len(orders)}\n"
        f"✅ Доставлено: {done}\n"
        f"❌ Отменено: {cancel}\n\n"
        f"💰 Оборот: {helpers.money(total_sum)}\n"
        f"🏦 К выплате: {helpers.money(shop.balance)}\n"
        f"⭐ Рейтинг: {float(shop.rating or 0):.1f} ({shop.reviews_count})"
    )
    await call.message.edit_text(text, reply_markup=kb.shop_stats_menu())
    await call.answer()


@router.callback_query(F.data == "shop_request_payout")
async def request_payout(call: CallbackQuery, state: FSMContext):
    async with async_session() as session:
        shop = await get_shop(session, call.from_user.id)
    if not shop or float(shop.balance) <= 0:
        await call.answer("Нечего выводить", show_alert=True)
        return

    await state.set_state(ShopEdit.payout)
    await call.message.edit_text(
        f"💸 <b>Запрос выплаты</b>\n\n"
        f"Доступно: {helpers.money(shop.balance)}\n\n"
        f"Введите сумму для вывода:",
        reply_markup=kb.cancel_kb("shop_stats")
    )
    await call.answer()


@router.message(ShopEdit.payout)
async def process_payout(message: Message, state: FSMContext):
    try:
        amount = Decimal(message.text.replace(",", ".").strip())
    except Exception:
        await message.answer("❌ Введите число.")
        return

    async with async_session() as session:
        shop = await get_shop(session, message.from_user.id)
        if not shop or amount <= 0 or amount > shop.balance:
            await message.answer("❌ Неверная сумма.")
            return

        await payments_service.create_payout(
            session=session,
            user_type="shop",
            user_id=shop.id,
            amount=amount,
            card_number=None,
            holder_name=shop.name,
        )

    await state.clear()
    await message.answer(
        f"✅ Заявка на выплату {helpers.money(amount)} отправлена админу.",
        reply_markup=kb.shop_main()
    )


# ═══════════════════════════════════════════
#   НАСТРОЙКИ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "shop_settings")
async def settings(call: CallbackQuery):
    async with async_session() as session:
        shop = await get_shop(session, call.from_user.id)
    if not shop:
        await call.answer("Ошибка", show_alert=True)
        return

    text = (
        f"⚙️ <b>Настройки</b>\n\n"
        f"📛 {shop.name}\n"
        f"📍 {shop.address or '—'}\n"
        f"📞 {shop.phone or '—'}"
    )
    await call.message.edit_text(text, reply_markup=kb.shop_settings_menu())
    await call.answer()


@router.callback_query(F.data == "shop_pause")
async def pause_shop(call: CallbackQuery):
    async with async_session() as session:
        shop = await get_shop(session, call.from_user.id)
        shop.is_paused = not shop.is_paused
        await session.commit()
        status = "приостановлен" if shop.is_paused else "активирован"
    await call.answer(f"Магазин {status}", show_alert=True)
    await show_shop_menu(call.message, shop, edit=True)


@router.callback_query(F.data == "shop_set_name")
async def set_name_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(ShopEdit.name)
    await call.message.edit_text(
        "✏️ Введите новое название магазина:",
        reply_markup=kb.cancel_kb("shop_settings")
    )
    await call.answer()


@router.message(ShopEdit.name)
async def set_name(message: Message, state: FSMContext):
    async with async_session() as session:
        shop = await get_shop(session, message.from_user.id)
        shop.name = message.text.strip()
        await session.commit()
    await state.clear()
    await message.answer("✅ Название обновлено.", reply_markup=kb.shop_main())


@router.callback_query(F.data == "shop_set_address")
async def set_address_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(ShopEdit.address)
    await call.message.edit_text(
        "✏️ Введите новый адрес:",
        reply_markup=kb.cancel_kb("shop_settings")
    )
    await call.answer()


@router.message(ShopEdit.address)
async def set_address(message: Message, state: FSMContext):
    async with async_session() as session:
        shop = await get_shop(session, message.from_user.id)
        shop.address = message.text.strip()
        await session.commit()
    await state.clear()
    await message.answer("✅ Адрес обновлён.", reply_markup=kb.shop_main())


@router.callback_query(F.data == "shop_set_phone")
async def set_phone_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(ShopEdit.phone)
    await call.message.edit_text(
        "✏️ Введите новый телефон:",
        reply_markup=kb.cancel_kb("shop_settings")
    )
    await call.answer()


@router.message(ShopEdit.phone)
async def set_phone(message: Message, state: FSMContext):
    if not helpers.is_valid_phone(message.text):
        await message.answer("❌ Неверный номер.")
        return
    async with async_session() as session:
        shop = await get_shop(session, message.from_user.id)
        shop.phone = helpers.clean_phone(message.text)
        await session.commit()
    await state.clear()
    await message.answer("✅ Телефон обновлён.", reply_markup=kb.shop_main())


@router.callback_query(F.data == "shop_set_geo")
async def set_geo_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(ShopEdit.geo)
    await call.message.edit_text(
        "📍 Отправьте новую геолокацию магазина:",
        reply_markup=kb.cancel_kb("shop_settings")
    )
    await call.answer()


@router.message(ShopEdit.geo, F.location)
async def set_geo(message: Message, state: FSMContext):
    async with async_session() as session:
        shop = await get_shop(session, message.from_user.id)
        shop.lat = message.location.latitude
        shop.lon = message.location.longitude
        await session.commit()
    await state.clear()
    await message.answer("✅ Гео обновлено.", reply_markup=kb.shop_main())
