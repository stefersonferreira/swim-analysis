"""Teste de fumaça da interface com um navegador real (Playwright).

Uso (com o sistema rodando em http://localhost:8080 ou BASE_URL):
    uv run --with playwright python tests/e2e/ui_smoke.py caminho/do/video.mp4 [pasta_capturas]

Faz upload, abre a revisão, marca eventos pelo teclado, calibra com 4 cliques, dá posição a
um evento clicando no quadro e confere que as métricas aparecem. Salva capturas de tela.
"""

import os
import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get("BASE_URL", "http://localhost:8080")


def main(video: str, out: str = "e2e-shots") -> None:
    shots = Path(out)
    shots.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        page.goto(f"{BASE}/upload")
        page.set_input_files("input[type=file]", video)
        page.get_by_label("Nome da prova").fill("Teste 50 livre")
        page.get_by_label("Atleta").fill("Atleta Teste")
        page.get_by_label("Piscina").select_option("25yd")
        page.get_by_label("Tempo final oficial").fill("21,80")
        page.get_by_label("Parcial oficial 25 jd").fill("10,58")
        page.get_by_label("Tempo final oficial").press("Tab")
        page.screenshot(path=shots / "01-upload.png")
        page.get_by_role("button", name="Enviar").click()

        page.wait_for_url(f"{BASE}/")
        link = page.get_by_role("link", name="Teste 50 livre").first
        expect(link).to_be_visible(timeout=180_000)
        page.screenshot(path=shots / "02-lista.png")
        link.click()

        frame_img = page.locator(".frame img")
        expect(frame_img).to_be_visible(timeout=30_000)
        page.wait_for_timeout(800)

        # Calibração: âncora no quadro 0 com 4 pontos formando um quadrilátero
        page.get_by_role("button", name="Calibração").click()
        page.get_by_role("button", name="+ Âncora neste quadro (0)").click()
        svg = page.locator(".frame svg")
        box = svg.bounding_box()
        pos = page.get_by_label("Posição ao longo (m)")
        last = pos.locator("option").count() - 1
        clicks = [  # (fração x, fração y) na imagem, (corda, índice da posição: parede/oposta)
            ((0.20, 0.42), (0, 0)),
            ((0.80, 0.30), (0, last)),
            ((0.10, 0.85), (3, 0)),
            ((0.90, 0.60), (3, last)),
        ]
        for (fx, fy), (rope, xi) in clicks:
            page.get_by_label("Corda").select_option(str(rope))
            pos.select_option(index=xi)
            page.mouse.click(box["x"] + fx * box["width"], box["y"] + fy * box["height"])
        page.get_by_role("button", name="Salvar e calcular").click()
        expect(page.get_by_text("Aceita")).to_be_visible(timeout=10_000)
        page.screenshot(path=shots / "03-calibracao.png")

        # Revisão: marcar eventos pelo teclado
        page.get_by_role("button", name="Revisão").click()
        page.locator("body").click(position={"x": 5, "y": 5})
        kb = page.keyboard
        kb.press("I")  # sinal de largada no quadro 0
        for _ in range(2):
            kb.press("Shift+ArrowRight")
        kb.press("O")  # pés fora no quadro 20
        for _ in range(9):
            kb.press("Shift+ArrowRight")
        kb.press("B")  # breakout no quadro 110 + posição com clique
        page.mouse.click(box["x"] + 0.45 * box["width"], box["y"] + 0.6 * box["height"])
        for i in range(10):
            for _ in range(15):
                kb.press("ArrowRight")
            kb.press("S")
            if i in (2, 9):
                page.mouse.click(
                    box["x"] + (0.5 + 0.03 * i) * box["width"], box["y"] + 0.55 * box["height"]
                )
        page.wait_for_timeout(500)
        expect(page.locator(".timeline rect[data-ev]")).to_have_count(13)
        page.screenshot(path=shots / "04-revisao.png")

        # Navegação: [ volta à braçada anterior, Del apaga
        kb.press("[")
        kb.press("Delete")
        page.wait_for_timeout(400)
        expect(page.locator(".timeline rect[data-ev]")).to_have_count(12)
        metrics = page.locator(".metrics").inner_text()
        assert "Reação" in metrics and "0,67" in metrics, metrics  # 20 quadros a 30 fps
        assert "21,80 s" in metrics and "10,58 s" in metrics, metrics
        # o clique logo depois da tecla B deu posição ao breakout
        bo_row = page.locator(".metrics tr", has_text="Breakout da largada").inner_text()
        assert "jd" in bo_row, bo_row
        page.screenshot(path=shots / "05-metricas.png", full_page=True)

        if errors:
            raise SystemExit(f"erros de JavaScript: {errors}")
        browser.close()
    print("ok:", ", ".join(sorted(x.name for x in shots.iterdir())))


if __name__ == "__main__":
    main(*sys.argv[1:])
