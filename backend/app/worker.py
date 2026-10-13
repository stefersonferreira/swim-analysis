"""Worker Celery: roda os módulos do pipeline fora do processo da API."""

from __future__ import annotations

import shutil
import subprocess

from celery import Celery

from app.config import get_settings
from app.db import Video, new_session
from swimcv.ingest import IngestError, ingest_video
from swimcv.storage import VideoPaths

settings = get_settings()
celery_app = Celery("swim", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_always_eager=settings.task_always_eager,
    task_eager_propagates=False,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
)


@celery_app.task(name="swim.ingest")
def ingest(video_id: str) -> str:
    db = new_session()
    try:
        video = db.get(Video, video_id)
        if video is None:
            return "missing"
        video.status, video.error = "processing", None
        db.commit()
        paths = VideoPaths.for_video(settings.data_dir, video_id)
        try:
            meta, warnings = ingest_video(paths, strict=settings.strict_ingest)
        except IngestError as exc:
            video.status, video.error = "rejected", str(exc)
            db.commit()
            return "rejected"
        except Exception as exc:  # erro inesperado: guarda para o usuário ver
            video.status, video.error = "failed", f"Falha na ingestão: {exc}"[:2000]
            db.commit()
            raise
        video.meta = meta.model_dump(mode="json")
        video.warnings = warnings
        video.status = "ready"
        db.commit()
        return "ready"
    finally:
        db.close()


@celery_app.task(name="swim.system_info")
def system_info() -> dict:
    """Diz se o worker enxerga a GPU (verificação da entrega 0)."""
    info: dict = {"gpu": False, "nvidia_smi": None, "ffmpeg": bool(shutil.which("ffmpeg"))}
    if shutil.which("nvidia-smi"):
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
            capture_output=True,
            text=True,
        )
        if out.returncode == 0 and out.stdout.strip():
            info["gpu"] = True
            info["nvidia_smi"] = out.stdout.strip()
    return info
