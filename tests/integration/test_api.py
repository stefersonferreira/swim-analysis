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
    race = {"stroke": "freestyle", "distance": 50, "pool_length": 25}
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


def test_race_update(client, video):
    vid = video["id"]
    race = {"stroke": "breaststroke", "distance": 100, "pool_length": 50}
    assert client.put(f"/api/videos/{vid}/race", json=race).status_code == 200
    out = client.get(f"/api/videos/{vid}/metrics").json()
    assert out["race"]["stroke"] == "breaststroke"
    assert any(m["name"] == "wall_time_s" for m in out["metrics"])
    bad = {"stroke": "freestyle", "distance": 50, "pool_length": 23}
    assert client.put(f"/api/videos/{vid}/race", json=bad).status_code == 422


def test_lanes_final_options_and_report(client, video):
    vid = video["id"]
    pts = client.get(f"/api/videos/{vid}/frames.json").json()["pts"]
    fr = [1, 5, 10, 20, len(pts) - 3, len(pts) - 2]
    create = [
        {"type": "start_signal", "frame": fr[0]},
        {"type": "feet_off", "frame": fr[1], "lane": 1},
        {"type": "feet_off", "frame": fr[2], "lane": 2},
        {"type": "finish_touch", "frame": fr[4], "lane": 2},
        {"type": "finish_touch", "frame": fr[5], "lane": 1},
    ]
    r = client.patch(f"/api/videos/{vid}/events", json={"create": create})
    assert r.status_code == 200, r.text
    r = client.put(
        f"/api/videos/{vid}/final-options",
        json={"strokes_partial": True, "notes": ["  Toque com margem de 0,2 s ", ""]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["strokes_partial"] is True
    assert r.json()["review_notes"] == ["Toque com margem de 0,2 s"]
    tl = client.get(f"/api/videos/{vid}/overlay.json").json()
    assert tl["strokes_partial"] and tl["notes"] == ["Toque com margem de 0,2 s"]
    assert [lr["lane"] for lr in tl["lanes"]] == [1, 2]
    page = client.get(f"/api/videos/{vid}/report.html")
    assert page.status_code == 200 and page.headers["content-type"].startswith("text/html")
    assert "Raia 2" in page.text and "Toque com margem de 0,2 s" in page.text
    assert "1º" in page.text


def test_client_order_feedback_and_delivery(client, tmp_path):
    src = tmp_path / "cliente.mp4"
    make_vfr_video(src)
    with src.open("rb") as f:
        r = client.post(
            "/api/public/orders",
            files={"file": ("cliente.mp4", f, "video/mp4")},
            data={"name": "Ana Souza", "phone": "(85) 99999-1234", "stroke": "breaststroke",
                  "pool_length": "25", "distance": "50", "notes": "melhorar a saída"},
        )  # fmt: skip
    assert r.status_code == 201, r.text
    token = r.json()["token"]
    # o cliente acompanha pelo link, sem ver nada interno
    st = client.get(f"/api/public/r/{token}").json()
    assert st["status"] == "new" and not st["delivered"] and st["first_name"] == "Ana"
    assert "feedback" not in st and st["due_at"]
    assert client.get(f"/api/public/r/{token}/report.html").status_code == 404
    # o treinador vê o pedido na lista, com prazo
    v = next(
        x for x in client.get("/api/videos").json() if x["order"]["share_path"].endswith(token)
    )
    assert v["order"]["origin"] == "client" and v["order"]["customer_notes"] == "melhorar a saída"
    assert v["race"]["stroke"] == "breaststroke" and v["race"]["distance"] == 50
    vid = v["id"]
    # entregar sem devolutiva é recusado
    assert client.post(f"/api/videos/{vid}/deliver").status_code == 409
    draft = client.post(f"/api/videos/{vid}/feedback/draft").json()
    assert set(draft) == {"summary", "strengths", "improve", "drills"}
    fb = {"summary": "Boa base.", "strengths": ["Ritmo regular"], "improve": [], "drills": ["  "]}
    r = client.put(f"/api/videos/{vid}/feedback", json=fb)
    assert r.json()["order"]["status"] == "reviewing"
    assert r.json()["order"]["feedback"]["drills"] == []
    r = client.put(f"/api/videos/{vid}/order", json={"paid": True})
    assert r.json()["order"]["paid"] is True
    r = client.post(f"/api/videos/{vid}/deliver")
    assert r.status_code == 200 and r.json()["order"]["status"] == "delivered"
    st = client.get(f"/api/public/r/{token}").json()
    assert st["delivered"] and st["feedback"]["summary"] == "Boa base."
    assert st["has_video"] is False and "table" in st
    page = client.get(f"/api/public/r/{token}/report.html").text
    assert "Devolutiva do treinador" in page and "Ritmo regular" in page
    assert client.get("/api/public/r/naoexiste").status_code == 404


def test_public_order_validation(client):
    bad = client.post(
        "/api/public/orders",
        files={"file": ("x.mp4", b"0", "video/mp4")},
        data={"name": "Bo", "stroke": "freestyle"},
    )
    assert bad.status_code == 422 and "WhatsApp" in bad.json()["detail"]
    bot = client.post(
        "/api/public/orders",
        files={"file": ("x.mp4", b"0", "video/mp4")},
        data={"name": "Bot", "email": "a@b.c", "website": "spam"},
    )
    assert bot.status_code == 400


def test_coach_password(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "admin_password", "segredo")
    client.cookies.clear()
    assert client.get("/api/videos").status_code == 401
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/auth/me").json() == {"auth_required": True, "logged_in": False}
    assert client.get("/api/public/r/naoexiste").status_code == 404  # público continua aberto
    assert client.post("/api/auth/login", json={"password": "errada"}).status_code == 401
    assert client.post("/api/auth/login", json={"password": "segredo"}).status_code == 200
    assert client.get("/api/videos").status_code == 200
    client.post("/api/auth/logout")
    client.cookies.clear()
    assert client.get("/api/videos").status_code == 401


def test_technique_notes_flow(client, video, monkeypatch):
    vid = video["id"]
    st = client.get(f"/api/videos/{vid}/technique").json()
    assert st["catalog"][0]["key"] == "start" and st["ai_enabled"] is False
    # outro teste pode ter trocado o estilo: usa os pontos do catálogo atual
    ph = {p["key"]: p for p in st["catalog"]}
    fix = next(i for i in ph["breath"]["items"] if not i["good"])
    other = next(i for i in ph["pull"]["items"] if not i["good"])
    notes = [
        {"id": "a", "frame": 30, "t": 1.0, "phase": "breath", "items": [fix["key"]],
         "mark": [100, 50]},
        {"id": "b", "frame": 40, "t": 1.3, "phase": "pull", "items": [other["key"]],
         "confirmed": False},
    ]  # fmt: skip
    r = client.put(f"/api/videos/{vid}/technique", json=notes)
    assert r.status_code == 200 and len(r.json()["tech_notes"]) == 2
    # só o confirmado entra no rascunho e no relatório
    fb = client.post(f"/api/videos/{vid}/feedback/draft").json()
    assert fix["text"] in fb["improve"], fb
    assert other["text"] not in fb["improve"]
    page = client.get(f"/api/videos/{vid}/report.html").text
    assert f"/api/videos/{vid}/frames/30.jpg" in page and "frames/40.jpg" not in page
    # IA sem chave: recusa clara; com chave, usa a resposta (rede simulada)
    ask = {"frame": 30, "phase": "breath", "lane": None, "mark": [100, 50]}
    r = client.post(f"/api/videos/{vid}/technique/ai", json=ask)
    assert r.status_code == 409 and "ANTHROPIC_API_KEY" in r.json()["detail"]
    from app.config import get_settings
    from swimcv.report import ai

    monkeypatch.setattr(get_settings(), "anthropic_api_key", "teste")
    sent = {}

    def fake_post(url, headers, body):
        sent["img"] = body["messages"][0]["content"][0]["source"]["data"]
        return {
            "content": [
                {"type": "text", "text": json.dumps({"items": [fix["key"]], "visible": True})}
            ]
        }

    monkeypatch.setattr(ai, "_post", fake_post)
    monkeypatch.setattr(
        ai.suggest, "__kwdefaults__", {**ai.suggest.__kwdefaults__, "post": fake_post}
    )
    r = client.post(f"/api/videos/{vid}/technique/ai", json=ask)
    assert r.status_code == 200, r.text
    assert r.json()["items"] == [fix["key"]] and sent["img"]
