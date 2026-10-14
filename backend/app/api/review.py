"""Revisão: eventos (marcação manual), métricas ao vivo, calibração e perfis de piscina."""

from __future__ import annotations

from bisect import bisect_left

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.videos import enqueue_analysis, get_video, paths_for, require_ready, video_dict
from app.db import Event, Pool, get_db
from app.services import (
    audit,
    calibration_of,
    calibration_payload,
    event_dict,
    metrics_payload,
    overlay_timeline,
    save_calibration,
)
from swimcv import contracts as c
from swimcv.analyze import AnalysisFiles, load_homographies
from swimcv.calibration import grid_lines
from swimcv.ingest.frames import read_frame_table

router = APIRouter(prefix="/api", tags=["review"])


class EventIn(BaseModel):
    type: c.EventType
    frame: int = Field(ge=0)
    image_xy: tuple[float, float] | None = None
    mark_m: float | None = None
    lane: int | None = Field(None, ge=1, le=10)


class EventUpdate(BaseModel):
    id: str
    type: c.EventType | None = None
    frame: int | None = Field(None, ge=0)
    image_xy: tuple[float, float] | None = None
    clear_image_xy: bool = False
    mark_m: float | None = None
    lane: int | None = Field(None, ge=1, le=10)
    clear_lane: bool = False


class EventsPatch(BaseModel):
    create: list[EventIn] = Field(default_factory=list)
    update: list[EventUpdate] = Field(default_factory=list)
    delete: list[str] = Field(default_factory=list)
    author: str | None = None


def _pts_lookup(video_id: str) -> list[float]:
    return read_frame_table(paths_for(video_id).frames)["pts"].tolist()


def _pts(pts: list[float], frame: int) -> float:
    if frame >= len(pts):
        raise HTTPException(422, f"quadro {frame} não existe (vídeo tem {len(pts)} quadros)")
    return float(pts[frame])


@router.get("/videos/{video_id}/events")
def get_events(video_id: str, db: Session = Depends(get_db)) -> dict:
    v = get_video(video_id, db)
    return metrics_payload(db, v)


@router.get("/videos/{video_id}/metrics")
def get_metrics(video_id: str, db: Session = Depends(get_db)) -> dict:
    return get_events(video_id, db)


@router.patch("/videos/{video_id}/events")
def patch_events(video_id: str, body: EventsPatch, db: Session = Depends(get_db)) -> dict:
    """Cria, altera e apaga eventos em lote. O tempo vem sempre da tabela de quadros."""
    v = get_video(video_id, db)
    require_ready(v)
    pts = _pts_lookup(video_id)
    created: list[str] = []
    for e in body.create:
        row = Event(
            video_id=v.id,
            type=e.type.value,
            frame=e.frame,
            t=_pts(pts, e.frame),
            image_x=e.image_xy[0] if e.image_xy else None,
            image_y=e.image_xy[1] if e.image_xy else None,
            mark_m=e.mark_m,
            lane=e.lane,
            source="manual",
            author=body.author,
        )
        db.add(row)
        db.flush()
        created.append(row.id)
        audit(db, v.id, "event", row.id, "create", None, event_dict(row), body.author)
    for u in body.update:
        row = db.get(Event, u.id)
        if row is None or row.video_id != v.id or row.deleted:
            raise HTTPException(404, f"evento {u.id} não encontrado")
        before = event_dict(row)
        if u.type is not None:
            row.type = u.type.value
        if u.frame is not None:
            row.frame, row.t = u.frame, _pts(pts, u.frame)
        if u.clear_image_xy:
            row.image_x = row.image_y = None
        elif u.image_xy is not None:
            row.image_x, row.image_y = u.image_xy
        if u.mark_m is not None:
            row.mark_m = u.mark_m
        if u.clear_lane:
            row.lane = None
        elif u.lane is not None:
            row.lane = u.lane
        row.source = "manual"
        audit(db, v.id, "event", row.id, "update", before, event_dict(row), body.author)
    for event_id in body.delete:
        row = db.get(Event, event_id)
        if row is None or row.video_id != v.id:
            raise HTTPException(404, f"evento {event_id} não encontrado")
        row.deleted = True  # nunca apaga de verdade: o histórico vira dado de treino
        audit(db, v.id, "event", row.id, "delete", event_dict(row), None, body.author)
    db.commit()
    return {**metrics_payload(db, v), "created_ids": created}


# ---- Calibração --------------------------------------------------------------------------


@router.get("/videos/{video_id}/calibration")
def get_calibration(video_id: str, db: Session = Depends(get_db)) -> dict:
    v = get_video(video_id, db)
    if v.calibration is None and v.pool_id:
        pool = db.get(Pool, v.pool_id)
        if pool:
            v.calibration = c.Calibration(
                pool=c.PoolProfile.model_validate(pool.profile)
            ).model_dump(mode="json")
    return calibration_payload(v)


