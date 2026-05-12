"""Async database engine + session factory."""
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlmodel import SQLModel
from typing import AsyncGenerator
from app.config import get_settings

settings = get_settings()

# Converte URL pra usar driver async (asyncpg) se ainda não estiver
DATABASE_URL = settings.database_url
if DATABASE_URL.startswith("postgresql+psycopg://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("sqlite:///"):
    DATABASE_URL = DATABASE_URL.replace("sqlite:///", "sqlite+aiosqlite:///", 1)

engine = create_async_engine(
    DATABASE_URL,
    echo=settings.debug,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionFactory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: injeta uma sessão por request."""
    async with AsyncSessionFactory() as session:
        yield session


async def init_db() -> None:
    """Cria tabelas (usado em dev/testes; em prod usar Alembic)."""
    from app import models  # noqa: F401  – registra todos modelos no metadata
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def ping_db() -> bool:
    """Pinga o banco. Retorna True se respondeu."""
    try:
        async with engine.connect() as conn:
            from sqlalchemy import text
            result = await conn.execute(text("SELECT 1"))
            return result.scalar() == 1
    except Exception:
        return False
