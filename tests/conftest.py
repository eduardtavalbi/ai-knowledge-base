import pytest
import pytest_asyncio

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine
)

from sqlalchemy.pool import StaticPool

from app.main import app
from app.api.auth import get_current_user
from app.models.user import User
from app.db.base import Base
from app.db.session import get_db

test_engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest_asyncio.fixture
async def client():
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with TestingSessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    async with TestingSessionLocal() as session:
        test_user = User(
            id=1,
            email="test@example.com",
            hashed_password="not-used-by-tests",
        )
        session.add(test_user)
        await session.commit()

    async def override_current_user():
        return test_user

    app.dependency_overrides[get_current_user] = override_current_user

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as test_client:
        yield test_client

    app.dependency_overrides.clear()

    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)


@pytest.fixture
def test_marker():
    return "test"


@pytest_asyncio.fixture
async def unauthenticated_client():
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with TestingSessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def tenant_client():
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with TestingSessionLocal() as session:
            yield session

    async with TestingSessionLocal() as session:
        first_user = User(
            id=101,
            email="first-tenant@example.com",
            hashed_password="unused",
        )
        second_user = User(
            id=102,
            email="second-tenant@example.com",
            hashed_password="unused",
        )
        session.add_all([first_user, second_user])
        await session.commit()

    active_user = {"value": first_user}

    async def override_current_user():
        return active_user["value"]

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_current_user
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as test_client:
        yield test_client, active_user, first_user, second_user

    app.dependency_overrides.clear()
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
