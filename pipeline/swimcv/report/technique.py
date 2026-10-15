"""Observações técnicas por quadro-chave.

O treinador (ou a IA, como sugestão) olha um quadro de cada fase da prova e marca o que vê numa
lista de pontos técnicos comuns. Cada ponto já traz a frase para o cliente e um exercício, então
a devolutiva técnica sai com poucos cliques. Funções puras; nenhuma chamada externa aqui.
"""

from __future__ import annotations

from dataclasses import dataclass

from swimcv.contracts import Event, EventType, Stroke

E = EventType


@dataclass(frozen=True)
class Item:
    key: str
    label: str  # rótulo curto do botão
    text: str  # frase para o cliente
    drill: str = ""  # exercício sugerido
    good: bool = False  # ponto forte (não é correção)


@dataclass(frozen=True)
class Phase:
    key: str
    label: str
    hint: str  # que quadro escolher
    items: tuple[Item, ...]


_START = Phase(
    "start",
    "Saída",
    "Quadro em que os pés deixam o bloco.",
    (
        Item(
            "start_good",
            "Saída explosiva",
            "Boa saída: impulsão forte e corpo estendido.",
            good=True,
        ),
        Item(
            "start_late",
            "Reação lenta",
            "Demora para reagir ao apito.",
            "Saídas ao apito: 6 a 8 saídas curtas até os 5 m, descanso completo.",
        ),
        Item(
            "start_high",
            "Saída alta",
            "Sai muito para cima em vez de para frente; perde distância no voo.",
            "Saídas mirando um ponto 2 a 3 m à frente, sobre a água.",
        ),
        Item(
            "start_arms",
            "Braços atrasados",
            "Os braços chegam à frente tarde e o corpo não entra em linha.",
            "Saída sentado na borda com braços já em flecha, focando entrar por um só buraco.",
        ),
    ),
)
_ENTRY = Phase(
    "entry",
    "Entrada e deslize",
    "Primeiro quadro em que as mãos tocam a água, ou logo depois.",
    (
        Item("entry_good", "Flecha firme", "Boa entrada: corpo alinhado em flecha.", good=True),
        Item(
            "entry_flat",
            "Entrada de barriga",
            "Entra com o corpo plano e freia na água.",
            "Saídas sobre um macarrão para entrar por cima dele, num só ponto.",
        ),
        Item(
            "streamline_loose",
            "Flecha solta",
            "Braços e cabeça soltos no deslize; a flecha não está firme.",
            "Deslizes em flecha da parede: mãos sobrepostas, braços apertando as orelhas.",
        ),
        Item(
            "glide_long",
            "Deslize longo demais",
            "Fica parado no deslize até perder velocidade.",
            "Começar a nadar quando a velocidade do deslize cair à de nado.",
        ),
    ),
)
_FINISH = Phase(
    "finish",
    "Chegada",
    "Quadro do toque na parede.",
    (
        Item(
            "finish_good", "Chegada forte", "Boa chegada: ataca a parede sem diminuir.", good=True
        ),
        Item(
            "finish_glide",
            "Chega deslizando",
            "Desliza para a parede em vez de completar a braçada.",
            "Chegadas: últimos 5 m fortes, ajustando a braçada para tocar no fim dela.",
        ),
        Item(
            "finish_look",
            "Olha a parede",
            "Levanta a cabeça para procurar a parede e perde velocidade.",
            "Contar as braçadas depois da bandeirola para chegar sem olhar.",
        ),
    ),
)

