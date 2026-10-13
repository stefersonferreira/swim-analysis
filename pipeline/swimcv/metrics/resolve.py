"""Converte pontos clicados (image_xy) em posição na piscina (x_m) usando a calibração."""

from swimcv.calibration.homography import project
from swimcv.contracts import Calibration, Event


def resolve_positions(events: list[Event], calibration: Calibration | None) -> list[Event]:
    """Devolve cópias dos eventos com x_m preenchido onde houver clique e calibração.

    Etapa 1 (câmera parada): usa a âncora aceita mais próxima no tempo (em quadros).
    A propagação quadro a quadro para câmera em movimento entra na entrega 5.
    """
    accepted = [r for r in (calibration.results if calibration else []) if r.accepted]
    out = []
    for e in events:
        if e.image_xy is None or not accepted:
            out.append(e)
            continue
        anchor = min(accepted, key=lambda r: abs(r.frame - e.frame))
        x, _y = project(anchor.homography, [e.image_xy])[0]
        out.append(e.model_copy(update={"x_m": float(x)}))
    return out
