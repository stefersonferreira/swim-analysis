"""Regras que ligam o banco aos módulos do pipeline (sem HTTP aqui)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import AuditLog, Event, Video
from swimcv import contracts as c
from swimcv.analyze import AnalysisFiles, load_homographies
from swimcv.calibration import grid_lines, solve
from swimcv.metrics import athlete_events, compare_lanes, compute_metrics, resolve_positions
from swimcv.overlay import build_timeline
from swimcv.storage import VideoPaths

LOW_CONFIDENCE = 0.35
REJECT_WINDOW_S = 0.15


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
        lane=e.lane,
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
        "lane": e.lane,
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


def video_paths(video_id: str) -> VideoPaths:
    return VideoPaths.for_video(get_settings().data_dir, video_id)


def metrics_payload(db: Session, video: Video) -> dict:
    """Eventos com posição resolvida + métricas + alertas, prontos para a tela."""
    race = race_of(video)
    rows = live_events(db, video.id)
    H = load_homographies(video_paths(video.id))
    resolved = resolve_positions([to_contract(e) for e in rows], calibration_of(video), H)
    report = compute_metrics(race, athlete_events(resolved, None, race.lane))
    metrics = [m.model_dump(mode="json") for m in report.metrics]
    x_by_id = {e.id: e.x_m for e in resolved}
    alerts = [a.model_dump(mode="json") for a in report.alerts]
    weak = [e for e in rows if e.source == "auto" and e.confidence < LOW_CONFIDENCE]
    for e in weak:
        alerts.append(
            {
                "kind": "low_confidence",
                "length_index": None,
                "t_from": e.t,
                "t_to": e.t,
                "event_ids": [e.id],
                "message": f"Evento automático com baixa confiança ({e.confidence:.0%}): confira",
            }
        )
    return {
        "events": [event_dict(e, x_by_id.get(e.id)) for e in rows],
        "metrics": metrics,
        "alerts": alerts,
        "race": race.model_dump(mode="json"),
        # quadro comparativo quando há eventos marcados por raia
        "lanes": [r.as_dict() for r in compare_lanes(race, resolved)]
        if any(e.lane is not None for e in resolved)
        else [],
    }


def overlay_timeline(db: Session, video: Video) -> dict:
    """Linha do tempo da sobreposição (navegador e MP4 usam a mesma)."""
    import pandas as pd

    race = race_of(video)
    paths = video_paths(video.id)
    H = load_homographies(paths)
    rows = live_events(db, video.id)
    resolved = resolve_positions([to_contract(e) for e in rows], calibration_of(video), H)
    report = compute_metrics(race, athlete_events(resolved, None, race.lane))
    traj = None
    f = AnalysisFiles.of(paths).trajectory
    if f.exists():
        df = pd.read_parquet(f)
        cols = [c for c in ("t", "head_x", "head_img_x", "head_img_y") if c in df]
        traj = {c: df[c].to_numpy() for c in cols}
    meta = video.meta or {}
    return build_timeline(
        race,
        resolved,
        report,
        title=video.title,
        athlete=video.athlete,
        width=meta.get("proxy_width", 1920),
        height=meta.get("proxy_height", 1080),
        duration_s=meta.get("duration_s", 0.0),
        trajectory=traj,
        notes=video.review_notes or [],
        strokes_partial=bool(video.strokes_partial),
    )


def replace_auto_events(db: Session, video: Video, events: list[c.Event]) -> int:
    """Troca os eventos automáticos que ninguém tocou pelos novos.

    - automático editado pela pessoa vira 'manual' e fica;
    - automático apagado pela pessoa conta como rejeitado: não volta numa nova análise.
    """
    q = select(Event).where(Event.video_id == video.id, Event.source == "auto")
    old = list(db.scalars(q))
    rejected = [(e.type, e.t) for e in old if e.deleted]
    manual = [(e.type, e.t) for e in live_events(db, video.id) if e.source == "manual"]
    for e in old:
        if not e.deleted:
            db.delete(e)
    n = 0
    for ev in events:
        if any(t == ev.type.value and abs(tt - ev.t) < REJECT_WINDOW_S for t, tt in rejected):
            continue
        # já existe um evento da pessoa (criado ou corrigido) desse tipo ali perto
        if any(t == ev.type.value and abs(tt - ev.t) < REJECT_WINDOW_S for t, tt in manual):
            continue
        db.add(
            Event(
                video_id=video.id,
                type=ev.type.value,
                frame=ev.frame,
                t=ev.t,
                image_x=ev.image_xy[0] if ev.image_xy else None,
                image_y=ev.image_xy[1] if ev.image_xy else None,
                mark_m=ev.mark_m,
                confidence=ev.confidence,
                source="auto",
                author="auto",
            )
        )
        n += 1
    audit(db, video.id, "analysis", None, "auto_events", {"replaced": len(old)}, {"created": n})
    return n


def has_start_signal(db: Session, video_id: str) -> bool:
    return any(e.type == "start_signal" for e in live_events(db, video_id))


def mark_analyzed(video: Video, status: str, notes: list[str]) -> None:
    video.analysis_status = status
    video.analysis_notes = notes
    video.analyzed_at = datetime.now(UTC)


def calibration_payload(video: Video) -> dict:
    cal = calibration_of(video) or c.Calibration()
    grids = {str(r.frame): grid_lines(cal, r) for r in cal.results if r.homography is not None}
    return {"calibration": cal.model_dump(mode="json"), "grids": grids}


def save_calibration(db: Session, video: Video, cal: c.Calibration) -> c.Calibration:
    solved = solve(cal)
    # homografias por quadro antigas não valem mais; a próxima análise refaz
    AnalysisFiles.of(video_paths(video.id)).homographies.unlink(missing_ok=True)
    before = video.calibration
    video.calibration = solved.model_dump(mode="json")
    audit(db, video.id, "calibration", None, "update", before, video.calibration)
    return solved


def report_html(db: Session, video: Video) -> str:
    """Relatório imprimível: mesmos números do vídeo (parte da mesma linha do tempo)."""
    from swimcv.report import build_report, render_html

    tl = overlay_timeline(db, video)
    events = [to_contract(e) for e in live_events(db, video.id)]
    return render_html(build_report(tl, events))
