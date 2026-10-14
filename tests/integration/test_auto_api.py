"""Fluxo automático pela API: envio -> largada pelo áudio -> calibração -> análise automática.

Usa a prova sintética com câmera parada (verdade conhecida). PostgreSQL em TEST_DATABASE_URL.
"""

import json
import os

import pytest

from tests.synthetic import FPS, anchor_points

DB_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.postgres,
    pytest.mark.slow,
    pytest.mark.skipif(not DB_URL, reason="defina TEST_DATABASE_URL para rodar"),
]


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    data = tmp_path_factory.mktemp("data")
    os.environ.update(
        SWIM_DATABASE_URL=DB_URL,
        SWIM_DATA_DIR=str(data),
        SWIM_TASK_ALWAYS_EAGER="1",
        SWIM_STATIC_DIR=str(data / "nostatic"),
    )
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text

    eng = create_engine(DB_URL)
    with eng.begin() as conn:
        conn.execute(text("drop schema public cascade; create schema public"))
    eng.dispose()
    command.upgrade(Config("alembic.ini"), "head")
    from fastapi.testclient import TestClient

    from app.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture(scope="module")
def video(client, synthetic_videos):
    src, moving, truth = synthetic_videos["static"]
    race = {"stroke": "freestyle", "distance": 50, "pool_length": 25, "lane": truth.lane}
    with src.open("rb") as f:
        r = client.post(
            "/api/videos",
            files={"file": ("sint.mp4", f, "video/mp4")},
            data={"race": json.dumps(race), "title": "Sintética"},
        )
    assert r.status_code == 201, r.text
    return r.json()["id"], moving, truth


def test_start_signal_is_automatic_after_upload(client, video):
    vid, _, truth = video
    evs = client.get(f"/api/videos/{vid}/events").json()["events"]
    (start,) = [e for e in evs if e["type"] == "start_signal"]
    assert start["source"] == "auto"
    assert start["t"] == pytest.approx(truth.start_t, abs=0.02)


def test_calibration_triggers_analysis(client, video):
    vid, moving, truth = video
    a = 150
    pts = anchor_points(a / FPS, moving, truth)
    body = {
        "pool": {"length_m": 25, "lanes": 8, "lane_width_m": 2.5},
        "anchors": [{"frame": a, "points": pts}],
    }
    r = client.put(f"/api/videos/{vid}/calibration", json=body)
    assert r.status_code == 200, r.text
    v = client.get(f"/api/videos/{vid}").json()
    assert v["analysis_status"] == "done", v["analysis_notes"]
    out = client.get(f"/api/videos/{vid}/events").json()
    kinds = {e["type"] for e in out["events"]}
    assert {
        "start_signal",
        "entry",
        "breakout",
        "stroke",
        "wall_feet",
        "finish_touch",
        "mark_pass",
    } <= kinds
    assert all(e["source"] == "auto" for e in out["events"])
    m = {(x["name"], x["length_index"], x["turn_index"]): x for x in out["metrics"]}
    assert m[("strokes", 0, None)]["value"] == pytest.approx(15, abs=1)
    assert m[("start_15m_s", None, None)]["status"] == "ok"
    traj = client.get(f"/api/videos/{vid}/trajectory.json").json()["frames"]
    assert len(traj["frame"]) > 600
    grid = client.get(f"/api/videos/{vid}/grid/300").json()["lines"]
    assert len(grid) == 9 + 6  # 9 cordas + linhas a cada 5 m (0..25)
    # sobreposição: balões de 15 m, parcial e chegada, nadador na imagem
    tl = client.get(f"/api/videos/{vid}/overlay.json").json()
    kinds = [c["kind"] for c in tl["callouts"]]
    assert {"15m", "split", "finish"} <= set(kinds), kinds
    assert tl["clock_end"] == pytest.approx(truth.finish_t - truth.start_t, abs=0.15)
    assert sum(x is not None for x in tl["track"]["x"]) > 100


def test_reanalysis_keeps_corrections(client, video):
    vid, *_ = video
    evs = client.get(f"/api/videos/{vid}/events").json()["events"]
    strokes = [e for e in evs if e["type"] == "stroke"]
    moved, removed = strokes[3], strokes[5]
    client.patch(
        f"/api/videos/{vid}/events",
        json={
            "update": [{"id": moved["id"], "frame": moved["frame"] + 1}],
            "delete": [removed["id"]],
        },
    )
    assert client.post(f"/api/videos/{vid}/analyze").status_code == 202
    after = client.get(f"/api/videos/{vid}/events").json()["events"]
    kept = next(e for e in after if e["id"] == moved["id"])
    assert kept["source"] == "manual" and kept["frame"] == moved["frame"] + 1
    # a braçada apagada não volta e a corrigida não é duplicada
    near = [e for e in after if e["type"] == "stroke" and abs(e["t"] - removed["t"]) < 0.1]
    assert not near
    dup = [e for e in after if e["type"] == "stroke" and abs(e["t"] - moved["t"]) < 0.1]
    assert len(dup) <= 1


def test_analysis_requires_lane(client, video):
    vid, *_ = video
    race = {"stroke": "freestyle", "distance": 50, "pool_length": 25}
    client.put(f"/api/videos/{vid}/race", json=race)
    r = client.post(f"/api/videos/{vid}/analyze")
    assert r.status_code == 409 and "raia" in r.json()["detail"]
