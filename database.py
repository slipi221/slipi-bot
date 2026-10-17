# -*- coding: utf-8 -*-
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
    log.info(f"🔧 Инициализация БД: {config.DATABASE_URL}")
    try:
        import models  # КРИТИЧНО! Импорт моделей внутри функции
        
        async with engine.begin() as conn:
            await conn.execute(text("PRAGMA journal_mode=WAL"))
            await conn.execute(text("PRAGMA synchronous=NORMAL"))
            await conn.run_sync(Base.metadata.create_all)
            
        log.info("✅ Таблицы успешно созданы!")
    except Exception as e:
        log.error(f"❌ Ошибка создания таблиц: {e}")
        raise

async def get_session():
    async with async_session() as session:
        yield session
