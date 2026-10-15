"""Quadros-chave e observações técnicas (lista de pontos por fase + sugestão por IA)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.videos import frame_bytes, get_video, require_ready, video_dict
from app.config import get_settings
from app.db import get_db
from app.services import audit, live_events, race_of, to_contract
from swimcv.report import ai
from swimcv.report.technique import catalog, clean_notes, suggest_keyframes

router = APIRouter(prefix="/api/videos", tags=["technique"])


@router.get("/{video_id}/technique")
def technique(video_id: str, db: Session = Depends(get_db)) -> dict:
    v = get_video(video_id, db)
    race = race_of(v)
    evs = [to_contract(e) for e in live_events(db, v.id)]
    return {
        "catalog": catalog(race.stroke),
        "suggestions": suggest_keyframes(race.stroke, evs),
        "notes": v.tech_notes or [],
        "ai_enabled": bool(get_settings().anthropic_api_key),
    }


class Note(BaseModel):
    id: str = Field(..., max_length=40)
    frame: int = Field(..., ge=0)
    t: float
    lane: int | None = Field(None, ge=1, le=10)
    phase: str | None = None
    items: list[str] = Field(default_factory=list, max_length=12)
    text: str = Field("", max_length=600)
    mark: list[float] | None = None
    source: str = "coach"
    confirmed: bool = True


@router.put("/{video_id}/technique")
def save_notes(video_id: str, notes: list[Note], db: Session = Depends(get_db)) -> dict:
    v = get_video(video_id, db)
    if len(notes) > 40:
        raise HTTPException(422, "no máximo 40 quadros")
    before = v.tech_notes
    v.tech_notes = clean_notes(race_of(v).stroke, [n.model_dump() for n in notes])
    audit(db, v.id, "tech_notes", v.id, "update", {"notes": before}, {"notes": v.tech_notes})
    db.commit()
    return video_dict(v) | {"tech_notes": v.tech_notes}


class AIAsk(BaseModel):
    frame: int = Field(..., ge=0)
    phase: str
    lane: int | None = None
    mark: list[float] | None = None


def frame_for_ai(video_id: str, frame: int, mark: list[float] | None) -> bytes:
    """Quadro em JPEG; com um ponto marcado, o recorte em volta dele (o atleta fica maior)."""
    return frame_bytes(video_id, frame, *(mark or (None, None)))


@router.post("/{video_id}/technique/ai")
def ai_suggest(video_id: str, ask: AIAsk, db: Session = Depends(get_db)) -> dict:
    v = get_video(video_id, db)
    require_ready(v)
    s = get_settings()
    stroke = race_of(v).stroke.value
    if ask.phase not in {p["key"] for p in catalog(stroke)}:
        raise HTTPException(422, "fase desconhecida")
    try:
        jpeg = frame_for_ai(v.id, ask.frame, ask.mark)
    except IndexError as exc:
        raise HTTPException(404, str(exc)) from exc
    try:
        return ai.suggest(
            jpeg, stroke, ask.phase, ask.lane, api_key=s.anthropic_api_key, model=s.ai_model
        )
    except ai.AIError as exc:
        raise HTTPException(503 if s.anthropic_api_key else 409, str(exc)) from exc
