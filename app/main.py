from fastapi import FastAPI, Response, status
from sqlalchemy import text

from app.api.internal import router as internal_router
from app.api.moderation import router as moderation_router
from app.api.server import router as server_router
from app.core.exceptions import register_exception_handlers
from app.db import engine

app = FastAPI(title="Server Roles Core Service")
register_exception_handlers(app)


app.include_router(server_router)
app.include_router(moderation_router)
app.include_router(internal_router)

@app.get("/")
def read_root():
    return {"message": "Welcome to Server Roles Core Service API"}

@app.get("/livez")
def livez():
    """Liveness: process is up. No external dependencies checked on purpose."""
    return {"status": "alive"}

@app.get("/readyz")
async def readyz(response: Response):
    """Readiness: process can actually serve traffic (DB reachable)."""
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not ready"}
    return {"status": "ready"}