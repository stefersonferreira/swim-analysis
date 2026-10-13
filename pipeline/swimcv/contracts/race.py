from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

YARD_M = 0.9144


class Stroke(StrEnum):
    FREESTYLE = "freestyle"
    BREASTSTROKE = "breaststroke"


class PoolUnit(StrEnum):
    METERS = "m"
    YARDS = "yd"


class RaceInfo(BaseModel):
    """Dados da prova informados no upload."""

    schema_version: int = 1
    stroke: Stroke
    distance: int = Field(description="Distância da prova na unidade da piscina (50, 100)")
    pool_length: int = Field(25, description="Comprimento da piscina na unidade da piscina")
    pool_unit: PoolUnit = PoolUnit.METERS
    lane: int | None = None
    cap_color: str | None = None
    official_final_s: float | None = None
    official_splits_s: list[float] = Field(
        default_factory=list,
        description="Tempos oficiais acumulados ao fim de cada piscina, em ordem",
    )

    @model_validator(mode="after")
    def _check(self) -> "RaceInfo":
        if self.distance % self.pool_length != 0:
            raise ValueError("a distância precisa ser múltiplo do comprimento da piscina")
        if len(self.official_splits_s) > self.n_lengths:
            raise ValueError("mais parciais oficiais do que piscinas na prova")
        return self

    @property
    def unit_m(self) -> float:
        return YARD_M if self.pool_unit == PoolUnit.YARDS else 1.0

    @property
    def pool_length_m(self) -> float:
        return self.pool_length * self.unit_m

    @property
    def n_lengths(self) -> int:
        return self.distance // self.pool_length

    @property
    def strokes_per_cycle(self) -> int:
        """Crawl: 2 braçadas por ciclo. Peito: cada evento 'stroke' já é um ciclo."""
        return 2 if self.stroke == Stroke.FREESTYLE else 1