FREE: tuple[Phase, ...] = (
    _START,
    _ENTRY,
    Phase(
        "body",
        "Posição do corpo",
        "Quadro de lado, no meio do nado.",
        (
            Item("body_good", "Corpo alinhado", "Corpo alto e alinhado na água.", good=True),
            Item(
                "hips_low",
                "Quadril baixo",
                "Quadril e pernas afundam; o corpo nada inclinado.",
                "Pernada de crawl com prancha baixa e olhar para o fundo.",
            ),
            Item(
                "head_high",
                "Cabeça alta",
                "Olha para frente; a cabeça alta afunda o quadril.",
                "Nado com olhar para o fundo da piscina, nuca alinhada à coluna.",
            ),
            Item(
                "snake",
                "Corpo serpenteia",
                "O corpo balança para os lados a cada braçada.",
                "Crawl com prancha entre as pernas, mantendo o corpo em linha.",
            ),
        ),
    ),
    Phase(
        "breath",
        "Respiração",
        "Quadro com a boca fora da água.",
        (
            Item(
                "breath_good",
                "Respiração baixa",
                "Boa respiração: rápida e com metade do rosto na água.",
                good=True,
            ),
            Item(
                "breath_lift",
                "Levanta a cabeça",
                "Levanta a cabeça para respirar em vez de girar.",
                "Pernada de lado (6 pernadas, 1 braçada), respirando só com o giro.",
            ),
            Item(
                "breath_late",
                "Respira tarde",
                "Respira atrasado e o braço da frente afunda.",
                "Crawl com um braço só, respirando para o lado do braço que puxa.",
            ),
            Item(
                "breath_one_side",
                "Respira de um lado",
                "Respira sempre do mesmo lado.",
                "Séries respirando a cada 3 braçadas.",
            ),
        ),
    ),
    Phase(
        "pull",
        "Braçada",
        "Quadro com a mão entrando na água ou no meio da puxada.",
        (
            Item("pull_good", "Braçada longa", "Braçada longa e bem apoiada.", good=True),
            Item(
                "hand_cross",
                "Mão cruza",
                "A mão entra cruzando a linha da cabeça.",
                "Crawl entrando a mão na linha do ombro (imaginar trilhos).",
            ),
            Item(
                "elbow_drop",
                "Cotovelo cai",
                "O cotovelo cai na puxada e a mão escorrega na água.",
                "Remada em cotovelo alto e crawl com punho fechado.",
            ),
            Item(
                "short_stroke",
                "Braçada curta",
                "Tira a mão da água antes de terminar a puxada.",
                "Crawl tocando a coxa com o polegar no fim de cada braçada.",
            ),
        ),
    ),
    Phase(
        "kick",
        "Pernada",
        "Quadro de lado com as pernas visíveis.",
        (
            Item("kick_good", "Pernada contínua", "Pernada contínua e estreita.", good=True),
            Item(
                "kick_knee",
                "Dobra o joelho",
                "Chuta dobrando muito o joelho (pernada de bicicleta).",
                "Pernada vertical em água funda, pernas quase retas.",
            ),
            Item(
                "kick_big",
                "Pernada larga",
                "Pernada larga demais, freando o corpo.",
                "Pernada com prancha, pés passando perto um do outro.",
            ),
            Item(
                "kick_stops",
                "Pernada para",
                "A pernada para ao respirar.",
                "Pernada de lado contando 6 pernadas em cada respiração.",
            ),
        ),
    ),
    _FINISH,
)

