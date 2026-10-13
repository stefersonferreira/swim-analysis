"""Cálculo determinístico das métricas a partir dos eventos.

Funções puras: sem arquivo, sem banco, sem relógio. Entrada = RaceInfo + eventos já com
`x_m` resolvido (ver swimcv.metrics.resolve). Saída = MetricsReport em unidades SI.

Convenções:
- Piscina k (0-based) termina no toque que fecha a piscina: no crawl, pés na parede
  (virada olímpica); no peito, toque das duas mãos; a última termina no toque final.
- d = distância a partir da parede de impulsão da piscina corrente.
  Piscinas pares saem da parede de saída (d = x_m); ímpares, da parede oposta (d = L - x_m).
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from swimcv.contracts import (
    Alert,
    Event,
    EventType,
    Metric,
    MetricsReport,
    MetricStatus,
    RaceInfo,
    Stroke,
)

NEAR_WALL_M = 5.0  # a janela limpa termina 5 m antes da parede
MIN_SPAN_M = 3.0  # distância mínima entre pontos para medir velocidade
DPC_RANGE_M = (1.2, 3.0)
STROKE_IRREGULARITY = 0.30
SPLIT_TOLERANCE_S = 0.15


@dataclass
class Length:
    index: int
    t_start: float | None  # pés saem do bloco (k=0) ou pés na parede (k>0)
    t_end: float | None  # toque que fecha a piscina
    events: list[Event] = field(default_factory=list)

    def of(self, kind: EventType) -> list[Event]:
        return [e for e in self.events if e.type == kind]

    def first(self, kind: EventType) -> Event | None:
        evs = self.of(kind)
        return evs[0] if evs else None


def _closing_type(race: RaceInfo) -> EventType:
    return EventType.WALL_FEET if race.stroke == Stroke.FREESTYLE else EventType.WALL_HANDS


def _distance_from_pushoff(e: Event, k: int, pool_m: float) -> float | None:
    if e.type == EventType.MARK_PASS and e.mark_m is not None:
        return e.mark_m
    if e.x_m is None:
        return None
    return e.x_m if k % 2 == 0 else pool_m - e.x_m


def split_lengths(race: RaceInfo, events: list[Event]) -> list[Length]:
    """Atribui cada evento a uma piscina usando os toques de fechamento como fronteira."""
    evs = sorted(events, key=lambda e: (e.t, e.frame))
    closing = _closing_type(race)
    closes = [e for e in evs if e.type == closing][: race.n_lengths - 1]
    finish = next((e for e in evs if e.type == EventType.FINISH_TOUCH), None)
    feet_off = next((e for e in evs if e.type == EventType.FEET_OFF), None)

    bounds = [c.t for c in closes]
    lengths: list[Length] = []
    for k in range(race.n_lengths):
        t_end = (
            bounds[k]
            if k < len(bounds)
            else (finish.t if finish and k == race.n_lengths - 1 else None)
        )
        lengths.append(Length(index=k, t_start=None, t_end=t_end))

    for e in evs:
        if e.type in (EventType.START_SIGNAL,):
            continue
        k = 0
        for i, b in enumerate(bounds):
            # O próprio toque de fechamento pertence à piscina que ele fecha.
            # No peito, os pés na parede logo após o toque das mãos também.
            if e.t > b or (e.t == b and e.type != closing):
                k = i + 1
        if race.stroke == Stroke.BREASTSTROKE and e.type == EventType.WALL_FEET and k > 0:
            k -= 1
        k = min(k, race.n_lengths - 1)
        lengths[k].events.append(e)

    # Início de cada piscina: pés fora do bloco, ou pés na parede da virada anterior.
    for k, ln in enumerate(lengths):
        if k == 0:
            ln.t_start = feet_off.t if feet_off else None
        else:
            prev_feet = lengths[k - 1].of(EventType.WALL_FEET)
            ln.t_start = prev_feet[-1].t if prev_feet else None
    return lengths


def _points(ln: Length, pool_m: float, with_walls: bool = False) -> list[tuple[float, float, str]]:
    """Pontos (t, d, id) com posição conhecida na piscina, em ordem de tempo.

    with_walls=True acrescenta as paredes como posições aproximadas da cabeça: toque das
    mãos (peito e chegada) em d = L, e pés na parede da virada anterior em d = 0. Serve só
    para interpolar marcas perto da parede (5 m), nunca para a velocidade de nado.
    """
    pts = []
    for e in ln.events:
        if e.type in (EventType.WALL_FEET, EventType.WALL_HANDS, EventType.FINISH_TOUCH):
            if with_walls and e.type != EventType.WALL_FEET:
                pts.append((e.t, pool_m, e.id))
            continue
        d = _distance_from_pushoff(e, ln.index, pool_m)
        if d is not None:
            pts.append((e.t, d, e.id))
    if with_walls and ln.index > 0 and ln.t_start is not None:
        pts.append((ln.t_start, 0.0, "pushoff"))
    pts.sort()
    return pts


def time_at_distance(
    points: list[tuple[float, float, str]], d: float
) -> tuple[float, list[str]] | None:
    """Instante em que a cabeça cruza a distância d, interpolando entre dois pontos."""
    for (t0, d0, i0), (t1, d1, i1) in zip(points, points[1:], strict=False):
        if d0 == d and d1 != d:
            return t0, [i0]
        if (d0 - d) * (d1 - d) < 0 and d1 != d0:
            return t0 + (d - d0) * (t1 - t0) / (d1 - d0), [i0, i1]
    if points and points[-1][1] == d:
        return points[-1][0], [points[-1][2]]
    return None


def _linfit_slope(ts: list[float], ds: list[float]) -> float:
    mt, md = statistics.fmean(ts), statistics.fmean(ds)
    num = sum((t - mt) * (d - md) for t, d in zip(ts, ds, strict=True))
    den = sum((t - mt) ** 2 for t in ts)
    return num / den


class _Builder:
    def __init__(self) -> None:
        self.report = MetricsReport()

    def ok(self, name: str, value: float, unit: str, ids: list[str] | None = None, **kw) -> None:
        self.report.metrics.append(
            Metric(name=name, value=value, unit=unit, source_event_ids=ids or [], **kw)
        )

    def missing(self, name: str, unit: str, reason: str, **kw) -> None:
        self.report.metrics.append(
            Metric(name=name, unit=unit, status=MetricStatus.NOT_MEASURED, reason=reason, **kw)
        )

    def alert(self, kind: str, message: str, **kw) -> None:
        self.report.alerts.append(Alert(kind=kind, message=message, **kw))


def compute_metrics(race: RaceInfo, events: list[Event]) -> MetricsReport:
    b = _Builder()
    pool_m = race.pool_length_m
    evs = sorted(events, key=lambda e: (e.t, e.frame))
    start = next((e for e in evs if e.type == EventType.START_SIGNAL), None)
    lengths = split_lengths(race, evs)
    first = lengths[0]
    feet_off = first.first(EventType.FEET_OFF)
    entry = first.first(EventType.ENTRY)

    # ---- Largada -------------------------------------------------------------------
    if start and feet_off:
        b.ok("reaction_s", feet_off.t - start.t, "s", [start.id, feet_off.id])
    else:
        b.missing("reaction_s", "s", "falta o sinal de largada ou os pés fora do bloco")

    pts0 = _points(first, pool_m)
    hit = time_at_distance(pts0, 15.0)
    if start and hit:
        b.ok("start_15m_s", hit[0] - start.t, "s", [start.id, *hit[1]])
    else:
        b.missing("start_15m_s", "s", "sem sinal de largada ou sem posição antes/depois de 15 m")

    bo = first.first(EventType.BREAKOUT)
    bo_d = _distance_from_pushoff(bo, 0, pool_m) if bo else None
    if bo and bo_d is not None:
        b.ok("start_breakout_m", bo_d, "m", [bo.id])
    else:
        b.missing("start_breakout_m", "m", "breakout sem posição na piscina")
    if bo and entry:
        b.ok("start_underwater_s", bo.t - entry.t, "s", [entry.id, bo.id])
    else:
        b.missing("start_underwater_s", "s", "falta a entrada na água ou o breakout")
    if bo and bo_d is not None and feet_off and bo.t > feet_off.t:
        b.ok("start_underwater_speed_mps", bo_d / (bo.t - feet_off.t), "m/s", [feet_off.id, bo.id])
    else:
        b.missing("start_underwater_speed_mps", "m/s", "falta breakout com posição ou pés fora")

    # ---- Viradas ---------------------------------------------------------------------
    for k in range(1, race.n_lengths):
        prev, ln = lengths[k - 1], lengths[k]
        turn = k - 1
        feet_list = prev.of(EventType.WALL_FEET)
        feet = feet_list[-1] if feet_list else None
        pts = _points(ln, pool_m)
        hit = time_at_distance(pts, 15.0)
        if feet and hit:
            b.ok("turn_15m_s", hit[0] - feet.t, "s", [feet.id, *hit[1]], turn_index=turn)
        else:
            b.missing(
                "turn_15m_s",
                "s",
                "falta pés na parede ou posição em torno de 15 m",
                turn_index=turn,
            )
        tbo = ln.first(EventType.BREAKOUT)
        tbo_d = _distance_from_pushoff(tbo, k, pool_m) if tbo else None
        if tbo and tbo_d is not None:
            b.ok("turn_breakout_m", tbo_d, "m", [tbo.id], turn_index=turn)
        else:
            b.missing("turn_breakout_m", "m", "breakout sem posição", turn_index=turn)
        if tbo and feet:
            b.ok("turn_underwater_s", tbo.t - feet.t, "s", [feet.id, tbo.id], turn_index=turn)
        else:
            b.missing("turn_underwater_s", "s", "falta pés na parede ou breakout", turn_index=turn)
        t_in = time_at_distance(_points(prev, pool_m, with_walls=True), pool_m - NEAR_WALL_M)
        t_out = time_at_distance(_points(ln, pool_m, with_walls=True), NEAR_WALL_M)
        if t_in and t_out:
            ids = [i for i in t_in[1] + t_out[1] if i != "pushoff"]
            b.ok("turn_5m_inout_s", t_out[0] - t_in[0], "s", ids, turn_index=turn)
        else:
            b.missing(
                "turn_5m_inout_s",
                "s",
                "falta posição a 5 m da parede antes e depois",
                turn_index=turn,
            )
        if race.stroke == Stroke.BREASTSTROKE:
            hands = prev.of(EventType.WALL_HANDS)
            if hands and feet and feet.t >= hands[-1].t:
                b.ok(
                    "wall_time_s",
                    feet.t - hands[-1].t,
                    "s",
                    [hands[-1].id, feet.id],
                    turn_index=turn,
                )
            else:
                b.missing(
                    "wall_time_s", "s", "falta toque das mãos ou pés na parede", turn_index=turn
                )

    # ---- Nado por piscina --------------------------------------------------------------
    step = race.strokes_per_cycle
    for ln in lengths:
        k = ln.index
        strokes = sorted(ln.of(EventType.STROKE), key=lambda e: e.t)
        if strokes:
            b.ok("strokes", float(len(strokes)), "count", [s.id for s in strokes], length_index=k)
        else:
            b.missing("strokes", "count", "nenhuma braçada marcada", length_index=k)

        # Janela limpa: do breakout em diante, até 5 m da parede.
        pts = _points(ln, pool_m)
        bo = ln.first(EventType.BREAKOUT)
        win = [p for p in pts if (bo is None or p[0] >= bo.t) and p[1] <= pool_m - NEAR_WALL_M]
        speed = None
        if len(win) >= 2 and win[-1][1] - win[0][1] >= MIN_SPAN_M:
            speed = _linfit_slope([p[0] for p in win], [p[1] for p in win])
            b.ok("swim_speed_mps", speed, "m/s", [p[2] for p in win], length_index=k)
        else:
            b.missing(
                "swim_speed_mps",
                "m/s",
                f"precisa de 2 posições a {MIN_SPAN_M:.0f} m ou mais entre si, "
                "depois do breakout e antes de 5 m da parede",
                length_index=k,
            )

        # Tempo de ciclo: pula o primeiro ciclo após o breakout; se houver janela de
        # posições, não usa braçadas depois do fim da janela.
        cyc_strokes = strokes[step:]
        if win and len(win) >= 2:
            cyc_strokes = [s for s in cyc_strokes if s.t <= win[-1][0] + 1e-9] or cyc_strokes
        durations = [
            cyc_strokes[i + step].t - cyc_strokes[i].t for i in range(len(cyc_strokes) - step)
        ]
        tempo = None
        if durations:
            tempo = statistics.fmean(durations)
            ids = [s.id for s in cyc_strokes]
            b.ok("tempo_s_per_cycle", tempo, "s/cycle", ids, length_index=k)
            b.ok("stroke_rate_cpm", 60.0 / tempo, "cycles/min", ids, length_index=k)
        else:
            b.missing(
                "tempo_s_per_cycle",
                "s/cycle",
                "menos de 2 ciclos completos após o primeiro ciclo",
                length_index=k,
            )
            b.missing("stroke_rate_cpm", "cycles/min", "sem tempo de ciclo", length_index=k)

        if speed is not None and tempo is not None:
            dpc = speed * tempo
            b.ok("dpc_m", dpc, "m", length_index=k)
            if not DPC_RANGE_M[0] <= dpc <= DPC_RANGE_M[1]:
                b.alert(
                    "dpc_out_of_range",
                    f"Distância por ciclo {dpc:.2f} m fora de {DPC_RANGE_M[0]}–"
                    f"{DPC_RANGE_M[1]} m: confira braçadas e posições",
                    length_index=k,
                )
        else:
            b.missing("dpc_m", "m", "falta velocidade ou tempo de ciclo", length_index=k)

        # Regularidade das braçadas (mesmo braço: intervalo de um ciclo).
        if len(strokes) >= step + 3:
            gaps = [strokes[i + step].t - strokes[i].t for i in range(len(strokes) - step)]
            med = statistics.median(gaps)
            for i, g in enumerate(gaps):
                if med > 0 and abs(g - med) / med > STROKE_IRREGULARITY:
                    b.alert(
                        "stroke_irregular",
                        f"Intervalo entre braçadas {g:.2f} s difere mais de 30% da "
                        f"mediana ({med:.2f} s): braçada faltando ou sobrando?",
                        length_index=k,
                        t_from=strokes[i].t,
                        t_to=strokes[i + step].t,
                        event_ids=[strokes[i].id, strokes[i + step].id],
                    )

    # ---- Parciais e tempo final ---------------------------------------------------------
    for ln in lengths:
        k = ln.index
        last = k == race.n_lengths - 1
        measured = (ln.t_end - start.t) if (start and ln.t_end is not None) else None
        official = None
        if last and race.official_final_s is not None:
            official = race.official_final_s
        elif k < len(race.official_splits_s):
            official = race.official_splits_s[k]
        name = "final_time_s" if last else "split_s"
        if official is not None:
            b.ok(name, official, "s", length_index=k, source="official")
            if measured is not None and abs(measured - official) > SPLIT_TOLERANCE_S:
                b.alert(
                    "split_mismatch",
                    f"Tempo medido {measured:.2f} s difere do oficial {official:.2f} s "
                    f"em mais de {SPLIT_TOLERANCE_S} s: confira o sinal de largada e o toque",
                    length_index=k,
                )
        elif measured is not None:
            b.ok(name, measured, "s", length_index=k)
        else:
            b.missing(name, "s", "falta o sinal de largada ou o toque", length_index=k)

    if start is None:
        b.alert("missing_start", "Sinal de largada não marcado: reação e tempos não medidos")
    return b.report
