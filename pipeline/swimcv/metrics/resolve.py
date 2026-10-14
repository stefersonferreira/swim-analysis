"""Converte pontos clicados (image_xy) em posição na piscina (x_m) usando a calibração."""

import numpy as np

from swimcv.calibration.homography import project
from swimcv.contracts import Calibration, Event


def resolve_positions(
    events: list[Event],
    calibration: Calibration | None,
    homographies: np.ndarray | None = None,
) -> list[Event]:
    """Devolve cópias dos eventos com x_m preenchido onde houver ponto na imagem.

    Com `homographies` (uma por quadro, câmera em movimento) usa a do próprio quadro; sem
    elas, a âncora aceita mais próxima no tempo (câmera parada).
    """
    accepted = [r for r in (calibration.results if calibration else []) if r.accepted]
    out = []
    for e in events:
        if e.image_xy is None or (not accepted and homographies is None):
            out.append(e)
            continue
        if homographies is not None and e.frame < len(homographies):
            h = homographies[e.frame]
        else:
            h = min(accepted, key=lambda r: abs(r.frame - e.frame)).homography
        x, _y = project(h, [e.image_xy])[0]
        out.append(e.model_copy(update={"x_m": float(x)}))
    return out
