"""Sugestão de observações técnicas por IA com visão (API da Anthropic).

Manda o quadro-chave e a lista de pontos daquela fase; a IA só pode escolher pontos da lista
e deve dizer "não dá para ver" quando o quadro não mostra. O resultado é sempre sugestão: o
treinador confirma ou descarta. Sem chave configurada, nada é chamado.
"""

from __future__ import annotations

import base64
import json
import urllib.request
from collections.abc import Callable

from swimcv.report.technique import phases_for

API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-sonnet-5-5"

Post = Callable[[str, dict, dict], dict]


class AIError(RuntimeError):
    pass


def _post(url: str, headers: dict, body: dict) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except Exception as exc:  # rede, chave errada, limite
        raise AIError(f"a IA não respondeu: {exc}") from exc


def build_prompt(stroke: str, phase_key: str, lane: int | None) -> tuple[str, list[str]]:
    phase = next(p for p in phases_for(stroke) if p.key == phase_key)
    options = "\n".join(f"- {i.key}: {i.label}. {i.text}" for i in phase.items)
    who = f"o nadador da raia {lane}" if lane else "o nadador em foco"
    estilo = "peito" if str(stroke) == "breaststroke" else "crawl (nado livre)"
    prompt = (
        f"Você ajuda um treinador de natação a revisar um vídeo de {estilo}. Esta imagem é um "
        f"quadro da fase '{phase.label}' ({phase.hint}). Observe {who}.\n\n"
        f"Pontos possíveis para esta fase:\n{options}\n\n"
        "Escolha só os pontos que você consegue VER com clareza neste quadro. Se o quadro não "
        "mostrar o suficiente (atleta pequeno, embaixo da água, borrado, de costas para a "
        "câmera), não escolha nada. Não invente.\n"
        'Responda só com JSON: {"items": ["chave", ...], "text": "uma frase curta em português '
        'para o atleta, ou vazio", "visible": true|false, "confidence": 0.0-1.0}'
    )
    return prompt, [i.key for i in phase.items]


def parse_answer(raw: str, allowed: list[str]) -> dict:
    s = raw.strip()
    if "{" in s:
        s = s[s.index("{") : s.rindex("}") + 1]
    try:
        d = json.loads(s)
    except ValueError as exc:
        raise AIError("resposta da IA fora do formato") from exc
    items = [k for k in d.get("items", []) if k in allowed]
    conf = float(d.get("confidence", 0.0) or 0.0)
    visible = bool(d.get("visible", True))
    if not visible:
        items = []
    return {
        "items": items,
        "text": str(d.get("text") or "").strip()[:300],
        "visible": visible,
        "confidence": max(0.0, min(1.0, conf)),
    }


def suggest(
    jpeg: bytes,
    stroke: str,
    phase_key: str,
    lane: int | None,
    *,
    api_key: str,
    model: str = DEFAULT_MODEL,
    post: Post = _post,
) -> dict:
    if not api_key:
        raise AIError("configure ANTHROPIC_API_KEY no .env para usar as sugestões por IA")
    prompt, allowed = build_prompt(stroke, phase_key, lane)
    body = {
        "model": model,
        "max_tokens": 400,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": base64.b64encode(jpeg).decode(),
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    resp = post(API_URL, headers, body)
    text = "".join(b.get("text", "") for b in resp.get("content", []) if b.get("type") == "text")
    return parse_answer(text, allowed)
