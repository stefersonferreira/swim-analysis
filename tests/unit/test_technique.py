"""Técnica quadro a quadro: catálogo, quadros sugeridos, IA (sem rede) e devolutiva."""

import json

import pytest

from swimcv.contracts import EventType as E
from swimcv.contracts import Stroke
from swimcv.metrics import athlete_events, compute_metrics
from swimcv.overlay import build_timeline
from swimcv.report import ai
from swimcv.report.build import build_report, render_html
from swimcv.report.technique import (
    catalog,
    clean_notes,
    items_by_key,
    notes_feedback,
    suggest_keyframes,
)
from tests.unit.test_lanes import three_lanes


def test_catalog_has_phases_and_unique_keys_per_stroke():
    for stroke in (Stroke.FREESTYLE, Stroke.BREASTSTROKE):
        cat = catalog(stroke)
        keys = [p["key"] for p in cat]
        assert keys[0] == "start" and keys[-1] == "finish" and "breath" in keys
        items = items_by_key(stroke)
        assert len(items) == sum(len(p["items"]) for p in cat)  # chaves únicas
        assert all(i.text and (i.good or i.drill) for _, i in items.values())


def test_suggested_keyframes_per_lane():
    race, evs = three_lanes()
    sug = suggest_keyframes(race.stroke, evs)
    by = {(s["lane"], s["phase"]) for s in sug}
    assert (1, "entry") in by and (1, "breath") in by and (1, "finish") in by
    assert (3, "finish") not in by  # raia 3 não tocou dentro do vídeo
    assert not any(s["phase"] == "start" for s in sug)  # sem pés fora marcados
    entry = next(s for s in sug if s["lane"] == 1 and s["phase"] == "entry")
    assert entry["dt"] == 0.3


def test_clean_notes_drops_unknown_items_and_bad_phase():
    out = clean_notes(
        "breaststroke",
        [{"id": "a", "frame": 5, "t": 1.0, "phase": "nope", "items": ["head_high", "x"],
          "text": "  ok  ", "mark": [1, 2], "source": "hack", "confirmed": False}],
    )  # fmt: skip
    assert out[0]["items"] == ["head_high"] and out[0]["phase"] is None
    assert out[0]["text"] == "ok" and out[0]["source"] == "coach" and not out[0]["confirmed"]


def test_notes_feedback_only_confirmed_and_named_by_lane():
    notes = [
        {"lane": 1, "items": ["head_high", "breath_good"], "confirmed": True},
        {"lane": 2, "items": ["knees_wide"], "confirmed": False},
    ]
    fb = notes_feedback("breaststroke", notes, multi_lane=True)
    assert fb["improve"] == ["Raia 1: Levanta muito a cabeça ao respirar; o quadril afunda."]
    assert fb["strengths"][0].startswith("Raia 1: Respira sem levantar")
    assert len(fb["drills"]) == 1


def test_ai_suggest_builds_request_and_filters_answer():
    seen = {}

    def fake_post(url, headers, body):
        seen.update(url=url, headers=headers, body=body)
        answer = {"items": ["head_high", "inventado"], "text": "Cabeça alta.", "visible": True,
                  "confidence": 1.7}  # fmt: skip
        return {"content": [{"type": "text", "text": "Aqui:\n" + json.dumps(answer)}]}

    r = ai.suggest(b"\xff\xd8jpeg", "breaststroke", "breath", 2, api_key="k", post=fake_post)
    assert r == {"items": ["head_high"], "text": "Cabeça alta.", "visible": True, "confidence": 1.0}
    assert seen["headers"]["x-api-key"] == "k"
    content = seen["body"]["messages"][0]["content"]
    assert content[0]["type"] == "image" and "raia 2" in content[1]["text"]
    assert "head_high" in content[1]["text"] and "knees_wide" not in content[1]["text"]


def test_ai_not_visible_means_no_items_and_no_key_fails():
    def post(*_):
        return {"content": [{"type": "text", "text": '{"items":["head_high"],"visible":false}'}]}

    assert ai.suggest(b"x", "breaststroke", "breath", None, api_key="k", post=post)["items"] == []
    with pytest.raises(ai.AIError):
        ai.suggest(b"x", "breaststroke", "breath", None, api_key="")
    with pytest.raises(ai.AIError):
        ai.parse_answer("sem json", ["a"])


def test_report_shows_confirmed_frames_with_ring():
    race, evs = three_lanes()
    race = race.model_copy(update={"stroke": Stroke.BREASTSTROKE})
    tl = build_timeline(race, evs, compute_metrics(race, athlete_events(evs, None, None)),
                        width=1000, height=2000)  # fmt: skip
    notes = clean_notes(
        "breaststroke",
        [
            {"id": "a", "frame": 120, "t": 4.0, "lane": 1, "phase": "breath",
             "items": ["head_high"], "mark": [500, 1000]},
            {"id": "b", "frame": 200, "t": 6.0, "lane": 2, "phase": "kick",
             "items": ["knees_wide"], "confirmed": False},
        ],
    )  # fmt: skip
    rep = build_report(tl, [e for e in evs if e.type != E.STROKE], tech_notes=notes)
    assert len(rep["technique"]) == 1
    card = rep["technique"][0]
    assert card["title"] == "Raia 1 · Respiração e cabeça · 4,00 s"
    assert card["mark"] == [50.0, 50.0]
    page = render_html(rep, frame_url=lambda n, z=None: f"/q/{n}.jpg")
    assert "/q/120.jpg" in page and "/q/200.jpg" not in page and "class='ring'" in page


def test_measured_slow_start_is_not_repeated_by_the_checklist():
    notes = [{"lane": None, "items": ["start_late", "start_arms"], "confirmed": True}]
    fb = notes_feedback("freestyle", notes, False, ["Saída lenta, 1,20 s do apito."])
    assert not any("reagir" in x for x in fb["improve"]) and len(fb["improve"]) == 1
    assert len(notes_feedback("freestyle", notes, False)["improve"]) == 2


def test_zoom_box_stays_inside_the_frame():
    from swimcv.report.technique import zoom_box

    assert zoom_box(1080, 1920, 540, 960) == (216, 717, 648, 486)
    x0, y0, w, h = zoom_box(1080, 1920, 5, 1915)  # canto: encosta na borda
    assert (x0, y0 + h) == (0, 1920)
    x0, y0, w, h = zoom_box(1920, 1080, 1900, 10)  # deitado
    assert x0 + w == 1920 and y0 == 0 and w / h == pytest.approx(4 / 3, abs=0.01)
