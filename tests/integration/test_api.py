"""Fluxo completo pela API: upload -> ingestão -> eventos manuais -> calibração -> métricas.

Precisa de PostgreSQL (TEST_DATABASE_URL). No CI ele roda como serviço; localmente:
TEST_DATABASE_URL=postgresql+psycopg://swim:swim@localhost:5432/swim_test
"""

import json
import os

import cv2
import numpy as np
import pytest

from tests.conftest import decode_index, make_vfr_video

DB_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.postgres,
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

    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c


@pytest.fixture(scope="module")
def video(client, tmp_path_factory):
    src = tmp_path_factory.mktemp("src") / "prova.mp4"
    make_vfr_video(src)
    race = {"stroke": "freestyle", "distance": 50, "pool_length": 25, "pool_unit": "m"}
    with src.open("rb") as f:
        r = client.post(
            "/api/videos",
            files={"file": ("prova.mp4", f, "video/mp4")},
            data={"race": json.dumps(race), "title": "Teste"},
        )
    assert r.status_code == 201, r.text
    vid = r.json()["id"]
    v = client.get(f"/api/videos/{vid}").json()
    assert v["status"] == "ready", v
    return v


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/system/worker").json()["worker"] == "eager"


def test_ingested_video_and_exact_frames(client, video):
    assert video["meta"]["n_frames"] == 90
    pts = client.get(f"/api/videos/{video['id']}/frames.json").json()["pts"]
    assert len(pts) == 90 and pts[0] == 0
    for n in (0, 17, 45, 89):
        r = client.get(f"/api/videos/{video['id']}/frames/{n}.jpg")
        img = cv2.imdecode(np.frombuffer(r.content, np.uint8), cv2.IMREAD_COLOR)
        assert decode_index(img) == n
    assert client.get(f"/api/videos/{video['id']}/frames/90.jpg").status_code == 404
    r = client.get(f"/api/videos/{video['id']}/proxy.mp4", headers={"Range": "bytes=0-99"})
    assert r.status_code == 206 and len(r.content) == 100


def test_bad_upload_rejected(client):
    r = client.post(
        "/api/videos", files={"file": ("x.avi", b"123", "video/avi")}, data={"race": "{}"}
    )
    assert r.status_code == 422


def test_events_metrics_and_calibration(client, video):
    vid = video["id"]
    pts = client.get(f"/api/videos/{vid}/frames.json").json()["pts"]
    body = {
        "create": [
            {"type": "start_signal", "frame": 3},
            {"type": "feet_off", "frame": 25},
            {"type": "breakout", "frame": 60, "image_xy": [400, 300]},
        ],
        "author": "teste",
    }
    r = client.patch(f"/api/videos/{vid}/events", json=body)
    assert r.status_code == 200, r.text
    out = r.json()
    assert len(out["created_ids"]) == 3
    reaction = next(m for m in out["metrics"] if m["name"] == "reaction_s")
    assert reaction["value"] == pytest.approx(pts[25] - pts[3])  # tempo real (VFR), não 22/30
    bo = next(e for e in out["events"] if e["type"] == "breakout")
    assert bo["x_m"] is None  # ainda sem calibração

    # Calibração: piscina em vista "de cima" sintética, 40 px por metro, origem em (100, 100)
    pool = {"length_m": 25, "lanes": 6, "lane_width_m": 2.5}
    pts_pool = [(0, 0), (25, 0), (0, 15), (25, 15), (15, 7.5)]
    anchor = {
        "frame": 10,
        "points": [
            {"image_xy": [100 + 40 * x, 100 + 40 * y], "pool_xy": [x, y]} for x, y in pts_pool
        ],
    }
    r = client.put(f"/api/videos/{vid}/calibration", json={"pool": pool, "anchors": [anchor]})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["calibration"]["results"][0]["accepted"]
    assert res["grids"]["10"]
    bo = next(e for e in res["events"] if e["type"] == "breakout")
    assert bo["x_m"] == pytest.approx((400 - 100) / 40)  # 7,5 m

    # Mover e apagar ficam no histórico; o tempo acompanha o quadro
    r = client.patch(f"/api/videos/{vid}/events", json={"update": [{"id": bo["id"], "frame": 61}]})
    bo2 = next(e for e in r.json()["events"] if e["id"] == bo["id"])
    assert bo2["t"] == pytest.approx(pts[61])
    r = client.patch(f"/api/videos/{vid}/events", json={"delete": [bo["id"]]})
    assert all(e["id"] != bo["id"] for e in r.json()["events"])


def test_race_update_changes_units(client, video):
    vid = video["id"]
    race = {"stroke": "breaststroke", "distance": 50, "pool_length": 25, "pool_unit": "yd"}
    assert client.put(f"/api/videos/{vid}/race", json=race).status_code == 200
    out = client.get(f"/api/videos/{vid}/metrics").json()
    assert out["race"]["stroke"] == "breaststroke"
    assert any(m["name"] == "wall_time_s" for m in out["metrics"])