class CalibrationIn(BaseModel):
    pool: c.PoolProfile
    anchors: list[c.Anchor]
    pool_id: int | None = None


@router.put("/videos/{video_id}/calibration")
def put_calibration(video_id: str, body: CalibrationIn, db: Session = Depends(get_db)) -> dict:
    v = get_video(video_id, db)
    require_ready(v)
    n = v.meta["n_frames"] if v.meta else 0
    for a in body.anchors:
        if not 0 <= a.frame < n:
            raise HTTPException(422, f"âncora no quadro {a.frame} fora do vídeo")
    if body.pool_id is not None:
        if db.get(Pool, body.pool_id) is None:
            raise HTTPException(404, "piscina não encontrada")
        v.pool_id = body.pool_id
    save_calibration(db, v, c.Calibration(pool=body.pool, anchors=body.anchors))
    db.commit()
    enqueue_analysis(db, v)
    return {**calibration_payload(v), **metrics_payload(db, v), "video": video_dict(v)}


@router.get("/videos/{video_id}/trajectory.json")
def trajectory(video_id: str, db: Session = Depends(get_db)) -> dict:
    get_video(video_id, db)
    tr = AnalysisFiles.of(paths_for(video_id)).trajectory
    if not tr.exists():
        return {"frames": []}
    df = pd.read_parquet(tr)
    cols = ["frame", "head_x", "confidence", "head_img_x", "head_img_y"]
    return {"frames": df[cols].round(3).to_dict(orient="list")}


@router.get("/videos/{video_id}/overlay.json")
def overlay(video_id: str, db: Session = Depends(get_db)) -> dict:
    """Balões, relógio e números da sobreposição ao vivo (mesmos do MP4 exportado)."""
    v = get_video(video_id, db)
    require_ready(v)
    return overlay_timeline(db, v)


@router.get("/videos/{video_id}/grid/{frame}")
def frame_grid(video_id: str, frame: int, db: Session = Depends(get_db)) -> dict:
    """Grade da piscina no quadro pedido (com câmera em movimento, cada quadro tem a sua)."""
    v = get_video(video_id, db)
    cal = calibration_of(v)
    if cal is None:
        return {"lines": []}
    H = load_homographies(paths_for(video_id))
    if H is not None and 0 <= frame < len(H):
        res = c.AnchorResult(frame=frame, homography=H[frame].tolist(), accepted=True)
    else:
        ok = [r for r in cal.results if r.accepted and r.homography is not None]
        if not ok:
            return {"lines": []}
        res = min(ok, key=lambda r: abs(r.frame - frame))
    return {"lines": grid_lines(cal, res)}


# ---- Perfis de piscina ---------------------------------------------------------------------


class PoolIn(BaseModel):
    name: str
    profile: c.PoolProfile


@router.get("/pools")
def list_pools(db: Session = Depends(get_db)) -> list[dict]:
    return [
        {"id": p.id, "name": p.name, "profile": p.profile}
        for p in db.scalars(select(Pool).order_by(Pool.name))
    ]


@router.post("/pools", status_code=201)
def create_pool(body: PoolIn, db: Session = Depends(get_db)) -> dict:
    p = Pool(name=body.name, profile=body.profile.model_dump(mode="json"))
    db.add(p)
    db.commit()
    return {"id": p.id, "name": p.name, "profile": p.profile}


@router.post("/videos/{video_id}/calibration/copy-from/{other_id}")
def copy_calibration(video_id: str, other_id: str, db: Session = Depends(get_db)) -> dict:
    """Câmera no mesmo lugar: reaproveita os cliques de outro vídeo da mesma piscina."""
    v, src = get_video(video_id, db), get_video(other_id, db)
    cal = calibration_of(src)
    if cal is None:
        raise HTTPException(409, "o outro vídeo não tem calibração")
    require_ready(v)
    n = v.meta["n_frames"]
    anchors = [a.model_copy(update={"frame": min(a.frame, n - 1)}) for a in cal.anchors]
    save_calibration(db, v, cal.model_copy(update={"anchors": anchors}))
    v.pool_id = src.pool_id
    db.commit()
    enqueue_analysis(db, v)
    return {**calibration_payload(v), **metrics_payload(db, v), "video": video_dict(v)}


def nearest_frame(pts: list[float], t: float) -> int:
    i = bisect_left(pts, t)
    if i == 0:
        return 0
    if i >= len(pts):
        return len(pts) - 1
    return i if pts[i] - t < t - pts[i - 1] else i - 1
