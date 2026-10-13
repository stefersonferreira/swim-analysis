from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

POOL_LENGTHS_M = (25, 50)


class Stroke(StrEnum):
    FREESTYLE = "freestyle"
    BREASTSTROKE = "breaststroke"


class RaceInfo(BaseModel):
    """Dados da prova informados no upload. Tudo em metros."""

    schema_version: int = 2
    stroke: Stroke
    distance: int = Field(description="Distância da prova em metros (50, 100)")
    pool_length: int = Field(25, description="Comprimento da piscina em metros (25 ou 50)")
    lane: int | None = None
    cap_color: str | None = None
    official_final_s: float | None = None
    official_splits_s: list[float] = Field(
        default_factory=list,
        description="Tempos oficiais acumulados ao fim de cada piscina, em ordem",
    )

    @model_validator(mode="after")
    def _check(self) -> "RaceInfo":
        if self.pool_length not in POOL_LENGTHS_M:
            raise ValueError("piscina deve ter 25 ou 50 m")
        if self.distance % self.pool_length != 0:
            raise ValueError("a distância precisa ser múltiplo do comprimento da piscina")
        if len(self.official_splits_s) > self.n_lengths:
            raise ValueError("mais parciais oficiais do que piscinas na prova")
        return self

    @property
    def pool_length_m(self) -> float:
        return float(self.pool_length)

    @property
    def n_lengths(self) -> int:
        return self.distance // self.pool_length

    @property
    def strokes_per_cycle(self) -> int:
        """Crawl: 2 braçadas por ciclo. Peito: cada evento 'stroke' já é um ciclo."""
        return 2 if self.stroke == Stroke.FREESTYLE else 1
