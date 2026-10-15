"""Rascunho da devolutiva do treinador.

Sai só dos números medidos (a mesma linha do tempo do vídeo) e é um ponto de partida: o
treinador revisa, apaga e completa antes de entregar. Nada aqui afirma o que não foi medido.
Função pura.
"""

from __future__ import annotations

from statistics import mean, pstdev

from swimcv.overlay.timeline import br, clock_text

SLOW_REACTION_S = 1.0  # do apito até sair do bloco
GOOD_REACTION_S = 0.8
STEADY_CV = 0.08  # variação do tempo de ciclo abaixo disso = ritmo constante
FADE = 0.10  # ciclo 10% mais lento no fim = ritmo caiu


def _cycles(strokes: list[list]) -> list[float]:
    return [tp for _, tp in strokes if tp]


def _pace_points(
    name: str, cycles: list[float], word: str, out: dict, rate: float | None = None
) -> None:
    """rate: o ritmo que o vídeo e o relatório mostram (para os números baterem)."""
    if len(cycles) < 3:
        return
    avg = mean(cycles)
    cv = pstdev(cycles) / avg if avg else 0.0
    if cv <= STEADY_CV:
        out["strengths"].append(
            f"{name}: ritmo constante, {rate or 60 / avg:.0f} {word}/min sem perder o padrão."
        )
    half = len(cycles) // 2
    first, last = mean(cycles[:half]), mean(cycles[half:])
    if first and last > first * (1 + FADE):
        out["improve"].append(
            f"{name}: o ritmo cai ao longo do trecho medido "
            f"({60 / first:.0f} para {60 / last:.0f} {word}/min)."
        )
        out["drills"].append(
            f"{name}: séries curtas no ritmo de prova (ex.: 6 × 12,5 m) mantendo {60 / first:.0f} "
            f"{word}/min do começo ao fim."
        )


def _start_points(name: str, delay: float | None, kind: str | None, out: dict) -> None:
    if delay is None or kind not in ("feet_off", "entry"):
        return
    # entrar na água leva ~0,3 s a mais que sair do bloco
    extra = 0.3 if kind == "entry" else 0.0
    what = "até deixar o bloco" if kind == "feet_off" else "até entrar na água"
    if delay >= SLOW_REACTION_S + extra:
        out["improve"].append(f"{name}: saída lenta, {br(delay)} s do apito {what}.")
        out["drills"].append(
            f"{name}: saídas ao apito, 6 a 8 saídas curtas (até os 5 m) reagindo ao som, "
            "descanso completo."
        )
    elif delay <= GOOD_REACTION_S + extra:
        out["strengths"].append(f"{name}: boa reação na saída ({br(delay)} s do apito {what}).")


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def draft_feedback(tl: dict) -> dict:
    """{summary, strengths[], improve[], drills[]} a partir da linha do tempo."""
    out: dict = {"summary": "", "strengths": [], "improve": [], "drills": []}
    breast = tl.get("stroke_word") == "Ciclos"
    # ritmo é sempre por ciclo (no crawl, um ciclo = 2 braçadas)
    word = "ciclos"
    lanes = tl.get("lanes") or []

    if lanes:
        done = sorted((lr for lr in lanes if lr["final_time"]), key=lambda lr: lr["final_time"])
        if len(done) >= 2:
            a, b = done[0], done[1]
            out["summary"] = (
                f"A raia {a['lane']} chegou {br(b['final_time'] - a['final_time'])} s à frente "
                f"da raia {b['lane']} ({clock_text(a['final_time'])} s contra "
                f"{clock_text(b['final_time'])} s)."
            )
        elif done:
            out["summary"] = (
                f"Raia {done[0]['lane']}: {clock_text(done[0]['final_time'])} s nos "
                f"{tl['distance']} m."
            )
        for lr in sorted(lanes, key=lambda lr: lr["lane"]):
            name = f"Raia {lr['lane']}"
            _start_points(name, lr["start_delay"], lr["start_delay_kind"], out)
            _pace_points(name, _cycles(lr["strokes"]), word, out, lr["rate"])
        rated = [lr for lr in lanes if lr["rate"]]
        if len(rated) >= 2:
            lo, hi = min(rated, key=lambda lr: lr["rate"]), max(rated, key=lambda lr: lr["rate"])
            if hi["rate"] - lo["rate"] >= 6:
                out["improve"].append(
                    f"Raia {lo['lane']}: ritmo de {lo['rate']:.0f} {word}/min, contra "
                    f"{hi['rate']:.0f} da raia {hi['lane']}."
                )
                if breast:
                    out["drills"].append(
                        f"Raia {lo['lane']}: peito com deslize mais curto, contando os ciclos por "
                        "piscina e tentando 1 a 2 ciclos a mais no mesmo tempo."
                    )
                else:
                    out["drills"].append(
                        f"Raia {lo['lane']}: crawl com frequência mais alta em trechos curtos "
                        "(ex.: 8 × 12,5 m forte), sem encurtar a braçada."
                    )
    else:
        rows = dict(tl.get("summary") or [])
        final = tl.get("clock_end")
        if final:
            out["summary"] = f"Tempo de {clock_text(final)} s nos {tl['distance']} m."
            if rows.get("Ritmo"):
                out["summary"] += f" Ritmo médio de {rows['Ritmo']}."
        name = "Atleta"
        reaction = None
        for k, v in rows.items():
            if k == "Reação":
                reaction = float(v.split()[0].replace(",", "."))
        _start_points(name, reaction, "feet_off", out)
        cycles = [tp for ln in tl.get("lengths", []) for _, tp in ln["strokes"] if tp]
        tempo_row = rows.get("Tempo de ciclo")
        rate = 60 / float(tempo_row.split()[0].replace(",", ".")) if tempo_row else None
        _pace_points(name, cycles, word, out, rate)

    if not (out["strengths"] or out["improve"]):
        out["improve"].append(
            "Poucos momentos marcados para apontar pontos fortes e de melhora: marque saída, "
            "ciclos e toque."
        )
    # nomes só fazem sentido com mais de um atleta
    if not lanes:
        for k in ("strengths", "improve", "drills"):
            out[k] = [_cap(s.removeprefix("Atleta: ")) for s in out[k]]
    return out
