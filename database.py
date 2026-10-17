# -*- coding: utf-8 -*-
"""
SLIPI — подключение к базе данных SQLite
"""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

import config

class Base(DeclarativeBase):
    pass

# Добавлен connect_args={"timeout": 30} для защиты от блокировок при 4 ботах
engine = create_async_engine(
    config.DATABASE_URL,
    echo=False,
    connect_args={"timeout": 30},
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

async def init_db():
    """Создаёт все таблицы + включает WAL-режим."""
    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.execute(text("PRAGMA synchronous=NORMAL"))
        # Импорт моделей, чтобы SQLAlchemy видел их перед create_all
        import models 
        await conn.run_sync(Base.metadata.create_all)

async def get_session():
    """ИСПРАВЛЕНО: Теперь используется yield вместо return."""
    async with async_session() as session:
        yield session
