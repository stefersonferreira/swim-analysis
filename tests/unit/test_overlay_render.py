"""MP4 com a sobreposição: desenho de um quadro e gravação com ffmpeg."""

import shutil
import subprocess

import av
import numpy as np
import pytest
from PIL import Image

from swimcv.metrics import compute_metrics
from swimcv.overlay import build_timeline
from swimcv.overlay.render import END_HOLD_S, Painter, render_mp4
from tests.unit.test_metrics import reference_free_50m


def timeline(**kw):
    race, evs = reference_free_50m()
    return build_timeline(
        race, evs, compute_metrics(race, evs), title="50 livre", width=640, height=360, **kw
    )


def test_draw_changes_pixels_where_expected():
    tl = timeline()
    frame = Image.new("RGB", (640, 360), (40, 120, 180))
    p = Painter(tl, 640, 360)
    out = np.asarray(p.draw(frame, 8.0), int)
    base = np.asarray(frame, int)
    diff = np.abs(out - base).sum(axis=2) > 30
    assert diff[10:60, 10:110].mean() > 0.5  # cartão do relógio
    assert diff[10:60, -100:-10].mean() > 0.5  # painel da piscina
    assert diff[180:250, 280:360].mean() < 0.05  # meio do quadro livre (sem nadador)
    # escala junto com o quadro: 2x maior desenha no mesmo lugar relativo
    big = np.asarray(Painter(tl, 1280, 720).draw(frame.resize((1280, 720)), 8.0), int)
    assert np.abs(big[::2, ::2] - out).mean() < 12


def test_summary_card_at_end():
    tl = timeline()
    frame = Image.new("RGB", (640, 360), (40, 120, 180))
    out = np.asarray(Painter(tl, 640, 360).draw(frame, 30.0, force_summary=True), int)
    centre = out[150:210, 260:380]
    assert centre.mean() < 80  # cartão escuro no centro


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg não instalado")
def test_render_mp4_with_audio_and_end_card(tmp_path):
    src = tmp_path / "proxy.mp4"
    wav = tmp_path / "audio.wav"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30:duration=3",
         "-c:v", "libx264", "-g", "1", "-pix_fmt", "yuv420p", str(src)],
        check=True,
    )  # fmt: skip
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=3", str(wav)],
        check=True,
    )
    pts = np.arange(90) / 30
    seen = []
    out = render_mp4(
        src, pts, timeline(), tmp_path / "o.mp4", audio=wav, fps=30, progress=seen.append
    )
    with av.open(str(out)) as c:
        v = c.streams.video[0]
        n = sum(1 for _ in c.decode(v))
        assert (v.codec_context.width, v.codec_context.height) == (640, 360)
        assert len(c.streams.audio) == 1
    assert n == 90 + int(END_HOLD_S * 30)
    assert seen[-1] == 1.0


def test_portrait_video_uses_bigger_panels():
    """Celular em pé: painéis em 2,2% da largura por unidade, como o --u da tela."""
    from swimcv.overlay.render import PORTRAIT_SCALE

    tl = timeline()
    land = Painter(tl, 1280, 720)
    port = Painter(tl, 720, 1280)
    assert port.u == pytest.approx(7.2 * PORTRAIT_SCALE)
    assert land.u == pytest.approx(12.8)
    frame = Image.new("RGB", (720, 1280), (40, 120, 180))
    out = np.asarray(port.draw(frame, 8.0), int)
    diff = np.abs(out - np.asarray(frame, int)).sum(axis=2) > 30
    # cartão do relógio ocupa uma faixa larga no alto, sem sair do quadro
    assert diff[30:150, 30:250].mean() > 0.4
    assert not diff[:, -2:].all()


def test_lanes_board_and_comparison_summary():
    from swimcv.metrics import athlete_events
    from tests.unit.test_lanes import three_lanes

    race, evs = three_lanes()
    tl = build_timeline(
        race,
        evs,
        compute_metrics(race, athlete_events(evs, None, None)),
        width=640,
        height=360,
        duration_s=23.4,
    )
    frame = Image.new("RGB", (640, 360), (40, 120, 180))
    base = np.asarray(frame, int)
    live = np.abs(np.asarray(Painter(tl, 640, 360).draw(frame, 12.0), int) - base).sum(axis=2) > 30
    assert live[15:70, -120:-15].mean() > 0.5  # quadro das raias no canto
    assert live[300:350, 100:540].mean() < 0.05  # sem barra de progresso de um atleta só
    end = np.abs(np.asarray(Painter(tl, 640, 360).draw(frame, 23.35), int) - base).sum(axis=2) > 30
    assert end[150:210, 220:420].mean() > 0.5  # comparativo no meio


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg não instalado")
def test_render_mp4_lanes_without_main_finish(tmp_path):
    """Várias raias sem chegada do atleta da prova: o fim com o comparativo é gravado
    (antes quebrava em t_finish=None e travava esperando o ffmpeg)."""
    from swimcv.metrics import athlete_events
    from tests.unit.test_lanes import three_lanes

    src = tmp_path / "proxy.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=30:duration=1",
         "-c:v", "libx264", "-g", "1", "-pix_fmt", "yuv420p", str(src)],
        check=True,
    )  # fmt: skip
    race, evs = three_lanes()
    tl = build_timeline(
        race,
        evs,
        compute_metrics(race, athlete_events(evs, None, None)),
        width=320,
        height=180,
        duration_s=1.0,
    )
    assert tl["t_finish"] is None
    out = render_mp4(src, np.arange(30) / 30, tl, tmp_path / "o.mp4", fps=30)
    with av.open(str(out)) as c:
        n = sum(1 for _ in c.decode(c.streams.video[0]))
    assert n == 30 + int(END_HOLD_S * 30)


def test_render_mp4_drawing_error_does_not_hang(tmp_path, monkeypatch):
    """Erro ao desenhar um quadro sobe como erro, sem deixar o ffmpeg esperando."""
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg não instalado")
    src = tmp_path / "proxy.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=30:duration=1",
         "-c:v", "libx264", "-g", "1", "-pix_fmt", "yuv420p", str(src)],
        check=True,
    )  # fmt: skip

    def boom(*a, **k):
        raise ValueError("falha de desenho")

    monkeypatch.setattr(Painter, "draw", boom)
    with pytest.raises(ValueError):
        render_mp4(src, np.arange(30) / 30, timeline(), tmp_path / "o.mp4", fps=30)
    assert not (tmp_path / "o.mp4").exists()
