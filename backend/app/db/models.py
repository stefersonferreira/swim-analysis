import secrets
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _now() -> datetime:
    return datetime.now(UTC)


def _id() -> str:
    return uuid4().hex


def _token() -> str:
    # link de entrega para o cliente: difícil de adivinhar, sem login
    return secrets.token_urlsafe(16)


class Base(DeclarativeBase):
    pass


class Pool(Base):
    __tablename__ = "pools"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    profile: Mapped[dict] = mapped_column(JSON)  # swimcv.contracts.PoolProfile
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    title: Mapped[str] = mapped_column(String(300))
    athlete: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="uploaded")
    error: Mapped[str | None] = mapped_column(Text)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    race: Mapped[dict] = mapped_column(JSON)  # swimcv.contracts.RaceInfo
    meta: Mapped[dict | None] = mapped_column(JSON)  # swimcv.contracts.VideoMeta
    calibration: Mapped[dict | None] = mapped_column(JSON)  # swimcv.contracts.Calibration
    pool_id: Mapped[int | None] = mapped_column(ForeignKey("pools.id", ondelete="SET NULL"))
    # análise automática: idle | queued | running | done | failed
    analysis_status: Mapped[str] = mapped_column(String(20), default="idle", server_default="idle")
    analysis_notes: Mapped[list | None] = mapped_column(JSON)
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # MP4 com a sobreposição: idle | queued | running | done | failed
    export_status: Mapped[str] = mapped_column(String(20), default="idle", server_default="idle")
    export_progress: Mapped[float | None] = mapped_column(Float)
    export_error: Mapped[str | None] = mapped_column(Text)
    exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # vídeo final: ciclos marcados só num trecho (contagem vira "–") e observações do resumo
    strokes_partial: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    review_notes: Mapped[list | None] = mapped_column(JSON)
    # pedido de revisão (cliente envia pela página pública ou o treinador cadastra)
    origin: Mapped[str] = mapped_column(String(10), default="coach", server_default="coach")
    customer_name: Mapped[str | None] = mapped_column(String(200))
    customer_email: Mapped[str | None] = mapped_column(String(200))
    customer_phone: Mapped[str | None] = mapped_column(String(40))
    customer_notes: Mapped[str | None] = mapped_column(Text)
    # new | reviewing | delivered
    order_status: Mapped[str] = mapped_column(String(20), default="new", server_default="new")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    share_token: Mapped[str] = mapped_column(String(40), unique=True, index=True, default=_token)
    # devolutiva do treinador: {summary, strengths[], improve[], drills[]}
    feedback: Mapped[dict | None] = mapped_column(JSON)
    # observações técnicas por quadro-chave (swimcv.report.technique.clean_notes)
    tech_notes: Mapped[list | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    events: Mapped[list["Event"]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )


class Event(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(30))
    frame: Mapped[int] = mapped_column(Integer)
    t: Mapped[float] = mapped_column(Float)
    image_x: Mapped[float | None] = mapped_column(Float)
    image_y: Mapped[float | None] = mapped_column(Float)
    mark_m: Mapped[float | None] = mapped_column(Float)
    lane: Mapped[int | None] = mapped_column(Integer)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    source: Mapped[str] = mapped_column(String(10), default="manual")
    author: Mapped[str | None] = mapped_column(String(100))
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    video: Mapped[Video] = relationship(back_populates="events")


class AuditLog(Base):
    """Toda alteração de evento ou calibração: base do dataset de treino e do painel de
    precisão (valor automático x valor final)."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_id: Mapped[str] = mapped_column(String(32), index=True)
    entity: Mapped[str] = mapped_column(String(30))
    entity_id: Mapped[str | None] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(20))
    before: Mapped[dict | None] = mapped_column(JSON)
    after: Mapped[dict | None] = mapped_column(JSON)
    author: Mapped[str | None] = mapped_column(String(100))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
