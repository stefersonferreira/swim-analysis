"""Relatório da análise: mesmos números do vídeo e só o que foi medido."""

from datetime import date

from swimcv.contracts import EventType as E
from swimcv.metrics import athlete_events, compute_metrics
from swimcv.overlay import build_timeline
from swimcv.report import build_report, render_html
from tests.unit.test_lanes import ev, three_lanes
from tests.unit.test_metrics import reference_free_50m


def lanes_report(**kw):
    race, evs = three_lanes()
    tl = build_timeline(
        race, evs, compute_metrics(race, athlete_events(evs, None, None)), duration_s=23.4, **kw
    )
    return build_report(tl, evs, today=date(2026, 10, 14)), tl


def test_lanes_report_compares_and_explains_the_gap():
    rep, tl = lanes_report(strokes_partial=True, notes=["Ritmo medido de 4 a 19 s"])
    assert rep["table"]["head"] == ["Raia", "Saída", "Ritmo", "Tempo", "Dif.", "Velocidade média"]
    rows = {r[0]: r for r in rep["table"]["rows"]}
    assert rows["Raia 2"][4] == "1º" and rows["Raia 1"][4] == "+1,60 s"
    assert rows["Raia 3"][3] == "–"  # chegada fora do vídeo
    assert rep["lead"].startswith("A raia 2 chegou 1,60 s à frente da raia 1")
    # saída 1,6 x 1,1: 0,5 s da diferença; o resto, 1,1 s, no nado
    assert (
        "A saída explica 0,50 s dessa diferença; o resto, 1,10 s, nasce no nado." in rep["insights"]
    )
    assert any(i.startswith("Ritmo: raia 1 com") for i in rep["insights"])
    assert "Ritmo medido de 4 a 19 s" in rep["notes"]
    assert any("só num trecho" in n for n in rep["notes"])
    who = [m["who"] for m in rep["moments"]]
    assert who[0] == "Todas as raias" and "Raia 1" in who


def test_full_counts_when_not_partial():
    rep, _ = lanes_report()
    assert "Ciclos" in rep["table"]["head"] or "Braçadas" in rep["table"]["head"]


def test_single_athlete_report_and_html_escapes():
    race, evs = reference_free_50m()
    tl = build_timeline(race, evs, compute_metrics(race, evs), title="50 <livre>")
    rep = build_report(tl, evs)
    assert rep["table"]["head"] == ["Medida", "Valor"] and rep["table"]["rows"]
    page = render_html(rep)
    assert "50 &lt;livre&gt;" in page and "<script" not in page
    assert "Salvar em PDF" in page


def test_no_start_marked_says_so():
    race, evs = three_lanes()
    evs = [e for e in evs if e.type != E.START_SIGNAL] + [ev(E.STROKE, 5.0, 1)]
    tl = build_timeline(race, evs, compute_metrics(race, athlete_events(evs, None, None)))
    rep = build_report(tl, evs)
    assert any("Sem largada" in n for n in rep["notes"])
