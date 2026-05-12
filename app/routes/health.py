"""Healthcheck endpoint — usado pelo Coolify pra saber se o app subiu."""
from fastapi import APIRouter
import redis.asyncio as aioredis
from app.config import get_settings
from app.database import ping_db

router = APIRouter()


@router.get("/health")
async def healthcheck():
    """Status geral. 200 sempre que o app está vivo, mesmo com dependências falhando."""
    s = get_settings()

    # DB ping
    db_ok = await ping_db()

    # Redis ping
    redis_ok = False
    try:
        r = aioredis.from_url(s.redis_url, socket_connect_timeout=2)
        await r.ping()
        redis_ok = True
        await r.aclose()
    except Exception:
        redis_ok = False

    return {
        "status": "ok" if (db_ok and redis_ok) else "degraded",
        "app": s.app_name,
        "env": s.app_env,
        "checks": {
            "db": "ok" if db_ok else "fail",
            "redis": "ok" if redis_ok else "fail",
        },
    }


@router.get("/health/live")
async def liveness():
    """Liveness: o processo está vivo? Sempre 200 enquanto FastAPI tiver subindo."""
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness():
    """Readiness: app + dependências OK? 503 se algo falhar."""
    from fastapi import HTTPException
    db_ok = await ping_db()
    if not db_ok:
        raise HTTPException(status_code=503, detail="db unavailable")
    return {"status": "ready"}
