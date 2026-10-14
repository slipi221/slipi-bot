# -*- coding: utf-8 -*-
"""
SLIPI — подключение к базе данных PostgreSQL
"""
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy.orm import DeclarativeBase

import config


# ═══════════════════════════════════════════
#   БАЗОВЫЙ КЛАСС ДЛЯ МОДЕЛЕЙ
# ═══════════════════════════════════════════
class Base(DeclarativeBase):
    pass


# ═══════════════════════════════════════════
#   АСИНХРОННЫЙ ДВИЖОК
# ═══════════════════════════════════════════
engine = create_async_engine(
    config.DATABASE_URL,
    echo=False,           # True — выводить SQL-запросы в консоль (для отладки)
    pool_pre_ping=True,   # проверять соединение перед использованием
    pool_size=10,         # размер пула соединений
    max_overflow=20,      # максимум дополнительных соединений
)


# ═══════════════════════════════════════════
#   ФАБРИКА СЕССИЙ
# ═══════════════════════════════════════════
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ═══════════════════════════════════════════
#   СОЗДАНИЕ ВСЕХ ТАБЛИЦ
# ═══════════════════════════════════════════
async def init_db():
    """Создаёт все таблицы в БД (если их ещё нет)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ═══════════════════════════════════════════
#   ПОЛУЧЕНИЕ СЕССИИ (для хендлеров)
# ═══════════════════════════════════════════
async def get_session() -> AsyncSession:
    """Возвращает асинхронную сессию БД."""
    async with async_session() as session:
        return session
