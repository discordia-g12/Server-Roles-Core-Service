import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import tests.db_utils as db_utils
from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app


@pytest.fixture
async def db_session():
    async with db_utils.TestingSessionLocal() as session:
        yield session

@pytest.fixture(autouse=True, scope="session")
def setup_database():
    url = make_url(settings.database_url)
    default_db = url.database
    test_db_name = f"{default_db}_test"

    async def init_db():
        
        
        # Connect to default database with AUTOCOMMIT to create the test database
        sys_engine = create_async_engine(settings.database_url, isolation_level="AUTOCOMMIT")
        async with sys_engine.connect() as sys_conn:
            # Force disconnect any existing connections to the test db if it was left over
            await sys_conn.execute(text(f"""
                SELECT pg_terminate_backend(pg_stat_activity.pid)
                FROM pg_stat_activity
                WHERE pg_stat_activity.datname = '{test_db_name}'
                AND pid <> pg_backend_pid();
            """))
            await sys_conn.execute(text(f'DROP DATABASE IF EXISTS {test_db_name}'))
            await sys_conn.execute(text(f'CREATE DATABASE {test_db_name}'))
        await sys_engine.dispose()

        # Create engine pointing to the new test_db
        test_url = settings.database_url.replace(f"/{default_db}", f"/{test_db_name}")
        
        db_utils.test_engine = create_async_engine(test_url, poolclass=NullPool)
        db_utils.TestingSessionLocal = async_sessionmaker(
            db_utils.test_engine, expire_on_commit=False, class_=AsyncSession
        )

        async def override_get_db():
            async with db_utils.TestingSessionLocal() as session:
                yield session

        app.dependency_overrides[get_db] = override_get_db

        # Create tables
        async with db_utils.test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(init_db())
    
    yield

    async def cleanup_db():
        
        # Dispose the test engine so it releases all connections
        await db_utils.test_engine.dispose()
        
        # Connect to default database to drop the test database
        sys_engine = create_async_engine(settings.database_url, isolation_level="AUTOCOMMIT")
        async with sys_engine.connect() as sys_conn:
            await sys_conn.execute(text(f"""
                SELECT pg_terminate_backend(pg_stat_activity.pid)
                FROM pg_stat_activity
                WHERE pg_stat_activity.datname = '{test_db_name}'
                AND pid <> pg_backend_pid();
            """))
            await sys_conn.execute(text(f'DROP DATABASE IF EXISTS {test_db_name}'))
        await sys_engine.dispose()

    asyncio.run(cleanup_db())

@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.fixture(autouse=True)
def fake_storage(monkeypatch):
    """Ningún test le pega a S3: las subidas devuelven una URL fake y se registran acá."""
    calls = {"uploaded": [], "deleted": []}

    def fake_upload(contents: bytes, prefix: str, content_type: str = "image/webp") -> str:
        url = f"https://fake-bucket.s3.amazonaws.com/{prefix}/{len(calls['uploaded'])}.webp"
        calls["uploaded"].append({"url": url, "contents": contents, "prefix": prefix})
        return url

    def fake_delete(url: str | None) -> None:
        calls["deleted"].append(url)

    monkeypatch.setattr("app.services.storage.upload_image", fake_upload)
    monkeypatch.setattr("app.services.storage.delete_image", fake_delete)
    return calls
