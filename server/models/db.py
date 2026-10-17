from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from server.config import settings


class Base(DeclarativeBase):
    pass


# Create async engine
engine = create_async_engine(settings.database_url, echo=False)

# Create session factory
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncSession:
    """Dependency for FastAPI routes to get DB session."""
    async with async_session() as session:
        yield session
