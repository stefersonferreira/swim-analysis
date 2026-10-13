from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field


class EventType(StrEnum):
    START_SIGNAL = "start_signal"  # início do bipe / buzina
    FEET_OFF = "feet_off"  # último quadro com o pé no bloco
    ENTRY = "entry"  # mãos tocam a água na saída
    BREAKOUT = "breakout"  # cabeça rompe a superfície após a fase submersa
    STROKE = "stroke"  # crawl: entrada de um braço; peito: um ciclo (pico da cabeça)
    WALL_HANDS = "wall_hands"  # peito: toque das duas mãos na virada
    WALL_FEET = "wall_feet"  # pés na parede na virada
    FINISH_TOUCH = "finish_touch"  # toque final
    MARK_PASS = "mark_pass"  # cabeça cruza uma marca conhecida (mark_m)


class EventSource(StrEnum):
    AUTO = "auto"
    MANUAL = "manual"


class Event(BaseModel):
    """Um acontecimento da prova num instante do vídeo.

    Posição:
    - `image_xy`: ponto clicado no quadro (pixels do proxy). Convertido em `x_m` pela
      calibração no momento do cálculo, para que recalibrar atualize tudo.
    - `x_m`: posição ao longo da piscina, medida a partir da parede de saída (0..L).
    - `mark_m`: só para MARK_PASS, distância da marca até a parede de impulsão da
      piscina corrente (ex.: 15 = marca de 15 m).
    """

    schema_version: int = 1
    id: str = Field(default_factory=lambda: uuid4().hex)
    type: EventType
    frame: int = Field(ge=0)
    t: float = Field(description="PTS do quadro em segundos, relativo ao primeiro quadro")
    image_xy: tuple[float, float] | None = None
    x_m: float | None = None
    mark_m: float | None = None
    confidence: float = Field(1.0, ge=0, le=1)
    source: EventSource = EventSource.MANUAL
    author: str | None = None
