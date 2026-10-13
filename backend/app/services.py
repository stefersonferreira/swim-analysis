"""Regras que ligam o banco aos módulos do pipeline (sem HTTP aqui)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import AuditLog, Event, Video
from swimcv import contracts as c
from swimcv.calibration import grid_lines, solve
from swimcv.metrics import compute_metrics, display, resolve_positions


def race_of(video: Video) -> c.RaceInfo:
    return c.RaceInfo.model_validate(video.race)


def calibration_of(video: Video) -> c.Calibration | None:
    return c.Calibration.model_validate(video.calibration) if video.calibration else None


def to_contract(e: Event) -> c.Event:
    xy = (e.image_x, e.image_y) if e.image_x is not None and e.image_y is not None else None
    return c.Event(
        id=e.id,
        type=c.EventType(e.type),
        frame=e.frame,
        t=e.t,
        image_xy=xy,
        mark_m=e.mark_m,
        confidence=e.confidence,
        source=c.EventSource(e.source),
        author=e.author,
    )


def live_events(db: Session, video_id: str) -> list[Event]:
    q = select(Event).where(Event.video_id == video_id, Event.deleted.is_(False))
    return list(db.scalars(q.order_by(Event.t, Event.frame)))


def event_dict(e: Event, x_m: float | None = None) -> dict:
    return {
        "id": e.id,
        "type": e.type,
        "frame": e.frame,
        "t": e.t,
        "image_xy": [e.image_x, e.image_y] if e.image_x is not None else None,
        "mark_m": e.mark_m,
        "x_m": x_m,
        "confidence": e.confidence,
        "source": e.source,
        "author": e.author,
    }


def audit(
    db: Session,
    video_id: str,
    entity: str,
    entity_id: str | None,
    action: str,
    before: dict | None,
    after: dict | None,
    author: str | None = None,
) -> None:
    db.add(
        AuditLog(
            video_id=video_id,
            entity=entity,
            entity_id=entity_id,
            action=action,
            before=before,
            after=after,
            author=author,
        )
    )


def metrics_payload(db: Session, video: Video) -> dict:
    """Eventos com posição resolvida + métricas + alertas, prontos para a tela."""
    race = race_of(video)
    rows = live_events(db, video.id)
    resolved = resolve_positions([to_contract(e) for e in rows], calibration_of(video))
    report = compute_metrics(race, resolved)
    metrics = []
    for m in report.metrics:
        value, unit = display(m, race.pool_unit)
        metrics.append({**m.model_dump(mode="json"), "display_value": value, "display_unit": unit})
    x_by_id = {e.id: e.x_m for e in resolved}
    return {
        "events": [event_dict(e, x_by_id.get(e.id)) for e in rows],
        "metrics": metrics,
        "alerts": [a.model_dump(mode="json") for a in report.alerts],
        "race": race.model_dump(mode="json"),
    }


def calibration_payload(video: Video) -> dict:
    cal = calibration_of(video) or c.Calibration()
    grids = {str(r.frame): grid_lines(cal, r) for r in cal.results if r.homography is not None}
    return {"calibration": cal.model_dump(mode="json"), "grids": grids}


def save_calibration(db: Session, video: Video, cal: c.Calibration) -> c.Calibration:
    solved = solve(cal)
    before = video.calibration
    video.calibration = solved.model_dump(mode="json")
    audit(db, video.id, "calibration", None, "update", before, video.calibration)
    return solved