BREAST: tuple[Phase, ...] = (
    _START,
    _ENTRY,
    Phase(
        "pull",
        "Braçada",
        "Quadro no fim da puxada, cabeça subindo.",
        (
            Item(
                "pull_good",
                "Puxada compacta",
                "Puxada curta e rápida, cotovelos à frente.",
                good=True,
            ),
            Item(
                "pull_wide",
                "Puxada larga",
                "Puxa largo e passa da linha dos ombros.",
                "Braçada de peito com pull-buoy, mãos sem passar dos ombros.",
            ),
            Item(
                "pull_long",
                "Puxa até o quadril",
                "Leva as mãos até o quadril (puxada de borboleta).",
                "Contar 'puxa-junta' com as mãos voltando à frente na altura do peito.",
            ),
            Item(
                "recovery_slow",
                "Volta lenta",
                "Demora para levar as mãos de volta à frente.",
                "Braçada de peito rápida com pernada de golfinho leve.",
            ),
        ),
    ),
    Phase(
        "breath",
        "Respiração e cabeça",
        "Quadro com a boca fora da água.",
        (
            Item(
                "breath_good",
                "Cabeça neutra",
                "Respira sem levantar o queixo; a cabeça acompanha o corpo.",
                good=True,
            ),
            Item(
                "head_high",
                "Cabeça alta",
                "Levanta muito a cabeça ao respirar; o quadril afunda.",
                "Respirar olhando para baixo-frente, queixo próximo do peito.",
            ),
            Item(
                "head_down_late",
                "Volta tarde",
                "Demora para colocar a cabeça na água e deslizar.",
                "Peito contando 'respira-volta' a cada ciclo.",
            ),
        ),
    ),
    Phase(
        "kick",
        "Pernada",
        "Quadro com as pernas abertas ou fechando.",
        (
            Item(
                "kick_good",
                "Pernada forte",
                "Pernada que fecha completa e empurra o corpo.",
                good=True,
            ),
            Item(
                "knees_wide",
                "Joelhos abertos",
                "Abre muito os joelhos; a pernada perde força.",
                "Pernada de peito de costas, joelhos sem sair da água.",
            ),
            Item(
                "feet_not_out",
                "Pés sem virar",
                "Os pés não viram para fora; empurra com a ponta.",
                "Pernada com prancha, 'calcanhar no bumbum, pé de pato'.",
            ),
            Item(
                "scissor",
                "Tesoura",
                "Uma perna faz movimento diferente da outra (tesoura).",
                "Pernada de peito na borda, olhando os dois pés iguais.",
            ),
        ),
    ),
    Phase(
        "timing",
        "Coordenação e deslize",
        "Quadro com os braços estendidos à frente.",
        (
            Item(
                "timing_good",
                "Bom tempo",
                "Coordena bem: puxa, respira, chuta e desliza.",
                good=True,
            ),
            Item(
                "timing_overlap",
                "Braço e perna juntos",
                "Puxa e chuta ao mesmo tempo; os movimentos se anulam.",
                "2 pernadas para 1 braçada, separando os tempos.",
            ),
            Item(
                "glide_none",
                "Sem deslize",
                "Emenda um ciclo no outro sem estender o corpo.",
                "Peito contando '1' no deslize em cada ciclo.",
            ),
            Item(
                "cycle_glide_long",
                "Deslize longo",
                "Desliza tempo demais e perde velocidade em prova curta.",
                "Séries curtas forte buscando 1 a 2 ciclos a mais por piscina.",
            ),
        ),
    ),
    _FINISH,
)


def phases_for(stroke: Stroke | str) -> tuple[Phase, ...]:
    return (
        BREAST
        if str(stroke) == Stroke.BREASTSTROKE.value or stroke == Stroke.BREASTSTROKE
        else FREE
    )


def items_by_key(stroke: Stroke | str) -> dict[str, tuple[Phase, Item]]:
    return {i.key: (p, i) for p in phases_for(stroke) for i in p.items}


def catalog(stroke: Stroke | str) -> list[dict]:
    """Lista de fases e pontos para a tela e para a IA."""
    return [
        {
            "key": p.key,
            "label": p.label,
            "hint": p.hint,
            "items": [
                {"key": i.key, "label": i.label, "text": i.text, "drill": i.drill, "good": i.good}
                for i in p.items
            ],
        }
        for p in phases_for(stroke)
    ]


