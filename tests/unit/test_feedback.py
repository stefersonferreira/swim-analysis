"""Rascunho da devolutiva: só a partir do que foi medido."""

from swimcv.metrics import athlete_events, compute_metrics
from swimcv.overlay import build_timeline
from swimcv.report import draft_feedback
from swimcv.report.build import clean_feedback
from tests.unit.test_lanes import three_lanes
from tests.unit.test_metrics import reference_free_50m


def test_lanes_draft_points_to_the_slow_start_and_lower_rate():
    race, evs = three_lanes()
    tl = build_timeline(race, evs, compute_metrics(race, athlete_events(evs, None, None)))
    fb = draft_feedback(tl)
    assert fb["summary"].startswith("A raia 2 chegou 1,60 s à frente da raia 1")
    assert any(s.startswith("Raia 1: saída lenta, 1,60 s") for s in fb["improve"])
    assert any(s.startswith("Raia 1: saídas ao apito") for s in fb["drills"])
    assert any("ritmo constante" in s for s in fb["strengths"])


def test_single_athlete_draft_has_no_lane_prefix():
    race, evs = reference_free_50m()
    fb = draft_feedback(build_timeline(race, evs, compute_metrics(race, evs)))
    assert fb["summary"].startswith("Tempo de ")
    assert all(
        not s.startswith("Atleta") for k in ("strengths", "improve", "drills") for s in fb[k]
    )
    assert fb["strengths"] or fb["improve"]


def test_clean_feedback_drops_empty():
    assert clean_feedback({"summary": " ", "strengths": ["", " "]}) is None
    out = clean_feedback({"summary": " ok ", "drills": [" a ", ""]})
    assert out == {"summary": "ok", "strengths": [], "improve": [], "drills": ["a"]}
