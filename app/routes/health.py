"""Healthcheck endpoint."""
from fastapi import APIRouter
from app.config import get_settings

router = APIRouter()


@router.get("/health")
async def healthcheck():
    s = get_settings()
    return {
        "status": "ok",
        "app": s.app_name,
        "env": s.app_env,
    }
