"""Testes da biblioteca de métricas (tudo em metros).

O cenário de crawl (50 m livre em piscina de 25 m) segue o mesmo padrão do vídeo de
referência: tempo 0,96 / 1,00 s/ciclo, velocidade 2,03 / 1,95 m/s, logo distância por ciclo
1,95 / 1,95 m; reação 0,67 s, submerso 3,66 s, parciais oficiais.
"""

import pytest

from swimcv.contracts import Event, EventType, MetricStatus, RaceInfo, Stroke
from swimcv.metrics import compute_metrics, split_lengths

E = EventType
L = 25.0


def ev(kind, t, x_m=None, mark_m=None):
    return Event(type=kind, frame=int(round(t * 30)), t=t, x_m=x_m, mark_m=mark_m)


def reference_free_50m() -> tuple[RaceInfo, list[Event]]:
    race = RaceInfo(
        stroke=Stroke.FREESTYLE,
        distance=50,
        pool_length=25,
        lane=3,
        official_final_s=21.80,
        official_splits_s=[10.58],
    )
    v0, v1 = 2.03, 1.95  # m/s
    bo0_d, bo1_d = 9.9, 5.5  # m da parede de impulsão
    evs = [
        ev(E.START_SIGNAL, 1.00),
        ev(E.FEET_OFF, 1.67),
        ev(E.ENTRY, 2.30),
        ev(E.BREAKOUT, 5.96, x_m=bo0_d),
        # ponto a 5 m da parede oposta, no mesmo ritmo
        ev(E.MARK_PASS, 5.96 + (L - 5 - bo0_d) / v0, mark_m=L - 5),
    ]
    evs += [ev(E.STROKE, 6.10 + 0.48 * i) for i in range(12)]
    t_wall = 1.00 + 10.58
    evs.append(ev(E.WALL_FEET, t_wall, x_m=L))
    t_bo1 = t_wall + 2.39
    evs.append(ev(E.BREAKOUT, t_bo1, x_m=L - bo1_d))
    evs.append(ev(E.MARK_PASS, t_bo1 + (L - 5 - bo1_d) / v1, mark_m=L - 5))
    evs += [ev(E.STROKE, t_bo1 + 0.15 + 0.50 * i) for i in range(18)]
    evs.append(ev(E.FINISH_TOUCH, 1.00 + 21.80, x_m=0.0))
    return race, evs


def test_reference_scenario_numbers():
    race, evs = reference_free_50m()
    r = compute_metrics(race, evs)

    assert r.value("reaction_s") == pytest.approx(0.67)
    assert r.value("start_underwater_s") == pytest.approx(3.66)
    assert r.value("start_breakout_m") == pytest.approx(9.9)
    assert r.value("strokes", length_index=0) == 12
    assert r.value("strokes", length_index=1) == 18
    assert r.value("tempo_s_per_cycle", length_index=0) == pytest.approx(0.96)
    assert r.value("tempo_s_per_cycle", length_index=1) == pytest.approx(1.00)
    assert r.value("swim_speed_mps", length_index=0) == pytest.approx(2.03)
    assert r.value("swim_speed_mps", length_index=1) == pytest.approx(1.95)
    # distância por ciclo = velocidade x tempo de ciclo
    assert r.value("dpc_m", length_index=0) == pytest.approx(2.03 * 0.96)
    assert r.value("dpc_m", length_index=1) == pytest.approx(1.95 * 1.00)
    assert r.value("turn_breakout_m", turn_index=0) == pytest.approx(5.5)
    assert r.value("turn_underwater_s", turn_index=0) == pytest.approx(2.39)
    split = r.get("split_s", length_index=0)
    assert split.value == pytest.approx(10.58) and split.source == "official"
    assert r.value("final_time_s", length_index=1) == pytest.approx(21.80)
    assert r.value("stroke_rate_cpm", length_index=0) == pytest.approx(62.5)
    assert all(m.unit in {"s", "m", "m/s", "count", "s/cycle", "cycles/min"} for m in r.metrics)
    assert not [a for a in r.alerts if a.kind in ("split_mismatch", "dpc_out_of_range")]


def test_lengths_split_by_closing_touch():
    race, evs = reference_free_50m()
    lengths = split_lengths(race, evs)
    assert [len(ln.of(E.STROKE)) for ln in lengths] == [12, 18]
    assert lengths[0].of(E.WALL_FEET) and not lengths[1].of(E.WALL_FEET)
    assert lengths[1].t_start == pytest.approx(11.58)


def test_missing_start_signal_is_not_measured_not_estimated():
    race, evs = reference_free_50m()
    evs = [e for e in evs if e.type != E.START_SIGNAL]
    r = compute_metrics(race, evs)
    m = r.get("reaction_s")
    assert m.status == MetricStatus.NOT_MEASURED and m.value is None
    assert any(a.kind == "missing_start" for a in r.alerts)
    # o tempo oficial ainda aparece
    assert r.value("final_time_s", length_index=1) == pytest.approx(21.80)


