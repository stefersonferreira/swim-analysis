"""Várias raias no mesmo vídeo: eventos por raia e quadro comparativo."""

import pytest

from swimcv.contracts import Event, RaceInfo
from swimcv.contracts import EventType as E
from swimcv.metrics import athlete_events, compare_lanes, compute_metrics, lanes_in
from swimcv.overlay import build_timeline
from swimcv.overlay.timeline import state_at
from tests.unit.test_metrics import reference_free_50m


def ev(ty, t, lane=None):
    return Event(type=ty, frame=round(t * 30), t=t, lane=lane)


def three_lanes() -> tuple[RaceInfo, list[Event]]:
    """25 m livre, largada comum em 1,0 s; a raia 3 não chega dentro do vídeo."""
    race, _ = reference_free_50m()
    race = race.model_copy(
        update={"distance": 25, "lane": None, "official_final_s": None, "official_splits_s": []}
    )
    evs = [ev(E.START_SIGNAL, 1.0)]
    for lane, delay, period, fin in [
        (1, 1.6, 0.62, 21.0),
        (2, 1.1, 0.58, 19.4),
        (3, 1.2, 0.6, None),
    ]:
        evs.append(ev(E.ENTRY, 1.0 + delay, lane))
        t = 1.0 + delay + 2.5
        while t < (fin or 23):
            evs.append(ev(E.STROKE, round(t, 3), lane))
            t += period
        if fin:
            evs.append(ev(E.FINISH_TOUCH, fin, lane))
    return race, evs


def test_athlete_events_split_by_lane():
    race, evs = three_lanes()
    one = athlete_events(evs, 1, None)
    assert one[0].type == E.START_SIGNAL and one[0].lane is None
    assert all(e.lane in (None, 1) for e in one)
    assert [e for e in one if e.lane is None] == [evs[0]]  # só a largada comum
    assert lanes_in(evs, None) == [1, 2, 3]
    # eventos sem raia = atleta da prova (raia 4)
    main = [ev(E.STROKE, 5.0)]
    assert athlete_events(evs + main, None, 4)[-1] is main[0]
    assert athlete_events(evs + main, 4, 4)[-1] is main[0]
    assert main[0] not in athlete_events(evs + main, 2, 4)
    assert lanes_in(evs + main, 4) == [1, 2, 3, 4]


def test_compare_lanes_values():
    race, evs = three_lanes()
    res = {r.lane: r for r in compare_lanes(race, evs)}
    assert res[1].start_delay_s == pytest.approx(1.6) and res[1].start_delay_kind == "entry"
    assert res[2].final_time_s == pytest.approx(18.4)
    assert res[2].avg_speed_mps == pytest.approx(25 / 18.4)
    assert res[1].tempo_s_per_cycle == pytest.approx(2 * 0.62, rel=0.02)  # crawl: 2 braçadas/ciclo
    assert res[1].stroke_rate_cpm == pytest.approx(60 / (2 * 0.62), rel=0.02)
    assert res[3].final_time_s is None and res[3].avg_speed_mps is None
    assert res[3].strokes > 0 and res[3].dpc_m is None  # sem calibração


def test_lanes_timeline_board_and_summary():
    race, evs = three_lanes()
    tl = build_timeline(
        race, evs, compute_metrics(race, athlete_events(evs, None, None)), duration_s=23.4
    )
    assert [lr["lane"] for lr in tl["lanes"]] == [1, 2, 3]
    s = state_at(tl, 19.5)
    by = {r["lane"]: r for r in s["lanes"]}
    assert by[2]["finished"] and not by[1]["finished"] and by[1]["strokes"] > 0
    assert not s["show_summary"]
    assert state_at(tl, 23.35)["show_summary"]  # raia 3 não chega: resumo no fim do vídeo


def test_single_athlete_timeline_has_no_lanes():
    race, evs = reference_free_50m()
    tl = build_timeline(race, evs, compute_metrics(race, evs))
    assert tl["lanes"] == [] and state_at(tl, 8.0)["lanes"] == []


def test_lanes_live_callouts_difference_and_clock_stop():
    race, evs = three_lanes()
    evs.append(ev(E.FINISH_TOUCH, 22.5, 3))
    tl = build_timeline(race, evs, compute_metrics(race, athlete_events(evs, None, None)),
                        duration_s=30.0)  # fmt: skip
    by = {lr["lane"]: lr for lr in tl["lanes"]}
    assert by[2]["behind"] == 0 and by[1]["behind"] == pytest.approx(1.6)
    titles = [c["title"] for c in tl["callouts"]]
    assert "Raia 2 · Saída" in titles and "Raia 1 · Chegada" in titles
    fin1 = next(c for c in tl["callouts"] if c["title"] == "Raia 1 · Chegada")
    assert fin1["sub"] == "+1,60 s"
    s = state_at(tl, 1.5)
    assert not {r["lane"]: r for r in s["lanes"]}[1]["started"]
    assert {r["lane"]: r for r in state_at(tl, 3.0)["lanes"]}[1]["started"]
    assert state_at(tl, 25.0)["clock"] == pytest.approx(22.5 - 1.0)  # parou na última chegada
