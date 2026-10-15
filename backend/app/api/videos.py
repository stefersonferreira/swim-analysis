"""Vídeos: upload, lista, dados da prova e arquivos de mídia para a revisão."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import Video, get_db
from app.services import audit, feedback_draft
from swimcv.contracts import RaceInfo
from swimcv.ingest.frames import FrameReaderCache, read_frame_table
from swimcv.report.build import clean_feedback
from swimcv.storage import VideoPaths

router = APIRouter(prefix="/api/videos", tags=["videos"])
readers = FrameReaderCache()
ALLOWED = {".mp4", ".mov", ".m4v", ".mkv"}
IMMUTABLE = {"Cache-Control": "public, max-age=31536000, immutable"}


def paths_for(video_id: str) -> VideoPaths:
    return VideoPaths.for_video(get_settings().data_dir, video_id)


def get_video(video_id: str, db: Session) -> Video:
    v = db.get(Video, video_id)
    if v is None:
        raise HTTPException(404, "vídeo não encontrado")
    return v


def require_ready(v: Video) -> None:
    if v.status != "ready":
        raise HTTPException(409, f"vídeo ainda não está pronto (status: {v.status})")


def video_dict(v: Video) -> dict:
    return {
        "id": v.id,
        "title": v.title,
        "athlete": v.athlete,
        "status": v.status,
        "error": v.error,
        "warnings": v.warnings or [],
        "race": v.race,
        "meta": v.meta,
        "has_calibration": bool(v.calibration),
        "calibration_ok": calibration_accepted(v),
        "pool_id": v.pool_id,
        "analysis_status": v.analysis_status or "idle",
        "analysis_notes": v.analysis_notes or [],
        "strokes_partial": bool(v.strokes_partial),
        "review_notes": v.review_notes or [],
        "analyzed_at": v.analyzed_at.isoformat() if v.analyzed_at else None,
        "export_status": v.export_status or "idle",
        "export_progress": v.export_progress,
        "export_error": v.export_error,
        "exported_at": v.exported_at.isoformat() if v.exported_at else None,
        "created_at": v.created_at.isoformat() if v.created_at else None,
        "order": order_dict(v),
    }


def order_dict(v: Video) -> dict:
    return {
        "origin": v.origin or "coach",
        "status": v.order_status or "new",
        "customer_name": v.customer_name,
        "customer_email": v.customer_email,
        "customer_phone": v.customer_phone,
        "customer_notes": v.customer_notes,
        "due_at": v.due_at.isoformat() if v.due_at else None,
        "delivered_at": v.delivered_at.isoformat() if v.delivered_at else None,
        "paid": bool(v.paid),
        "share_path": f"/r/{v.share_token}",
        "feedback": v.feedback,
        "tech_notes": v.tech_notes or [],
    }


def calibration_accepted(v: Video) -> bool:
    return bool(v.calibration) and any(r.get("accepted") for r in v.calibration.get("results", []))


def enqueue_ingest(video_id: str) -> None:
    from app.worker import ingest

    ingest.delay(video_id)


def enqueue_analysis(db: Session, v: Video) -> bool:
    """Põe a análise automática na fila se houver calibração aceita e raia informada."""
    if v.status != "ready" or not calibration_accepted(v) or not (v.race or {}).get("lane"):
        return False
    from app.worker import analyze

    v.analysis_status, v.analysis_notes = "queued", []
    db.commit()
    analyze.delay(v.id)
    db.refresh(v)
    return True


@router.post("", status_code=201)
async def upload_video(
    file: UploadFile = File(...),
    race: str = Form(..., description="JSON de RaceInfo"),
    title: str = Form(""),
    athlete: str = Form(""),
    db: Session = Depends(get_db),
) -> dict:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED:
        raise HTTPException(422, f"formato {suffix or '?'} não aceito; use MP4 ou MOV")
    try:
        race_info = RaceInfo.model_validate(json.loads(race))
    except (ValueError, ValidationError) as exc:
        raise HTTPException(422, f"dados da prova inválidos: {exc}") from exc

    v = Video(
        title=title or (file.filename or "Prova"),
        athlete=athlete or None,
        race=race_info.model_dump(mode="json"),
        status="uploaded",
        warnings=[],
    )
    await store_upload(db, v, file, suffix, get_settings().max_upload_mb)
    return video_dict(v)


async def store_upload(db: Session, v: Video, file: UploadFile, suffix: str, max_mb: int) -> None:
    """Grava o arquivo enviado em partes (sem carregar tudo na memória) e põe na fila."""
    limit = max_mb * 1024 * 1024
    db.add(v)
    db.flush()
    paths = paths_for(v.id).ensure()
    dst = paths.original(suffix)
    written = 0
    with dst.open("wb") as out:
        while chunk := await file.read(4 * 1024 * 1024):
            written += len(chunk)
            if written > limit:
                out.close()
                shutil.rmtree(paths.root, ignore_errors=True)
                db.rollback()
                raise HTTPException(413, f"arquivo maior que {max_mb} MB")
            out.write(chunk)
    db.commit()
    enqueue_ingest(v.id)
    db.refresh(v)


@router.get("")
def list_videos(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(Video).order_by(Video.created_at.desc()))
    return [video_dict(v) for v in rows]


@router.get("/{video_id}")
def read_video(video_id: str, db: Session = Depends(get_db)) -> dict:
    return video_dict(get_video(video_id, db))


@router.put("/{video_id}/race")
def update_race(video_id: str, race: RaceInfo, db: Session = Depends(get_db)) -> dict:
    v = get_video(video_id, db)
    before = v.race
    v.race = race.model_dump(mode="json")
    audit(db, v.id, "race", None, "update", before, v.race)
    db.commit()
    if (before or {}).get("lane") != race.lane or (before or {}).get("stroke") != race.stroke:
        enqueue_analysis(db, v)
    return video_dict(v)


class FinalOptions(BaseModel):
    """Como o vídeo final apresenta o que foi medido."""

    strokes_partial: bool = False
    notes: list[str] = Field(default_factory=list, max_length=6)


@router.put("/{video_id}/final-options")
def update_final_options(video_id: str, opts: FinalOptions, db: Session = Depends(get_db)) -> dict:
    v = get_video(video_id, db)
    notes = [n.strip()[:120] for n in opts.notes if n.strip()]
    before = {"strokes_partial": bool(v.strokes_partial), "notes": v.review_notes or []}
    v.strokes_partial, v.review_notes = opts.strokes_partial, notes
    after = {"strokes_partial": v.strokes_partial, "notes": notes}
    audit(db, v.id, "video", v.id, "final_options", before, after)
    db.commit()
    return video_dict(v)


class OrderUpdate(BaseModel):
    status: Literal["new", "reviewing", "delivered"] | None = None
    paid: bool | None = None
    customer_name: str | None = Field(None, max_length=200)
    customer_email: str | None = Field(None, max_length=200)
    customer_phone: str | None = Field(None, max_length=40)


@router.put("/{video_id}/order")
def update_order(video_id: str, body: OrderUpdate, db: Session = Depends(get_db)) -> dict:
    v = get_video(video_id, db)
    before = order_dict(v)
    data = body.model_dump(exclude_unset=True)
    if "status" in data:
        v.order_status = data.pop("status")
        v.delivered_at = datetime.now(UTC) if v.order_status == "delivered" else None
    for k, val in data.items():
        setattr(v, k, (val.strip() or None) if isinstance(val, str) else val)
    audit(db, v.id, "order", v.id, "update", before, order_dict(v))
    db.commit()
    return video_dict(v)


class Feedback(BaseModel):
    summary: str = Field("", max_length=2000)
    strengths: list[str] = Field(default_factory=list, max_length=12)
    improve: list[str] = Field(default_factory=list, max_length=12)
    drills: list[str] = Field(default_factory=list, max_length=12)


@router.put("/{video_id}/feedback")
def save_feedback(video_id: str, fb: Feedback, db: Session = Depends(get_db)) -> dict:
    v = get_video(video_id, db)
    before = v.feedback
    v.feedback = clean_feedback(fb.model_dump())
    if v.order_status == "new" and v.feedback:
        v.order_status = "reviewing"
    audit(db, v.id, "feedback", v.id, "update", before, v.feedback)
    db.commit()
    return video_dict(v)


@router.post("/{video_id}/feedback/draft")
def draft(video_id: str, db: Session = Depends(get_db)) -> dict:
    v = get_video(video_id, db)
    require_ready(v)
    return feedback_draft(db, v)


@router.post("/{video_id}/deliver")
def deliver(video_id: str, db: Session = Depends(get_db)) -> dict:
    """Marca como entregue: o link do cliente passa a mostrar vídeo, números e devolutiva."""
    v = get_video(video_id, db)
    require_ready(v)
    if not v.feedback:
        raise HTTPException(409, "escreva a devolutiva antes de entregar")
    before = order_dict(v)
    v.order_status, v.delivered_at = "delivered", datetime.now(UTC)
    audit(db, v.id, "order", v.id, "deliver", before, order_dict(v))
    db.commit()
    return video_dict(v)


@router.post("/{video_id}/analyze", status_code=202)
def analyze_video(video_id: str, db: Session = Depends(get_db)) -> dict:
    v = get_video(video_id, db)
    require_ready(v)
    if not calibration_accepted(v):
        raise HTTPException(409, "Calibre a piscina antes (aba Calibração).")
    if not (v.race or {}).get("lane"):
        raise HTTPException(409, "Informe a raia do nadador nos dados da prova.")
    enqueue_analysis(db, v)
    return video_dict(v)


@router.post("/{video_id}/export", status_code=202)
def export_video(video_id: str, db: Session = Depends(get_db)) -> dict:
    """Gera o MP4 com a sobreposição Fluxi Swim (no worker)."""
    v = get_video(video_id, db)
    require_ready(v)
    if v.export_status in ("queued", "running"):
        return video_dict(v)
    from app.worker import export

    v.export_status, v.export_progress, v.export_error = "queued", 0.0, None
    db.commit()
    export.delay(v.id)
    db.refresh(v)
    return video_dict(v)


@router.get("/{video_id}/export.mp4")
def export_file(video_id: str, db: Session = Depends(get_db)) -> FileResponse:
    v = get_video(video_id, db)
    f = export_path(video_id)
    if v.export_status != "done" or not f.exists():
        raise HTTPException(404, "o vídeo com a sobreposição ainda não foi gerado")
    return FileResponse(f, media_type="video/mp4", filename=f"{slug(v.title)}-fluxi-swim.mp4")


def export_path(video_id: str) -> Path:
    return paths_for(video_id).root / "export" / "overlay.mp4"


def slug(s: str) -> str:
    import re
    import unicodedata

    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower() or "prova"


@router.post("/{video_id}/reingest", status_code=202)
def reingest(video_id: str, db: Session = Depends(get_db)) -> dict:
    v = get_video(video_id, db)
    readers.drop(v.id)
    shutil.rmtree(paths_for(v.id).root / "analysis", ignore_errors=True)
    shutil.rmtree(paths_for(v.id).root / "export", ignore_errors=True)
    v.status = "uploaded"
    v.analysis_status = "idle"
    v.export_status, v.export_progress, v.export_error = "idle", None, None
    db.commit()
    enqueue_ingest(v.id)
    return video_dict(v)


@router.delete("/{video_id}", status_code=204)
def delete_video(video_id: str, db: Session = Depends(get_db)) -> Response:
    v = get_video(video_id, db)
    readers.drop(v.id)
    db.delete(v)
    db.commit()
    shutil.rmtree(paths_for(video_id).root, ignore_errors=True)
    return Response(status_code=204)


# ---- Mídia ---------------------------------------------------------------------------


@router.get("/{video_id}/proxy.mp4")
def proxy(video_id: str, db: Session = Depends(get_db)) -> FileResponse:
    require_ready(get_video(video_id, db))
    return FileResponse(paths_for(video_id).proxy, media_type="video/mp4")


@router.get("/{video_id}/poster.jpg")
def poster(video_id: str, db: Session = Depends(get_db)) -> FileResponse:
    require_ready(get_video(video_id, db))
    return FileResponse(paths_for(video_id).poster, media_type="image/jpeg")


@router.get("/{video_id}/frames.json")
def frames(video_id: str, db: Session = Depends(get_db)) -> dict:
    require_ready(get_video(video_id, db))
    table = read_frame_table(paths_for(video_id).frames)
    return {"pts": [round(float(p), 6) for p in table["pts"]]}


@router.get("/{video_id}/frames/{n}.jpg")
def frame_jpeg(
    video_id: str,
    n: int,
    mx: float | None = None,
    my: float | None = None,
    db: Session = Depends(get_db),
) -> Response:
    """Quadro exato; com mx/my, o recorte ampliado em volta desse ponto."""
    require_ready(get_video(video_id, db))
    try:
        data = frame_bytes(video_id, n, mx, my)
    except IndexError as exc:
        raise HTTPException(404, str(exc)) from exc
    return Response(data, media_type="image/jpeg", headers=IMMUTABLE)


def frame_bytes(video_id: str, n: int, mx: float | None = None, my: float | None = None) -> bytes:
    p = paths_for(video_id)
    data = readers.get(video_id, p.proxy, p.frames).jpeg(n)
    if mx is None or my is None:
        return data
    import io

    from PIL import Image

    from swimcv.report.technique import zoom_box

    im = Image.open(io.BytesIO(data))
    x0, y0, w, h = zoom_box(im.width, im.height, mx, my)
    out = io.BytesIO()
    im.crop((x0, y0, x0 + w, y0 + h)).save(out, "JPEG", quality=88)
    return out.getvalue()


@router.get("/{video_id}/waveform.json")
def waveform(video_id: str, db: Session = Depends(get_db)) -> Response:
    require_ready(get_video(video_id, db))
    p = paths_for(video_id).waveform
    if not p.exists():
        return Response('{"bins_per_s":100,"t0":0,"peaks":[]}', media_type="application/json")
    return FileResponse(p, media_type="application/json")