def test_split_mismatch_alert():
    race, evs = reference_free_50m()
    race = race.model_copy(update={"official_splits_s": [10.30]})
    r = compute_metrics(race, evs)
    assert any(a.kind == "split_mismatch" and a.length_index == 0 for a in r.alerts)


def test_missing_stroke_triggers_irregular_alert():
    race, evs = reference_free_50m()
    strokes0 = [e for e in evs if e.type == E.STROKE and e.t < 11]
    evs = [e for e in evs if e.id != strokes0[6].id]
    r = compute_metrics(race, evs)
    assert any(a.kind == "stroke_irregular" and a.length_index == 0 for a in r.alerts)


def test_15m_interpolated_between_positions():
    race, evs = reference_free_50m()
    r = compute_metrics(race, evs)
    expected = 5.96 + (15 - 9.9) / 2.03 - 1.00
    assert r.value("start_15m_s") == pytest.approx(expected)


def breast_50m() -> tuple[RaceInfo, list[Event]]:
    race = RaceInfo(stroke=Stroke.BREASTSTROKE, distance=50, pool_length=25)
    evs = [
        ev(E.START_SIGNAL, 0.50),
        ev(E.FEET_OFF, 1.20),
        ev(E.ENTRY, 1.80),
        ev(E.BREAKOUT, 6.00, x_m=10.0),  # após a filipina
    ]
    evs += [
        ev(E.STROKE, 6.40 + 1.20 * i, x_m=10.0 + 1.3 * (6.40 + 1.20 * i - 6.0)) for i in range(9)
    ]
    evs.append(ev(E.WALL_HANDS, 18.30, x_m=25.0))
    evs.append(ev(E.WALL_FEET, 19.10, x_m=25.0))
    evs.append(ev(E.BREAKOUT, 23.60, x_m=25.0 - 8.0))
    evs += [
        ev(E.STROKE, 24.0 + 1.25 * i, x_m=17.0 - 1.25 * (24.0 + 1.25 * i - 23.6)) for i in range(8)
    ]
    evs.append(ev(E.FINISH_TOUCH, 35.90, x_m=0.0))
    return race, evs


def test_breaststroke_cycles_and_wall_time():
    race, evs = breast_50m()
    r = compute_metrics(race, evs)
    assert r.value("strokes", length_index=0) == 9
    assert r.value("strokes", length_index=1) == 8
    # peito: cada evento é um ciclo; pula o primeiro ciclo
    assert r.value("tempo_s_per_cycle", length_index=0) == pytest.approx(1.20)
    assert r.value("tempo_s_per_cycle", length_index=1) == pytest.approx(1.25)
    assert r.value("swim_speed_mps", length_index=0) == pytest.approx(1.3)
    assert r.value("dpc_m", length_index=0) == pytest.approx(1.56)
    assert r.value("wall_time_s", turn_index=0) == pytest.approx(0.80)
    assert r.value("turn_underwater_s", turn_index=0) == pytest.approx(4.50)
    assert r.value("turn_breakout_m", turn_index=0) == pytest.approx(8.0)
    assert r.value("split_s", length_index=0) == pytest.approx(17.80)  # toque das mãos
    assert r.value("final_time_s", length_index=1) == pytest.approx(35.40)
    lengths = split_lengths(race, evs)
    assert lengths[0].of(E.WALL_FEET) and lengths[0].of(E.WALL_HANDS)
    assert lengths[1].t_start == pytest.approx(19.10)


def test_turn_5m_in_out():
    race, evs = breast_50m()
    r = compute_metrics(race, evs)
    m = r.get("turn_5m_inout_s", turn_index=0)
    assert m.status == MetricStatus.OK
    # entrada: cabeça a 20 m na piscina 0 (velocidade 1,3 m/s a partir de 10 m em 6,0 s)
    t_in = 6.0 + (20.0 - 10.0) / 1.3
    # saída: entre os pés na parede (d=0 em 19,10) e o breakout (d=8 em 23,60)
    t_out = 19.10 + 5.0 * (23.60 - 19.10) / 8.0
    assert m.value == pytest.approx(t_out - t_in)


def test_race_validation():
    with pytest.raises(ValueError):
        RaceInfo(stroke=Stroke.FREESTYLE, distance=60, pool_length=25)
    with pytest.raises(ValueError, match="25 ou 50"):
        RaceInfo(stroke=Stroke.FREESTYLE, distance=66, pool_length=33)
    # campo antigo de unidade é ignorado (dados gravados antes da mudança)
    assert (
        RaceInfo.model_validate(
            {"stroke": "freestyle", "distance": 50, "pool_length": 25, "pool_unit": "m"}
        ).pool_length_m
        == 25.0
    )
    assert RaceInfo(stroke=Stroke.FREESTYLE, distance=100, pool_length=25).n_lengths == 4


def test_duplicate_start_alert():
    race, evs = reference_free_50m()
    evs.append(ev(E.START_SIGNAL, 1.5))
    r = compute_metrics(race, evs)
    assert any(a.kind == "duplicate_start" for a in r.alerts)
    assert r.value("reaction_s") == pytest.approx(0.67)  # vale o primeiro
