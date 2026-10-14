"""Worker Celery: roda os módulos do pipeline fora do processo da API."""

from __future__ import annotations

import shutil
import subprocess

from celery import Celery

from app.config import get_settings
from app.db import Video, new_session
from app.services import (
    calibration_of,
    has_start_signal,
    mark_analyzed,
    race_of,
    replace_auto_events,
)
from swimcv import contracts as c
from swimcv.analyze import AnalysisError, detect_start_signal
from swimcv.analyze import run as run_analysis
from swimcv.ingest import IngestError, ingest_video
from swimcv.ingest.frames import read_frame_table
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
        paths = VideoPaths.for_video(get_settings().data_dir, video_id)
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
        _auto_start(db, video, paths)
        return "ready"
    finally:
        db.close()


def _auto_start(db, video: Video, paths: VideoPaths) -> None:
    """Largada pelo áudio logo depois da ingestão (não precisa de calibração)."""
    if not video.meta or not video.meta.get("has_audio") or has_start_signal(db, video.id):
        return
    try:
        t, conf, _ = detect_start_signal(paths)
    except Exception:  # áudio estranho não pode derrubar a ingestão
        return
    if t is None:
        return
    pts = read_frame_table(paths.frames)["pts"].to_numpy()
    frame = int(abs(pts - t).argmin())
    replace_auto_events(
        db,
        video,
        [
            c.Event(
                type=c.EventType.START_SIGNAL,
                frame=frame,
                t=t,
                confidence=conf,
                source=c.EventSource.AUTO,
            )
        ],
    )
    db.commit()


@celery_app.task(name="swim.analyze")
def analyze(video_id: str) -> str:
    """Análise automática completa: trajetória e eventos."""
    db = new_session()
    try:
        video = db.get(Video, video_id)
        if video is None or video.status != "ready":
            return "not_ready"
        video.analysis_status, video.analysis_notes = "running", []
        db.commit()
        paths = VideoPaths.for_video(get_settings().data_dir, video_id)
        try:
            cal = calibration_of(video)
            if cal is None:
                raise AnalysisError("Calibre a piscina antes (aba Calibração).")
            events, notes = run_analysis(paths, race_of(video), cal)
        except AnalysisError as exc:
            mark_analyzed(video, "failed", [str(exc)])
            db.commit()
            return "failed"
        except Exception as exc:
            mark_analyzed(video, "failed", [f"Erro inesperado na análise: {exc}"[:500]])
            db.commit()
            raise
        n = replace_auto_events(db, video, events)
        mark_analyzed(video, "done", [f"{n} eventos automáticos gerados.", *notes])
        db.commit()
        return "done"
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
