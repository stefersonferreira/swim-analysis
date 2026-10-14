"""Teste de fumaça da análise automática com navegador real.

Uso (sistema rodando em BASE_URL, padrão http://localhost:8080):
    uv run --with playwright python tests/e2e/auto_smoke.py prova_sintetica.mp4 [capturas]

A prova sintética vem de tests/synthetic.py (câmera parada). Envia pela tela, calibra pela API
com os pontos exatos, espera a análise automática terminar e confere na tela: eventos
automáticos, marcador do nadador e métricas preenchidas sem nenhuma marcação manual.
"""

import json
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get("BASE_URL", "http://localhost:8080")


def main(video: str, out: str = "e2e-auto-shots", points_json: str | None = None) -> None:
    shots = Path(out)
    shots.mkdir(exist_ok=True)
    points = json.loads(Path(points_json).read_text()) if points_json else None
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        page.goto(f"{BASE}/upload")
        page.set_input_files("input[type=file]", video)
        page.get_by_label("Nome da prova").fill("Automática 50 livre")
        page.get_by_label("Raia (necessária para a análise automática)").fill("4")
        page.get_by_role("button", name="Enviar").click()
        page.wait_for_url(f"{BASE}/")
        link = page.get_by_role("link", name="Automática 50 livre").first
        expect(link).to_be_visible(timeout=300_000)
        vid = link.get_attribute("href").rstrip("/").split("/")[-1]

        # largada automática já existe depois da ingestão
        evs = page.request.get(f"{BASE}/api/videos/{vid}/events").json()["events"]
        assert any(e["type"] == "start_signal" and e["source"] == "auto" for e in evs), evs

        if points is None:
            sys.path[:0] = ["pipeline", "."]
            from tests.synthetic import FPS, Truth, anchor_points

            points = anchor_points(150 / FPS, False, Truth())
        body = {
            "pool": {"length_m": 25, "lanes": 8, "lane_width_m": 2.5},
            "anchors": [{"frame": 150, "points": points}],
        }
        r = page.request.put(f"{BASE}/api/videos/{vid}/calibration", data=body)
        assert r.ok, r.text()

        deadline = time.time() + 600
        while time.time() < deadline:
            v = page.request.get(f"{BASE}/api/videos/{vid}").json()
            if v["analysis_status"] in ("done", "failed"):
                break
            time.sleep(2)
        assert v["analysis_status"] == "done", v

        page.goto(f"{BASE}/videos/{vid}")
        expect(page.get_by_text("Análise automática:")).to_be_visible(timeout=30_000)
        expect(page.locator(".analysis-bar.done")).to_be_visible()
        # vai para 8 s (nado) e confere o marcador do nadador
        page.locator("body").click(position={"x": 5, "y": 5})
        for _ in range(24):
            page.keyboard.press("Shift+ArrowRight")
        expect(page.locator(".swimmer circle")).to_be_visible()
        page.wait_for_timeout(800)
        page.screenshot(path=shots / "auto-revisao.png", full_page=True)
        # sobreposição ao vivo: relógio de prova, fase e braçadas da piscina
        expect(page.locator(".fx-overlay")).to_be_visible()
        expect(page.get_by_test_id("fx-phase")).to_have_text("Nadando")
        assert page.get_by_test_id("fx-clock").inner_text().strip() not in ("", "–")
        assert int(page.get_by_test_id("fx-strokes").inner_text()) > 0
        page.locator(".frame").screenshot(path=shots / "auto-sobreposicao.png")
        n_ev = page.locator(".timeline rect[data-ev]").count()
        assert n_ev >= 30, n_ev
        metrics = page.locator(".metrics").inner_text()
        assert "15 m da largada" in metrics
        row = page.locator(".metrics tr", has_text="Braçadas").inner_text()
        assert "—" not in row.split("\t")[1], row
        if errors:
            raise SystemExit(f"erros de JavaScript: {errors}")
        browser.close()
    print("ok:", ", ".join(sorted(x.name for x in shots.iterdir())))


if __name__ == "__main__":
    main(*sys.argv[1:])
