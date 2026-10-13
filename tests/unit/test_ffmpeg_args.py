"""As opções do ffmpeg dependem da versão instalada (4.4 na imagem GPU, 5.1 na CPU, 6+ local)."""

from unittest.mock import patch

import pytest

from swimcv.ingest import run


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ((4, 4), ["-vsync", "passthrough", "-enc_time_base", "-1"]),
        ((5, 1), ["-fps_mode", "passthrough", "-enc_time_base", "-1"]),
        ((6, 1), ["-fps_mode", "passthrough", "-enc_time_base", "-1"]),
        ((7, 1), ["-fps_mode", "passthrough", "-enc_time_base", "demux"]),
    ],
)
def test_passthrough_args_by_version(version, expected):
    with patch.object(run, "ffmpeg_version", return_value=version):
        assert run.passthrough_args() == expected


def test_proxy_command_uses_version_aware_args(tmp_path):
    seen = {}

    def fake_run(cmd):
        seen["cmd"] = cmd
        return ""

    with (
        patch.object(run, "ffmpeg_version", return_value=(4, 4)),
        patch.object(run, "_run", side_effect=fake_run),
    ):
        run.make_proxy(tmp_path / "in.mp4", tmp_path / "out.mp4", has_audio=False)
    cmd = seen["cmd"]
    assert "demux" not in cmd and "-fps_mode" not in cmd
    assert cmd[cmd.index("-vsync") + 1] == "passthrough"


@pytest.mark.parametrize(
    ("text", "version"),
    [
        ("ffmpeg version 4.4.2-0ubuntu0.22.04.1 Copyright", (4, 4)),
        ("ffmpeg version 5.1.9-0+deb12u1 Copyright", (5, 1)),
        ("ffmpeg version n7.1 Copyright", (7, 1)),
    ],
)
def test_version_parsing(text, version):
    class P:
        stdout = text

    run.ffmpeg_version.cache_clear()
    try:
        with patch.object(run.subprocess, "run", return_value=P()):
            assert run.ffmpeg_version() == version
    finally:
        run.ffmpeg_version.cache_clear()
