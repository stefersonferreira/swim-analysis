"""Várias raias no mesmo vídeo: eventos de cada atleta e o quadro comparativo.

Regras de raia (Event.lane):
- None = o atleta da prova (RaceInfo.lane), como sempre foi;
- um START_SIGNAL sem raia vale para todas as raias (largada comum);
- qualquer outro evento com raia pertence só àquela raia.

Funções puras, como o resto de swimcv.metrics.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from swimcv.contracts import Event, EventType, RaceInfo
from swimcv.metrics.compute import compute_metrics

E = EventType


def _is_common_start(e: Event) -> bool:
    return e.type == E.START_SIGNAL and e.lane is None


def athlete_events(events: list[Event], lane: int | None, main_lane: int | None) -> list[Event]:
    """Eventos de uma raia (com a largada comum). lane=None = o atleta da prova."""
    target = lane if lane is not None else main_lane
    out = []
    for e in events:
        if _is_common_start(e):
            out.append(e)
        elif e.lane is None:
            if lane is None or lane == main_lane:
                out.append(e)
        elif target is not None and e.lane == target:
            out.append(e)
    return out


def lanes_in(events: list[Event], main_lane: int | None) -> list[int]:
    """Raias com eventos próprios. A raia da prova entra se tiver eventos sem raia."""
    lanes = {e.lane for e in events if e.lane is not None}
    if main_lane is not None and any(e.lane is None and not _is_common_start(e) for e in events):
        lanes.add(main_lane)
    return sorted(lanes)


@dataclass
class LaneResult:
    lane: int
    start_delay_s: float | None  # pés fora do bloco (ou entrada na água) - largada
    start_delay_kind: str | None  # "feet_off" | "entry"
    strokes: int
    stroke_times: list[float]
    tempo_s_per_cycle: float | None
    stroke_rate_cpm: float | None
    final_time_s: float | None
    finish_t: float | None
    avg_speed_mps: float | None  # distância da prova / tempo final
    dpc_m: float | None  # só com posições na piscina (calibração)

    def as_dict(self) -> dict:
        return asdict(self)


def _mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def compare_lanes(race: RaceInfo, events: list[Event]) -> list[LaneResult]:
    out: list[LaneResult] = []
    for lane in lanes_in(events, race.lane):
        evs = athlete_events(events, lane, race.lane)
        upd: dict = {"lane": lane}
        if lane != race.lane:  # tempos oficiais informados são do atleta da prova
            upd |= {"official_final_s": None, "official_splits_s": []}
        r = race.model_copy(update=upd)
        report = compute_metrics(r, evs)
        start = next((e for e in sorted(evs, key=lambda e: e.t) if e.type == E.START_SIGNAL), None)
        mine = [e for e in evs if not _is_common_start(e)]
        feet = next((e for e in sorted(mine, key=lambda e: e.t) if e.type == E.FEET_OFF), None)
        entry = next((e for e in sorted(mine, key=lambda e: e.t) if e.type == E.ENTRY), None)
        delay, kind = None, None
        if start is not None and feet is not None:
            delay, kind = feet.t - start.t, "feet_off"
        elif start is not None and entry is not None:
            delay, kind = entry.t - start.t, "entry"
        strokes = sorted(e.t for e in mine if e.type == E.STROKE)
        tempos = [
            m.value for m in report.metrics if m.name == "tempo_s_per_cycle" and m.value is not None
        ]
        tempo = _mean(tempos)
        final = report.value("final_time_s", length_index=race.n_lengths - 1)
        fin = next((e for e in mine if e.type == E.FINISH_TOUCH), None)
        dpcs = [m.value for m in report.metrics if m.name == "dpc_m" and m.value is not None]
        out.append(
            LaneResult(
                lane=lane,
                start_delay_s=delay,
                start_delay_kind=kind,
                strokes=len(strokes),
                stroke_times=strokes,
                tempo_s_per_cycle=tempo,
                stroke_rate_cpm=60.0 / tempo if tempo else None,
                final_time_s=final,
                finish_t=fin.t if fin is not None else None,
                avg_speed_mps=race.distance / final if final else None,
                dpc_m=_mean(dpcs),
            )
        )
    return out
