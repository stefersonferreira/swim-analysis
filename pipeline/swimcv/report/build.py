# ruff: noqa: E501  (folha de estilo do relatório em linhas longas)
"""Relatório da análise.

Parte da mesma linha do tempo que desenha o vídeo (overlay.build_timeline), então os números
do relatório e do MP4 são sempre os mesmos. Só afirma o que foi medido: o que faltou aparece
como "–" e as observações de quem revisou vão junto.

Funções puras: build_report monta os dados; render_html só formata.
"""

from __future__ import annotations

import html
from datetime import date

from swimcv.contracts import Event, EventType
from swimcv.overlay.timeline import br, clock_text

E = EventType
DASH = "–"

MOMENT_LABEL = {
    E.START_SIGNAL: "Apito / largada",
    E.FEET_OFF: "Pés deixam o bloco",
    E.ENTRY: "Mãos na água",
    E.BREAKOUT: "Saiu à tona",
    E.WALL_HANDS: "Toque das mãos na virada",
    E.WALL_FEET: "Pés na parede",
    E.FINISH_TOUCH: "Toque final",
    E.MARK_PASS: "Passagem pela marca",
}


def _s(v: float | None, unit: str = " s") -> str:
    return DASH if v is None else f"{br(v)}{unit}"


def _lane_insights(lanes: list[dict], stroke_word: str) -> list[str]:
    done = sorted(
        (lr for lr in lanes if lr["final_time"] is not None), key=lambda lr: lr["final_time"]
    )
    out: list[str] = []
    if len(done) >= 2:
        a, b = done[0], done[1]
        gap = round(b["final_time"] - a["final_time"], 2)
        out.append(
            f"A raia {a['lane']} chegou {br(gap)} s à frente da raia {b['lane']} "
            f"({clock_text(a['final_time'])} s contra {clock_text(b['final_time'])} s)."
        )
        if (
            a["start_delay"] is not None
            and b["start_delay"] is not None
            and a["start_delay_kind"] == b["start_delay_kind"]
        ):
            ds = round(b["start_delay"] - a["start_delay"], 2)
            if ds > 0:
                rest = gap - ds
                out.append(
                    f"A saída explica {br(ds)} s dessa diferença; "
                    f"o resto, {br(max(rest, 0.0))} s, nasce no nado."
                )
            elif ds < 0:
                out.append(
                    f"A raia {b['lane']} saiu {br(-ds)} s antes: a diferença inteira nasce no nado."
                )
    rated = [lr for lr in lanes if lr["rate"]]
    if len(rated) >= 2:
        unit = f"{stroke_word.lower()}/min"
        parts = [
            f"raia {lr['lane']} com {lr['rate']:.0f} {unit}"
            for lr in sorted(rated, key=lambda lr: lr["lane"])
        ]
        out.append("Ritmo: " + ", ".join(parts) + ".")
    slow = [lr for lr in lanes if lr["start_delay"] is not None]
    if len(slow) >= 2:
        worst = max(slow, key=lambda lr: lr["start_delay"])
        best = min(slow, key=lambda lr: lr["start_delay"])
        if worst["start_delay"] - best["start_delay"] >= 0.1:
            out.append(
                f"Saída mais lenta: raia {worst['lane']} ({br(worst['start_delay'])} s do apito, "
                f"contra {br(best['start_delay'])} s da raia {best['lane']})."
            )
    return out


def build_report(tl: dict, events: list[Event], *, today: date | None = None) -> dict:
    """Dados do relatório a partir da linha do tempo e dos eventos marcados."""
    lanes = tl.get("lanes") or []
    partial = bool(tl.get("strokes_partial"))
    t0 = tl.get("t0")
    word = tl["stroke_word"]

    if lanes:
        cols = ["Saída", word, "Ritmo", "Tempo", "Dif.", "Velocidade média"]
        if partial:
            cols.remove(word)
        rows = []
        for lr in sorted(lanes, key=lambda lr: lr["lane"]):
            vals = {
                "Saída": _s(lr["start_delay"]),
                word: str(lr["n_strokes"]) if lr["n_strokes"] else DASH,
                "Ritmo": f"{lr['rate']:.0f}/min" if lr["rate"] else DASH,
                "Tempo": _s(lr["final_time"])
                if lr["final_time"] is None
                else f"{clock_text(lr['final_time'])} s",
                "Dif.": DASH
                if lr.get("behind") is None
                else ("1º" if lr["behind"] == 0 else f"+{br(lr['behind'])} s"),
                "Velocidade média": _s(lr["speed"], " m/s"),
            }
            rows.append([f"Raia {lr['lane']}", *[vals[c] for c in cols]])
        table = {"head": ["Raia", *cols], "rows": rows}
        insights = _lane_insights(lanes, word)
    else:
        table = {"head": ["Medida", "Valor"], "rows": [list(r) for r in tl.get("summary", [])]}
        insights = []

    lead = insights[0] if insights else ""
    if not lead and t0 is not None and tl.get("clock_end") is not None:
        lead = f"Tempo de {clock_text(tl['clock_end'])} s nos {tl['distance']} m."

    # momentos marcados, por raia (None = atleta da prova)
    moments: dict[str, list[tuple[str, str]]] = {}
    for e in sorted(events, key=lambda e: e.t):
        if e.type == E.STROKE:
            continue
        who = (
            "Todas as raias"
            if e.type == E.START_SIGNAL and e.lane is None
            else (
                f"Raia {e.lane}"
                if e.lane is not None
                else (f"Raia {tl['lane']}" if tl.get("lane") else "Atleta")
            )
        )
        label = MOMENT_LABEL.get(e.type, e.type.value)
        if e.type == E.MARK_PASS and e.mark_m is not None:
            label = f"Passagem pelos {e.mark_m:g} m"
        moments.setdefault(who, []).append((label, f"{br(e.t)} s"))
    strokes: dict[str, list[float]] = {}
    for e in events:
        if e.type == E.STROKE:
            who = (
                f"Raia {e.lane}"
                if e.lane is not None
                else (f"Raia {tl['lane']}" if tl.get("lane") else "Atleta")
            )
            strokes.setdefault(who, []).append(e.t)
    for who, ts in strokes.items():
        ts.sort()
        moments.setdefault(who, []).append(
            (f"{word} marcados ({len(ts)})", f"de {br(ts[0])} a {br(ts[-1])} s")
        )

    notes = []
    if partial:
        notes.append(f"{word} marcados só num trecho do vídeo: o ritmo vale, a contagem total não.")
    notes += list(tl.get("notes") or [])
    if t0 is None:
        notes.append("Sem largada marcada: os tempos não podem ser medidos.")

    return {
        "title": tl["title"] or tl["race_label"],
        "subtitle": " · ".join(
            x for x in (tl.get("athlete"), tl["race_label"], tl["pool_label"]) if x
        ),
        "date": (today or date.today()).strftime("%d/%m/%Y"),
        "lead": lead,
        "table": table,
        "insights": insights[1:] if insights else [],
        "moments": [
            {"who": k, "items": v}
            for k, v in sorted(moments.items(), key=lambda kv: (kv[0] != "Todas as raias", kv[0]))
        ],
        "notes": notes,
    }