def suggest_keyframes(stroke: Stroke | str, events: list[Event]) -> list[dict]:
    """Quadros-chave sugeridos a partir dos eventos marcados, por atleta (raia).

    Saída = pés fora do bloco; entrada = mãos na água + 0,3 s; nado = braçadas do meio do
    trecho marcado (uma por fase de nado); chegada = toque final.
    """
    lanes = sorted({e.lane for e in events if e.lane is not None}) or [None]
    swim_phases = [p.key for p in phases_for(stroke) if p.key not in ("start", "entry", "finish")]
    out: list[dict] = []
    for lane in lanes:
        mine = sorted(
            (e for e in events if e.lane == lane and e.type != E.START_SIGNAL), key=lambda e: e.t
        )

        def first(t: EventType, mine: list[Event] = mine) -> Event | None:
            return next((e for e in mine if e.type == t), None)

        feet, entry, fin = first(E.FEET_OFF), first(E.ENTRY), first(E.FINISH_TOUCH)
        strokes = [e for e in mine if e.type == E.STROKE]
        if feet:
            out.append({"lane": lane, "phase": "start", "frame": feet.frame, "t": feet.t})
        if entry:
            out.append(
                {"lane": lane, "phase": "entry", "frame": entry.frame, "t": entry.t, "dt": 0.3}
            )
        if strokes:
            mid = strokes[len(strokes) // 2 - len(swim_phases) // 2 :] or strokes
            for k, ph in enumerate(swim_phases):
                s = mid[min(k, len(mid) - 1)]
                out.append({"lane": lane, "phase": ph, "frame": s.frame, "t": s.t})
        if fin:
            out.append({"lane": lane, "phase": "finish", "frame": fin.frame, "t": fin.t})
    return out


def clean_notes(stroke: Stroke | str, notes: list[dict]) -> list[dict]:
    """Normaliza as observações salvas: só pontos do catálogo, texto aparado, ordem por tempo."""
    known = items_by_key(stroke)
    phases = {p.key for p in phases_for(stroke)}
    out = []
    for n in notes:
        items = [k for k in n.get("items", []) if k in known]
        text = (n.get("text") or "").strip()[:600]
        mark = n.get("mark")
        out.append(
            {
                "id": str(n.get("id") or ""),
                "frame": int(n["frame"]),
                "t": float(n["t"]),
                "lane": n.get("lane"),
                "phase": n.get("phase") if n.get("phase") in phases else None,
                "items": items,
                "text": text,
                "mark": [float(mark[0]), float(mark[1])] if mark and len(mark) == 2 else None,
                "source": n.get("source") if n.get("source") in ("ai", "coach") else "coach",
                "confirmed": bool(n.get("confirmed", True)),
            }
        )
    return sorted(out, key=lambda n: (n["lane"] or 0, n["t"]))


# pontos que os números já cobrem: com a medida no rascunho, a marcação manual não repete
COVERED_BY_METRICS = {"start_late": "saída lenta"}


def notes_feedback(
    stroke: Stroke | str, notes: list[dict], multi_lane: bool, already: list[str] = ()
) -> dict:
    """Pontos fortes, correções e exercícios vindos das observações confirmadas.

    already: frases que o rascunho dos números já tem (evita dizer a mesma coisa duas vezes).
    """
    low = " ".join(already).lower()
    known = items_by_key(stroke)
    out: dict[str, list[str]] = {"strengths": [], "improve": [], "drills": []}
    for n in notes:
        if not n.get("confirmed"):
            continue
        who = f"Raia {n['lane']}: " if multi_lane and n.get("lane") is not None else ""
        for k in n["items"]:
            _, it = known[k]
            if k in COVERED_BY_METRICS and COVERED_BY_METRICS[k] in low:
                continue
            line = who + it.text
            (out["strengths"] if it.good else out["improve"]).append(line)
            if it.drill:
                out["drills"].append(who + it.drill)
    for k in out:  # sem repetições, na ordem em que apareceram
        out[k] = list(dict.fromkeys(out[k]))
    return out


ZOOM = 0.6  # largura do recorte em fração da largura do quadro
ZOOM_ASPECT = 4 / 3


def zoom_box(width: int, height: int, mx: float, my: float) -> tuple[int, int, int, int]:
    """Recorte 4:3 em volta do ponto marcado, dentro do quadro: (x0, y0, w, h)."""
    w = int(min(width, ZOOM * width if width < height else ZOOM * height * ZOOM_ASPECT))
    h = int(min(height, w / ZOOM_ASPECT))
    x0 = int(min(max(mx - w / 2, 0), width - w))
    y0 = int(min(max(my - h / 2, 0), height - h))
    return x0, y0, w, h
