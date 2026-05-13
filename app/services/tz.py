"""Helper de fuso horário — sempre America/Bahia."""
from datetime import datetime
from zoneinfo import ZoneInfo

BAHIA = ZoneInfo("America/Bahia")


def now_bahia() -> datetime:
    """Datetime naive em horário de Bahia (UTC-3).
    Usar como replacement de datetime.utcnow() em todos os models/services."""
    return datetime.now(BAHIA).replace(tzinfo=None)
