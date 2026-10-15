"""Rotas públicas (sem login): o cliente envia o vídeo e acompanha a entrega pelo link.

Tudo aqui é acessado pelo `share_token` do pedido, nunca pelo id interno, e só mostra o que
é do cliente: situação, prazo e, depois de entregue, vídeo, números, devolutiva e relatório.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.videos import ALLOWED, export_path, frame_bytes, slug, store_upload
from app.config import get_settings
from app.db import Video, get_db
from app.services import overlay_timeline, report_html
from swimcv.contracts import RaceInfo, Stroke
from swimcv.report.build import build_report

router = APIRouter(prefix="/api/public", tags=["public"])

STROKE_PT = {Stroke.FREESTYLE: "livre", Stroke.BREASTSTROKE: "peito"}


def by_token(token: str, db: Session) -> Video:
    v = db.scalar(select(Video).where(Video.share_token == token))
    if v is None:
        raise HTTPException(404, "link não encontrado")
    return v


@router.post("/orders", status_code=201)
async def create_order(
    file: UploadFile = File(...),
    name: str = Form(..., min_length=2, max_length=200),
    email: str = Form("", max_length=200),
    phone: str = Form("", max_length=40),
    stroke: Stroke = Form(Stroke.FREESTYLE),
    pool_length: int = Form(25),
    distance: int = Form(25),
    notes: str = Form("", max_length=1000),
    website: str = Form(""),  # armadilha para robôs: pessoas não veem este campo
    db: Session = Depends(get_db),
) -> dict:
    if website:
        raise HTTPException(400, "envio recusado")
    if not (email.strip() or phone.strip()):
        raise HTTPException(422, "informe e-mail ou WhatsApp para receber a análise")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED:
        raise HTTPException(422, f"formato {suffix or '?'} não aceito; use MP4 ou MOV")
    if pool_length not in (25, 50):
        raise HTTPException(422, "piscina de 25 ou 50 m")
    if distance not in (25, 50, 100) or distance % pool_length:
        raise HTTPException(422, "distância de 25, 50 ou 100 m, múltipla da piscina")
    race = RaceInfo(stroke=stroke, distance=distance, pool_length=pool_length)
    now = datetime.now(UTC)
    v = Video(
        title=f"{name.strip()} · {distance} m {STROKE_PT.get(stroke, '')}".strip(),
        athlete=name.strip(),
        race=race.model_dump(mode="json"),
        status="uploaded",
        warnings=[],
        origin="client",
        customer_name=name.strip(),
        customer_email=email.strip() or None,
        customer_phone=phone.strip() or None,
        customer_notes=notes.strip() or None,
        order_status="new",
        due_at=now + timedelta(hours=get_settings().turnaround_hours),
    )
    await store_upload(db, v, file, suffix, get_settings().public_max_upload_mb)
    return {"token": v.share_token, "path": f"/r/{v.share_token}", "due_at": v.due_at.isoformat()}


@router.get("/r/{token}")
def order_status(token: str, db: Session = Depends(get_db)) -> dict:
    v = by_token(token, db)
    delivered = v.order_status == "delivered"
    out = {
        "title": v.title,
        "first_name": (v.customer_name or v.athlete or "").split(" ")[0] or None,
        "race": v.race,
        "status": v.order_status or "new",
        "video_status": v.status,
        "created_at": v.created_at.isoformat() if v.created_at else None,
        "due_at": v.due_at.isoformat() if v.due_at else None,
        "delivered_at": v.delivered_at.isoformat() if v.delivered_at else None,
        "delivered": delivered,
        "error": v.error if v.status in ("rejected", "failed") else None,
    }
    if delivered:
        rep = build_report(
            overlay_timeline(db, v), [], feedback=v.feedback, tech_notes=v.tech_notes or []
        )
        out |= {
            "feedback": rep["feedback"],
            "lead": rep["lead"],
            "table": rep["table"],
            "insights": rep["insights"],
            "notes": rep["notes"],
            "technique": [
                c | {"image": _frame_url(token, c["frame"], c["zoom"])} for c in rep["technique"]
            ],
            "has_video": v.export_status == "done" and _export(v).exists(),
            "video_url": f"/api/public/r/{token}/video.mp4",
            "report_url": f"/api/public/r/{token}/report.html",
        }
    return out


def _export(v: Video) -> Path:
    return export_path(v.id)


def _delivered(token: str, db: Session) -> Video:
    v = by_token(token, db)
    if v.order_status != "delivered":
        raise HTTPException(404, "ainda não entregue")
    return v


@router.get("/r/{token}/video.mp4")
def order_video(token: str, db: Session = Depends(get_db)) -> FileResponse:
    v = _delivered(token, db)
    f = _export(v)
    if not f.exists():
        raise HTTPException(404, "vídeo ainda não gerado")
    return FileResponse(f, media_type="video/mp4", filename=f"{slug(v.title)}-fluxi-swim.mp4")


@router.get("/r/{token}/report.html", response_class=HTMLResponse)
def order_report(token: str, db: Session = Depends(get_db)) -> HTMLResponse:
    v = _delivered(token, db)
    return HTMLResponse(report_html(db, v, frame_url=lambda n, z=None: _frame_url(token, n, z)))


@router.get("/r/{token}/frames/{n}.jpg")
def order_frame(
    token: str,
    n: int,
    mx: float | None = None,
    my: float | None = None,
    db: Session = Depends(get_db),
) -> Response:
    """Só os quadros das observações técnicas confirmadas de um pedido entregue."""
    v = _delivered(token, db)
    if n not in {x["frame"] for x in v.tech_notes or [] if x.get("confirmed")}:
        raise HTTPException(404, "quadro não disponível")
    return Response(frame_bytes(v.id, n, mx, my), media_type="image/jpeg")


def _frame_url(token: str, n: int, zoom: list | None) -> str:
    q = f"?mx={zoom[0]:.0f}&my={zoom[1]:.0f}" if zoom else ""
    return f"/api/public/r/{token}/frames/{n}.jpg{q}"