CSS = """
:root{--navy:#0b1220;--mint:#6ee7b7;--sky:#7cc4fa;--text:#eaf2ff;--muted:#9fb0cc;--line:rgba(159,176,204,.22)}
*{box-sizing:border-box}body{margin:0;background:var(--navy);color:var(--text);font:16px/1.5 Nunito,system-ui,sans-serif}
main{max-width:860px;margin:0 auto;padding:32px 20px 56px}
.brand{font:700 18px Fredoka,Nunito,sans-serif;background:linear-gradient(90deg,var(--mint),var(--sky));-webkit-background-clip:text;background-clip:text;color:transparent}
h1{font:600 30px/1.2 Fredoka,Nunito,sans-serif;margin:6px 0 4px}h2{font:600 20px Fredoka,Nunito,sans-serif;margin:30px 0 10px;color:var(--mint)}
.sub{color:var(--muted);font-weight:700}.lead{font-size:18px;margin:18px 0 0}
table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
th{color:var(--mint);font-weight:800;font-size:13px;text-align:right;padding:8px 10px;border-bottom:1px solid var(--line)}
td{padding:9px 10px;text-align:right;border-bottom:1px solid var(--line)}th:first-child,td:first-child{text-align:left}
ul{padding-left:20px}li{margin:6px 0}.muted{color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px}
.box{border:1px solid var(--line);border-radius:14px;padding:12px 14px}.box h3{margin:0 0 6px;font-size:15px}
.box td{padding:4px 0;border:0}.print{position:fixed;top:16px;right:16px;background:var(--mint);color:var(--navy);border:0;border-radius:10px;padding:8px 14px;font-weight:800;cursor:pointer}
@media print{body{background:#fff;color:#111}.brand{color:#0a7a55;background:none}h2,th{color:#0a7a55}.muted,.sub{color:#555}.print{display:none}:root{--line:#ddd}}
@media (max-width:600px){h1{font-size:24px}td,th{padding:6px 4px;font-size:13px}}
"""


def render_html(rep: dict) -> str:
    e = html.escape

    def table(t: dict) -> str:
        head = "".join(f"<th>{e(h)}</th>" for h in t["head"])
        body = "".join("<tr>" + "".join(f"<td>{e(c)}</td>" for c in r) + "</tr>" for r in t["rows"])
        return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"

    parts = [
        "<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        f"<title>{e(rep['title'])} · Fluxi Swim</title><style>{CSS}</style></head><body>",
        "<button class='print' onclick='window.print()'>Salvar em PDF</button><main>",
        "<div class='brand'>Fluxi Swim</div>",
        f"<h1>{e(rep['title'])}</h1><div class='sub'>{e(rep['subtitle'])} · {e(rep['date'])}</div>",
    ]
    if rep["lead"]:
        parts.append(f"<p class='lead'>{e(rep['lead'])}</p>")
    parts.append("<h2>Resultados</h2>" + table(rep["table"]))
    if rep["insights"]:
        parts.append("<h2>Pontos para o técnico</h2><ul>")
        parts += [f"<li>{e(i)}</li>" for i in rep["insights"]]
        parts.append("</ul>")
    if rep["moments"]:
        parts.append("<h2>Momentos marcados</h2><div class='grid'>")
        for m in rep["moments"]:
            rows = "".join(f"<tr><td>{e(a)}</td><td>{e(b)}</td></tr>" for a, b in m["items"])
            parts.append(f"<div class='box'><h3>{e(m['who'])}</h3><table>{rows}</table></div>")
        parts.append("</div>")
    if rep["notes"]:
        parts.append("<h2>Observações</h2><ul class='muted'>")
        parts += [f"<li>{e(n)}</li>" for n in rep["notes"]]
        parts.append("</ul>")
    parts.append(
        "<p class='muted'>Instantes em segundos do vídeo. “–” = não visto ou não medido.</p>"
    )
    parts.append("</main></body></html>")
    return "".join(parts)
