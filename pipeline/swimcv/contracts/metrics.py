from enum import StrEnum

from pydantic import BaseModel, Field


class MetricStatus(StrEnum):
    OK = "ok"
    NOT_MEASURED = "not_measured"


class Metric(BaseModel):
    name: str
    value: float | None = None
    unit: str = Field(description="s, m, m/s, count, s/cycle, cycles/min")
    length_index: int | None = None
    turn_index: int | None = None
    status: MetricStatus = MetricStatus.OK
    reason: str | None = None
    source: str = Field("measured", description="measured | official")
    source_event_ids: list[str] = Field(default_factory=list)
    confidence: float = 1.0


class Alert(BaseModel):
    kind: str
    message: str
    length_index: int | None = None
    t_from: float | None = None
    t_to: float | None = None
    event_ids: list[str] = Field(default_factory=list)


class MetricsReport(BaseModel):
    schema_version: int = 1
    metrics: list[Metric] = Field(default_factory=list)
    alerts: list[Alert] = Field(default_factory=list)

    def get(
        self, name: str, length_index: int | None = None, turn_index: int | None = None
    ) -> Metric | None:
        for m in self.metrics:
            if m.name != name:
                continue
            if length_index is not None and m.length_index != length_index:
                continue
            if turn_index is not None and m.turn_index != turn_index:
                continue
            return m
        return None

    def value(self, name: str, **kw) -> float | None:
        m = self.get(name, **kw)
        return m.value if m else None
