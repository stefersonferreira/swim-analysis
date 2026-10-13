"""Contratos de dados trocados entre os módulos do pipeline.

Regra: todo arquivo gravado por um módulo é validado por um destes modelos e carrega
`schema_version`. Mudar um contrato exige subir a versão e atualizar os testes.
Unidades sempre SI (metros, segundos).
"""

from swimcv.contracts.calibration import (
    Anchor,
    AnchorResult,
    Calibration,
    ClickPoint,
    PoolProfile,
)
from swimcv.contracts.events import Event, EventSource, EventType
from swimcv.contracts.metrics import Alert, Metric, MetricsReport, MetricStatus
from swimcv.contracts.race import RaceInfo, Stroke
from swimcv.contracts.video import VideoMeta

__all__ = [
    "Alert",
    "Anchor",
    "AnchorResult",
    "Calibration",
    "ClickPoint",
    "Event",
    "EventSource",
    "EventType",
    "Metric",
    "MetricStatus",
    "MetricsReport",
    "PoolProfile",
    "RaceInfo",
    "Stroke",
    "VideoMeta",
]
