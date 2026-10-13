from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    db.execute(text("select 1"))
    return {"status": "ok"}


@router.get("/system/worker")
def worker_info() -> dict:
    """Pergunta ao worker se ele está vivo e se enxerga a GPU."""
    from app.worker import system_info

    if get_settings().task_always_eager:
        return {"worker": "eager", **system_info()}
    try:
        res = system_info.delay().get(timeout=10)
    except Exception as exc:  # worker fora do ar
        return {"worker": "offline", "error": str(exc)}
    return {"worker": "online", **res}
