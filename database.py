# -*- coding: utf-8 -*-
"""
SLIPI — подключение к базе данных SQLite
"""
import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

import config

log = logging.getLogger("slipi")

class Base(DeclarativeBase):
    pass

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
    log.info(f"🔧 Инициализация БД по пути: {config.DATABASE_URL}")
    try:
        # ВАЖНО: Импорт моделей перед созданием таблиц
        import models
        
        async with engine.begin() as conn:
            await conn.execute(text("PRAGMA journal_mode=WAL"))
            await conn.execute(text("PRAGMA synchronous=NORMAL"))
            await conn.run_sync(Base.metadata.create_all)
            
        log.info("✅ Таблицы успешно созданы!")
    except Exception as e:
        log.error(f"❌ Ошибка при создании таблиц: {e}")
        raise e
