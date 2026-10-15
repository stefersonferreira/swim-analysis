"""MP4 com a sobreposição Fluxi Swim gravada no vídeo.

Mesmo desenho de frontend/src/overlay (overlay.css): as medidas usam u = 1% da largura do
quadro, como os cqw do navegador. O estado de cada instante vem de state_at, o mesmo que o
navegador usa (state.ts), então o vídeo exportado mostra exatamente o que a revisão mostra.

Saída em taxa constante: cada quadro de saída usa o quadro do proxy mais próximo no tempo,
o que também mantém o áudio sincronizado em vídeos de taxa variável. No fim, alguns segundos
com o resumo da prova.
"""

from __future__ import annotations

import contextlib
import math
import subprocess
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

import av
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from swimcv.overlay.timeline import CALLOUT_S, br, clock_text, state_at

FONTS = Path(__file__).resolve().parents[3] / "brand" / "fonts"
END_HOLD_S = 4.0
PORTRAIT_SCALE = 2.2  # mesmo valor de --u no vídeo em pé (overlay.css)

NAVY = (11, 18, 32)
GLASS = (10, 16, 32, 204)
MINT = (110, 231, 183)
SKY = (124, 196, 250)
TEXT = (234, 242, 255)
MUTED = (159, 176, 204)
AMBER = (245, 165, 36)
ROSE = (251, 113, 133)
INDIGO = (165, 180, 252)
YELLOW = (252, 211, 77)

PHASE_GRAD = {
    "start": (MINT, SKY),
    "swim": (MINT, SKY),
    "underwater": (SKY, INDIGO),
    "turn": (YELLOW, AMBER),
    "finish": (AMBER, ROSE),
}


class RenderError(Exception):
    pass


@lru_cache(maxsize=256)
def font(family: str, px: int, weight: int) -> ImageFont.FreeTypeFont:
    name = "Fredoka-Variable.ttf" if family == "fredoka" else "Nunito-Variable.ttf"
    f = ImageFont.truetype(str(FONTS / name), max(6, px))
    axes = f.get_variation_axes()
    vals = []
    for a in axes:
        n = a["name"].decode() if isinstance(a["name"], bytes) else a["name"]
        vals.append(weight if n.lower() == "weight" else a["default"])
    f.set_variation_by_axes(vals)
    return f


def _gradient(w: int, h: int, a: tuple, b: tuple) -> Image.Image:
    x = np.linspace(0, 1, max(w, 1))[None, :, None]
    row = np.array(a, float)[None, None, :3] * (1 - x) + np.array(b, float)[None, None, :3] * x
    arr = np.repeat(row, max(h, 1), axis=0).astype(np.uint8)
    return Image.fromarray(arr, "RGB").convert("RGBA")


def _text_w(s: str, f: ImageFont.FreeTypeFont) -> float:
    return f.getlength(s, features=["tnum"]) if s else 0.0


class Painter:
    """Desenha os elementos da sobreposição em quadros RGBA de W x H."""

    def __init__(self, tl: dict, width: int, height: int) -> None:
        self.tl = tl
        self.W, self.H = width, height
        self.pw = width / 100.0  # 1% da largura: posições horizontais
        # unidade de tamanho: como --u na tela (overlay.css); maior no vídeo em pé
        self.u = self.pw * (PORTRAIT_SCALE if height > width else 1.0)
        self.sx = width / tl["width"]  # trajetória em pixels do proxy
        self.sy = height / tl["height"]
        self._cache: dict = {}

    # ---- peças com cache ------------------------------------------------------------------
    def px(self, v: float) -> int:
        return int(round(v * self.u))

    def f(self, family: str, size_u: float, weight: int) -> ImageFont.FreeTypeFont:
        return font(family, self.px(size_u), weight)

    def card(self, w: int, h: int, radius: int, border: tuple, glow: tuple, glow_a: float):
        """Cartão translúcido com borda e brilho; devolve (sprite, margem)."""
        key = ("card", w, h, radius, border, glow, glow_a)
        if key in self._cache:
            return self._cache[key]
        m = self.px(2.2)
        W, H = w + 2 * m, h + 2 * m
        shape = Image.new("L", (W, H), 0)
        ImageDraw.Draw(shape).rounded_rectangle((m, m, m + w, m + h), radius, fill=255)
        halo = shape.filter(ImageFilter.GaussianBlur(self.u * 0.9))
        sprite = Image.new("RGBA", (W, H), (*glow, 0))
        sprite.putalpha(halo.point(lambda v: int(v * glow_a)))
        body = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(body).rounded_rectangle(
            (m, m, m + w, m + h),
            radius,
            fill=GLASS,
            outline=border,
            width=max(1, self.px(0.13)),
        )
        # o cartão tapa o brilho por dentro (o vidro é translúcido)
        cut = Image.new("L", (W, H), 0)
        ImageDraw.Draw(cut).rounded_rectangle((m, m, m + w, m + h), radius, fill=255)
        a = np.array(sprite.getchannel("A"), np.uint8)
        a[np.array(cut) > 0] = 0
        sprite.putalpha(Image.fromarray(a))
        sprite = Image.alpha_composite(sprite, body)
        self._cache[key] = (sprite, m, shape.crop((m, m, m + w, m + h)))
        return self._cache[key]

    def put_card(self, img: Image.Image, x: int, y: int, w: int, h: int, **kw) -> None:
        sprite, m, mask = self.card(w, h, kw.pop("radius", self.px(1.3)), **kw)
        # vidro fosco: desfoca o vídeo atrás do cartão
        box = (max(0, x), max(0, y), min(self.W, x + w), min(self.H, y + h))
        if box[2] > box[0] and box[3] > box[1]:
            region = img.crop(box).filter(ImageFilter.GaussianBlur(self.u * 0.35))
            img.paste(region, box[:2], mask.crop((box[0] - x, box[1] - y, box[2] - x, box[3] - y)))
        _composite_clipped(img, sprite, x - m, y - m)

    def text(self, d: ImageDraw.ImageDraw, xy, s: str, f, fill, anchor="ls") -> None:
        d.text(xy, s, font=f, fill=fill, anchor=anchor, features=["tnum"])

    def grad_text(self, img: Image.Image, x: int, y: int, s: str, f, a, b, anchor="ls") -> None:
        x0, t, r, bt = f.getbbox(s, anchor=anchor)
        w, h = int(r - x0) + 2, int(bt - t) + 2
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).text((-x0, -t), s, font=f, fill=255, anchor=anchor)
        g = _gradient(w, h, a, b)
        g.putalpha(mask)
        _composite_clipped(img, g, int(x + x0), int(y + t))

    def pill(self, img, x: int, y: int, s: str, f, grad, fg) -> tuple[int, int]:
        tw = _text_w(s, f)
        ph, pw = self.px(1.15 * 1.3 + 0.5), int(tw + self.px(2.0))
        key = ("pill", s, pw, ph, grad, fg)
        if key not in self._cache:
            m = self.px(1.2)
            sp = Image.new("RGBA", (pw + 2 * m, ph + 2 * m), (0, 0, 0, 0))
            shape = Image.new("L", sp.size, 0)
            ImageDraw.Draw(shape).rounded_rectangle((m, m, m + pw, m + ph), ph // 2, fill=255)
            glow = Image.new("RGBA", sp.size, (*grad[0], 0))
            glow.putalpha(
                shape.filter(ImageFilter.GaussianBlur(self.u * 0.6)).point(lambda v: v * 0.45)
            )
            g = _gradient(*sp.size, grad[0], grad[1])
            g.putalpha(shape)
            sp = Image.alpha_composite(glow, g)
            d = ImageDraw.Draw(sp)
            d.text((m + pw / 2, m + ph / 2), s, font=f, fill=fg, anchor="mm")
            self._cache[key] = (sp, m)
        sp, m = self._cache[key]
        _composite_clipped(img, sp, x - m, y - m)
        return pw, ph

    def ring(self, img, cx: float, cy: float, t: float) -> None:
        r = self.px(1.7)
        pulse = 0.5 + 0.5 * math.sin(2 * math.pi * t / 1.4)
        key = ("ring", round(pulse, 1))
        if key not in self._cache:
            m = self.px(2.5)
            S = 2 * (r + m)
            line = Image.new("L", (S, S), 0)
            ImageDraw.Draw(line).ellipse(
                (m, m, m + 2 * r, m + 2 * r), outline=255, width=max(2, self.px(0.3))
            )
            glow = line.filter(ImageFilter.GaussianBlur(self.u * (0.6 + 0.6 * round(pulse, 1))))
            a = np.clip(np.array(glow, float) * 2.2 + np.array(line, float), 0, 255).astype(
                np.uint8
            )
            sp = Image.new("RGBA", (S, S), (*MINT, 0))
            sp.putalpha(Image.fromarray(a))
            self._cache[key] = (sp, r + m)
        sp, off = self._cache[key]
        _composite_clipped(img, sp, int(cx - off), int(cy - off))

    def balloon_sprite(self, c: dict, below: bool, free: bool):
        key = ("balloon", c["kind"], c["title"], c["value"], c["sub"], c["big"], below, free)
        if key in self._cache:
            return self._cache[key]
        big = c["big"]
        color = AMBER if big else SKY if c["kind"] == "split" else MINT
        ft = self.f("nunito", 1.3 if big else 0.95, 900)
        fv = self.f("fredoka", 3.6 if big else 2.6, 600)
        fs = self.f("nunito", 1.0, 700)
        title = c["title"]
        lines = [(title, ft, color, (1.3 if big else 0.95) * 1.35)]
        if c["value"]:
            lines.append((c["value"], fv, TEXT, (3.6 if big else 2.6) * 1.1))
        if c["sub"]:
            lines.append((c["sub"], fs, MUTED, 1.0 * 1.4))
        tw = max(_text_w(s, f) for s, f, _, _ in lines)
        w = int(max(self.px(9), tw + self.px(2.6)))
        h = int(sum(self.px(lh) for *_, lh in lines) + self.px(1.5))
        m = self.px(2.4)
        tail = self.px(1.1)
        W, H = w + 2 * m, h + 2 * m + tail
        top = m + (tail if below else 0)
        shape = Image.new("L", (W, H), 0)
        sd = ImageDraw.Draw(shape)
        sd.rounded_rectangle((m, top, m + w, top + h), self.px(1.4), fill=255)
        cx = m + w / 2
        tw2 = self.px(0.9)
        if not free:
            if below:
                sd.polygon([(cx - tw2, top), (cx + tw2, top), (cx, top - tail)], fill=255)
            else:
                sd.polygon(
                    [(cx - tw2, top + h), (cx + tw2, top + h), (cx, top + h + tail)], fill=255
                )
        glow = Image.new("RGBA", (W, H), (*color, 0))
        glow.putalpha(shape.filter(ImageFilter.GaussianBlur(self.u * 1.0)).point(lambda v: v * 0.5))
        body = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        bd = ImageDraw.Draw(body)
        bd.rounded_rectangle(
            (m, top, m + w, top + h),
            self.px(1.4),
            fill=GLASS,
            outline=color,
            width=max(1, self.px(0.15)),
        )
        if not free:
            if below:
                bd.polygon([(cx - tw2, top + 1), (cx + tw2, top + 1), (cx, top - tail)], fill=color)
            else:
                bd.polygon(
                    [(cx - tw2, top + h - 1), (cx + tw2, top + h - 1), (cx, top + h + tail)],
                    fill=color,
                )
        a = np.array(glow.getchannel("A"))
        inner = Image.new("L", (W, H), 0)
        ImageDraw.Draw(inner).rounded_rectangle((m, top, m + w, top + h), self.px(1.4), fill=255)
        a[np.array(inner) > 0] = 0
        glow.putalpha(Image.fromarray(a))
        sp = Image.alpha_composite(glow, body)
        d = ImageDraw.Draw(sp)
        y = top + self.px(0.7)
        for s, f, fill, lh in lines:
            y += self.px(lh)
            d.text(
                (cx, y - self.px(lh) * 0.22), s, font=f, fill=fill, anchor="ms", features=["tnum"]
            )
        anchor_y = (top - tail) if below else (top + h + tail)
        self._cache[key] = (sp, cx, anchor_y, top, h)
        return self._cache[key]

    # ---- quadro inteiro ------------------------------------------------------------------
    def draw(self, frame: Image.Image, t: float, force_summary: bool = False) -> Image.Image:
        tl = self.tl
        s = state_at(tl, t)
        img = frame.convert("RGBA")
        if force_summary:
            s["show_summary"] = True
            s["callouts"] = []
            if tl.get("t_finish") is None and not tl.get("lanes"):
                s["clock"] = None  # sem chegada: o relógio não é tempo de prova
        d = ImageDraw.Draw(img)

        # relógio e prova
        x0 = y0 = self.px(1.8)
        fw = self.f("fredoka", 1.15, 700)
        ftime = self.f("fredoka", 4.4, 600)
        frace = self.f("nunito", 1.1, 800)
        fchip = self.f("nunito", 0.95, 900)
        fpill = self.f("fredoka", 1.15, 600)
        clock = clock_text(s["clock"]) if s["clock"] is not None else "–"
        race = tl["race_label"]
        chip = f"Raia {tl['lane']}" if tl.get("lane") else ""
        chip_w = _text_w(chip, fchip) + self.px(1.4) if chip else 0
        content_w = max(
            _text_w(clock, ftime), _text_w(race, frace) + (self.px(0.6) + chip_w if chip else 0)
        )
        has_phase = s["phase_label"] and s["phase"] != "ready"
        w = int(max(self.px(15), content_w + self.px(2.8)))
        h = self.px(0.9 + 1.5 + 4.6 + 1.65 + 1.1) + (self.px(0.7 + 2.0) if has_phase else 0)
        self.put_card(img, x0, y0, w, h, border=(110, 231, 183, 90), glow=MINT, glow_a=0.22)
        d = ImageDraw.Draw(img)
        cx = x0 + self.px(1.4)
        y = y0 + self.px(0.9 + 1.2)
        self.grad_text(img, cx, y, "Fluxi Swim", fw, MINT, SKY)
        y += self.px(4.4)
        self.text(d, (cx, y), clock, ftime, TEXT)
        y += self.px(1.75)
        self.text(d, (cx, y), race, frace, MUTED)
        if chip:
            chx = cx + _text_w(race, frace) + self.px(0.6)
            ch_h = self.px(1.35)
            d.rounded_rectangle(
                (chx, y - ch_h + self.px(0.2), chx + chip_w, y + self.px(0.2)),
                ch_h // 2,
                fill=AMBER,
            )
            d.text(
                (chx + chip_w / 2, y - ch_h / 2 + self.px(0.2)),
                chip,
                font=fchip,
                fill=NAVY,
                anchor="mm",
            )
        if has_phase:
            grad = PHASE_GRAD.get(s["phase"], (MINT, SKY))
            fg = (255, 255, 255) if s["phase"] == "finish" else NAVY
            self.pill(img, cx, y + self.px(0.9), s["phase_label"], fpill, grad, fg)

        # várias raias: quadro comparativo no lugar do painel de um atleta
        if tl.get("lanes"):
            if tl["t0"] is not None and t >= tl["t0"] and not s["show_summary"]:
                self._lanes_board(img, s, y0)
        # painel da piscina
        elif s["phase"] not in (None, "ready") and tl.get("has_swim_data", True):
            swimming = s["phase"] in ("swim", "underwater", "turn")
            rows = [
                ("Piscina", str(s["length"] + 1), f"/{tl['n_lengths']}"),
                (
                    tl["stroke_word"],
                    "–" if tl.get("strokes_partial") else str(s["strokes"]),
                    "",
                ),
                ("Tempo de ciclo", br(s["tempo"]) if s["tempo"] is not None else "–", "s"),
                (
                    _speed_label(s.get("speed_span")),
                    br(s["speed"]) if swimming and s["speed"] is not None else "–",
                    "m/s",
                ),
            ]
            fl = self.f("nunito", 0.95, 800)
            fv = self.f("fredoka", 2.2, 600)
            fu = self.f("fredoka", 1.1, 500)
            pw = self.px(14)
            row_h = self.px(0.45 + 1.2 + 2.5 + 0.45)
            ph = self.px(1.2) + 4 * row_h
            px0 = self.W - self.px(1.8) - pw
            self.put_card(img, px0, y0, pw, ph, border=(110, 231, 183, 90), glow=MINT, glow_a=0.22)
            d = ImageDraw.Draw(img)
            yy = y0 + self.px(0.6)
            for i, (lab, val, unit) in enumerate(rows):
                xl = px0 + self.px(1.2)
                self.text(d, (xl, yy + self.px(0.45 + 0.95)), lab, fl, MINT)
                vy = yy + self.px(0.45 + 1.2 + 2.2)
                # braçada/ciclo acabou de acontecer: contagem e tempo de ciclo piscam em verde
                hot = s.get("pulse") and i in (1, 2) and val != "–"
                self.text(d, (xl, vy), val, fv, MINT if hot else TEXT)
                if unit:
                    self.text(d, (xl + _text_w(val, fv) + self.px(0.3), vy), unit, fu, MUTED)
                if i < 3:
                    ly = yy + row_h
                    d.line((xl, ly, px0 + pw - self.px(1.2), ly), fill=(159, 176, 204, 46), width=1)
                yy += row_h

        # nadador e balões
        head = None
        if s["head"] is not None and s["phase"] != "ready" and not force_summary:
            head = (s["head"][0] * self.sx, s["head"][1] * self.sy)
            self.ring(img, head[0], head[1], t)
        n = len(s["callouts"])
        for i, c in enumerate(s["callouts"]):
            self._balloon(img, c, head, n - 1 - i, t)

        if tl.get("track", {}).get("d") and not tl.get(
            "lanes"
        ):  # sem posições, uma barra parada em 0 só confunde
            self._progress(img, s)
        if s["show_summary"]:
            self._summary(img)
        return img.convert("RGB")

    def _balloon(self, img, c: dict, head, stack: int, t: float) -> None:
        age, left = t - c["t"], c["until"] - t
        opacity = max(0.0, min(1.0, age / 0.18, left / 0.35))
        pop = 0.85 + 0.15 * (age / 0.25) if age < 0.25 else 1.0
        free = head is None
        below = False
        if head is not None:
            x = min(84.0, max(16.0, 100 * head[0] / self.W)) * self.pw
            below = 100 * head[1] / self.H < 38
        else:
            x = 50 * self.pw
        sp, acx, ay, top, h = self.balloon_sprite(c, below, free)
        if pop != 1.0:
            sp = sp.resize(
                (max(1, int(sp.width * pop)), max(1, int(sp.height * pop))), Image.BILINEAR
            )
            acx, ay, top, h = acx * pop, ay * pop, top * pop, h * pop
        if opacity < 1.0:
            a = np.array(sp.getchannel("A"), float) * opacity
            sp = sp.copy()
            sp.putalpha(Image.fromarray(a.astype(np.uint8)))
        shift = stack * 9 * self.u
        if head is None:
            ox, oy = x - acx, 16 * self.H / 100 + shift - top
        elif below:
            ox, oy = x - acx, head[1] + 3 * self.u + shift - top
        else:
            ox, oy = x - acx, head[1] - 3 * self.u - shift - (top + h)
        _composite_clipped(img, sp, int(ox), int(oy))

    def _progress(self, img, s: dict) -> None:
        tl, u = self.tl, self.u
        d = ImageDraw.Draw(img)
        fend = self.f("fredoka", 1.1, 600)
        end_label = f"{tl['distance']} m"
        x0 = self.px(3)
        x1 = self.W - self.px(3) - _text_w(end_label, fend) - self.px(1)
        th = self.px(0.9)
        cy = self.H - self.px(3.4) - th / 2
        y0, y1 = cy - th / 2, cy + th / 2
        d.rounded_rectangle(
            (x0, y0, x1, y1), th // 2, fill=(10, 16, 32, 190), outline=(159, 176, 204, 77)
        )
        prog = 0.0 if s["race_d"] is None else min(1.0, max(0.0, s["race_d"] / tl["distance"]))
        fx = x0 + prog * (x1 - x0)
        if fx - x0 > th:
            g = _gradient(int(fx - x0), int(th), MINT, SKY)
            mask = Image.new("L", g.size, 0)
            ImageDraw.Draw(mask).rounded_rectangle(
                (0, 0, g.width - 1, g.height - 1), th // 2, fill=255
            )
            glow = Image.new("RGBA", (g.width + 4 * th, g.height + 4 * th), (*MINT, 0))
            gm = Image.new("L", glow.size, 0)
            gm.paste(mask, (2 * th, 2 * th))
            glow.putalpha(gm.filter(ImageFilter.GaussianBlur(u * 0.6)).point(lambda v: v * 0.6))
            _composite_clipped(img, glow, int(x0 - 2 * th), int(y0 - 2 * th))
            g.putalpha(mask)
            _composite_clipped(img, g, int(x0), int(y0))
        d = ImageDraw.Draw(img)
        fl = self.f("nunito", 0.95, 800)
        fb = self.f("fredoka", 0.95, 600)
        for i in range(tl["n_lengths"] - 1):
            wm = (i + 1) * tl["pool_length"]
            tx = x0 + (x1 - x0) * wm / tl["distance"]
            passed = s["race_d"] is not None and s["race_d"] >= wm - 1e-6
            d.rounded_rectangle(
                (tx - self.px(0.1), y0 - self.px(0.5), tx + self.px(0.1), y1 + self.px(0.5)),
                1,
                fill=TEXT if passed else (234, 242, 255, 140),
            )
            lab = f"{int(wm)} m"
            split = tl["lengths"][i]["split"] if i < len(tl["lengths"]) else None
            extra = f" {clock_text(split)}" if passed and split is not None else ""
            lw = _text_w(lab, fl) + _text_w(extra, fb)
            ly = y0 - self.px(0.5) - self.px(1.8) + self.px(0.95)
            self._shadow_text(img, tx - lw / 2, ly, lab, fl, MUTED)
            if extra:
                self._shadow_text(img, tx - lw / 2 + _text_w(lab, fl), ly, extra, fb, SKY)
        # ponto do nadador
        r = self.px(0.9)
        key = ("dot",)
        if key not in self._cache:
            m = self.px(1.5)
            S = 2 * (r + m)
            sp = Image.new("RGBA", (S, S), (*MINT, 0))
            sh = Image.new("L", (S, S), 0)
            ImageDraw.Draw(sh).ellipse((m, m, m + 2 * r, m + 2 * r), fill=255)
            sp.putalpha(sh.filter(ImageFilter.GaussianBlur(u * 0.6)))
            dd = ImageDraw.Draw(sp)
            dd.ellipse(
                (m, m, m + 2 * r, m + 2 * r), fill=TEXT, outline=MINT, width=max(2, self.px(0.3))
            )
            self._cache[key] = (sp, r + m)
        sp, off = self._cache[key]
        _composite_clipped(img, sp, int(fx - off), int(cy - off))
        if s["race_d"] is not None and s["phase"] not in (None, "ready"):
            fd = self.f("fredoka", 1.05, 600)
            lab = f"{br(s['race_d'], 1)} m"
            self._shadow_text(img, fx - _text_w(lab, fd) / 2, cy + self.px(2.25), lab, fd, TEXT)
        self._shadow_text(img, x1 + self.px(1), cy + self.px(0.4), end_label, fend, MUTED)

    def _shadow_text(self, img, x: float, y: float, s: str, f, fill) -> None:
        key = ("shadow", s, id(f), fill)
        if key not in self._cache:
            x0, t, r, b = f.getbbox(s, anchor="ls")
            m = self.px(0.6)
            w, h = int(r - x0) + 2 * m, int(b - t) + 2 * m
            sh = Image.new("L", (w, h), 0)
            ImageDraw.Draw(sh).text(
                (m - x0, m - t + self.px(0.1)), s, font=f, fill=255, anchor="ls"
            )
            sp = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            sp.putalpha(sh.filter(ImageFilter.GaussianBlur(self.u * 0.25)).point(lambda v: v * 0.8))
            ImageDraw.Draw(sp).text(
                (m - x0, m - t), s, font=f, fill=fill, anchor="ls", features=["tnum"]
            )
            self._cache[key] = (sp, x0 - m, t - m)
        sp, ox, oy = self._cache[key]
        _composite_clipped(img, sp, int(x + ox), int(y + oy))

    # ---- várias raias ------------------------------------------------------------------
    def _lanes_board(self, img, s: dict, y0: int) -> None:
        """Quadro ao vivo: saída, ciclos, ritmo de cada raia; tempo quando ela chega."""
        tl = self.tl
        fh = self.f("nunito", 0.85, 800)
        fv = self.f("fredoka", 1.7, 600)
        fu = self.f("nunito", 0.85, 700)
        fc = self.f("nunito", 1.0, 900)
        info = {lr["lane"]: lr for lr in tl["lanes"]}
        # (cabeçalho, largura, valor(linha) -> (texto, unidade, destaque))
        cols = [("Saída", 6.2, _lane_start)]
        if not tl.get("strokes_partial"):
            cols.append((tl["stroke_word"], 5.6, lambda r: (str(r["strokes"]), "", False)))
        cols += [("Ritmo", 6.6, _lane_rate), ("Tempo", 6.0, _lane_time)]
        pad = self.px(1.2)
        lane_w = self.px(3.0)
        pw = int(2 * pad + lane_w + sum(self.px(w) for _, w, _ in cols))
        head_h, row_h = self.px(2.0), self.px(2.7)
        rows = s["lanes"]
        ph = pad + head_h + len(rows) * row_h + self.px(0.6)
        px0 = self.W - self.px(1.8) - pw
        self.put_card(img, px0, y0, pw, ph, border=(110, 231, 183, 90), glow=MINT, glow_a=0.22)
        d = ImageDraw.Draw(img)
        x_lane = px0 + pad
        rights, x = [], x_lane + lane_w
        for _, w, _ in cols:
            x += self.px(w)
            rights.append(x)
        hy = y0 + pad + self.px(0.9)
        self.text(d, (x_lane, hy), "Raia", fh, MINT)
        for (name, _, _), rx in zip(cols, rights, strict=True):
            self.text(d, (rx, hy), name, fh, MINT, anchor="rs")
        for i, r in enumerate(rows):
            r = {**r, "_info": info[r["lane"]]}
            cy = y0 + pad + head_h + i * row_h + row_h / 2
            rr = self.px(0.95)
            d.ellipse((x_lane, cy - rr, x_lane + 2 * rr, cy + rr), fill=AMBER)
            d.text((x_lane + rr, cy), str(r["lane"]), font=fc, fill=NAVY, anchor="mm")
            base = cy + self.px(0.65)
            for (_, _, fn), rx in zip(cols, rights, strict=True):
                val, unit, hi = fn(r)
                if val == "–":
                    self.text(d, (rx, base), "–", fv, MUTED, anchor="rs")
                    continue
                uw = _text_w(unit, fu) + self.px(0.15) if unit else 0
                if unit:
                    self.text(d, (rx, base), unit, fu, MUTED, anchor="rs")
                self.text(d, (rx - uw, base), val, fv, MINT if hi else TEXT, anchor="rs")
            if i < len(rows) - 1:
                ly = cy + row_h / 2
                d.line((x_lane, ly, rights[-1], ly), fill=(159, 176, 204, 46), width=1)

    def _lanes_summary(self, img) -> None:
        """Quadro final: uma linha por raia, lado a lado."""
        tl = self.tl
        key = ("lanes_summary",)
        if key not in self._cache:
            fw = self.f("fredoka", 1.4, 700)
            ft = self.f("fredoka", 2.2, 600)
            fs = self.f("nunito", 1.0, 700)
            fh = self.f("nunito", 0.9, 800)
            fv = self.f("fredoka", 1.5, 600)
            fn = self.f("nunito", 0.8, 700)
            fc = self.f("nunito", 1.0, 900)
            lanes = tl["lanes"]
            kinds = {lr["start_delay_kind"] for lr in lanes if lr["start_delay_kind"]}
            cols = [
                (
                    "Saída",
                    lambda lr: (
                        f"{br(lr['start_delay'])} s" if lr["start_delay"] is not None else "–"
                    ),
                ),
                (tl["stroke_word"], lambda lr: str(lr["n_strokes"]) if lr["n_strokes"] else "–"),
                ("Ritmo", lambda lr: f"{lr['rate']:.0f}/min" if lr["rate"] else "–"),
                ("Tempo", lambda lr: clock_text(lr["final_time"]) if lr["final_time"] else "–"),
                ("Dif.", lambda lr: _behind_text(lr.get("behind"))),
                ("Velocidade", lambda lr: f"{br(lr['speed'])} m/s" if lr["speed"] else "–"),
            ]
            if tl.get("strokes_partial"):
                cols.pop(1)
            notes = []
            if "entry" in kinds:
                notes.append("Saída: do apito até entrar na água")
            elif "feet_off" in kinds:
                notes.append("Saída: do apito até sair do bloco")
            if any(lr["final_time"] is None for lr in lanes):
                notes.append("– : chegada fora do vídeo")
            notes.append("Ritmo: ciclos de braço por minuto")
            notes += tl.get("notes", [])
            col_w = [self.px(6.4)] * (len(cols) - 1) + [self.px(7.6)]
            lane_w = self.px(4.0)
            pad = self.px(2.2)
            w = max(pad * 2 + lane_w + sum(col_w), self.px(34))
            row_h = self.px(3.0)
            title = tl["title"] or tl["race_label"]
            h = (
                pad
                + self.px(1.4 + 2.8 + 1.8 + 2.4)
                + (len(lanes)) * row_h
                + self.px(0.8)
                + len(notes) * self.px(1.4)
                + pad
            )
            sprite, m, _ = self.card(
                w, h, self.px(2), border=(110, 231, 183, 128), glow=MINT, glow_a=0.3
            )
            sp = sprite.copy()
            ImageDraw.Draw(sp).rounded_rectangle(
                (m, m, m + w, m + h),
                self.px(2),
                fill=(11, 18, 32, 235),
                outline=(110, 231, 183, 128),
                width=max(1, self.px(0.15)),
            )
            d = ImageDraw.Draw(sp)
            x = m + pad
            y = m + pad + self.px(1.4)
            self.grad_text(sp, x, y, "Fluxi Swim", fw, MINT, SKY)
            y += self.px(2.8)
            d.text((x, y), title, font=ft, fill=TEXT, anchor="ls")
            y += self.px(1.8)
            sub = " · ".join(v for v in (tl["race_label"], tl["pool_label"]) if v)
            d.text((x, y), sub, font=fs, fill=MUTED, anchor="ls")
            y += self.px(2.4)
            d.text((x, y), "Raia", font=fh, fill=MINT, anchor="ls")
            cx = x + lane_w
            rights = []
            for (name, _), cw in zip(cols, col_w, strict=True):
                cx += cw
                rights.append(cx)
                d.text((cx, y), name, font=fh, fill=MINT, anchor="rs")
            for lr in lanes:
                cy = y + self.px(0.6) + row_h / 2
                rr = self.px(1.0)
                d.ellipse((x, cy - rr, x + 2 * rr, cy + rr), fill=AMBER)
                d.text((x + rr, cy), str(lr["lane"]), font=fc, fill=NAVY, anchor="mm")
                for (_, fn_), rx in zip(cols, rights, strict=True):
                    val = fn_(lr)
                    d.text(
                        (rx, cy + self.px(0.55)),
                        val,
                        font=fv,
                        fill=MUTED if val == "–" else TEXT,
                        anchor="rs",
                        features=["tnum"],
                    )
                y += row_h
                d.line(
                    (x, y + self.px(0.6), rights[-1], y + self.px(0.6)),
                    fill=(159, 176, 204, 51),
                    width=1,
                )
            y += self.px(0.8)
            for note in notes:
                y += self.px(1.4)
                d.text((x, y), note, font=fn, fill=MUTED, anchor="ls")
            self._cache[key] = (sp, w, h, m)
        sp, w, h, m = self._cache[key]
        _composite_clipped(img, sp, int((self.W - w) / 2 - m), int((self.H - h) / 2 - m))

    def _summary(self, img) -> None:
        tl = self.tl
        if tl.get("lanes"):
            self._lanes_summary(img)
            return
        key = ("summary",)
        if key not in self._cache:
            fw = self.f("fredoka", 1.6, 700)
            ft = self.f("fredoka", 2.6, 600)
            fs = self.f("nunito", 1.1, 700)
            fk = self.f("nunito", 1.05, 800)
            fv = self.f("fredoka", 1.6, 600)
            title = tl["title"] or tl["race_label"]
            sub = " · ".join(
                x for x in (tl.get("athlete"), tl["race_label"], tl["pool_label"]) if x
            )
            rows = tl["summary"]
            col_w = self.px(16)
            gap = self.px(2)
            w = max(
                self.px(34),
                int(max(_text_w(title, ft), _text_w(sub, fs))) + self.px(5.2),
                2 * col_w + gap + self.px(5.2),
            )
            n_rows = math.ceil(len(rows) / 2)
            row_h = self.px(2.6)
            notes = tl.get("notes", [])
            fn = self.f("nunito", 0.8, 700)
            note_h = self.px(1.4)
            w = max(w, int(max((_text_w(n, fn) for n in notes), default=0)) + self.px(5.2))
            h = (
                self.px(2 + 2.1 + 3.2 + 2.2)
                + n_rows * row_h
                + self.px(1.6)
                + (len(notes) * note_h + self.px(0.6) if notes else 0)
            )
            sprite, m, _ = self.card(
                w, h, self.px(2), border=(110, 231, 183, 128), glow=MINT, glow_a=0.3
            )
            sp = sprite.copy()
            # fundo mais opaco no resumo
            ImageDraw.Draw(sp).rounded_rectangle(
                (m, m, m + w, m + h),
                self.px(2),
                fill=(11, 18, 32, 235),
                outline=(110, 231, 183, 128),
                width=max(1, self.px(0.15)),
            )
            d = ImageDraw.Draw(sp)
            x = m + self.px(2.6)
            y = m + self.px(2 + 1.4)
            self.grad_text(sp, x, y, "Fluxi Swim", fw, MINT, SKY)
            y += self.px(3.2)
            d.text((x, y), title, font=ft, fill=TEXT, anchor="ls")
            y += self.px(1.9)
            d.text((x, y), sub, font=fs, fill=MUTED, anchor="ls")
            y += self.px(1.2)
            cw = (w - self.px(5.2) - gap) / 2
            for i, (k, v) in enumerate(rows):
                col, row = i % 2, i // 2
                rx = x + col * (cw + gap)
                ry = y + (row + 1) * row_h
                d.text((rx, ry - self.px(0.3)), k, font=fk, fill=MUTED, anchor="ls")
                d.text(
                    (rx + cw, ry - self.px(0.3)),
                    v,
                    font=fv,
                    fill=TEXT,
                    anchor="rs",
                    features=["tnum"],
                )
                d.line(
                    (rx, ry + self.px(0.1), rx + cw, ry + self.px(0.1)),
                    fill=(159, 176, 204, 51),
                    width=1,
                )
            ny = y + n_rows * row_h + self.px(0.6)
            for note in notes:
                ny += note_h
                d.text((x, ny), note, font=fn, fill=MUTED, anchor="ls")
            self._cache[key] = (sp, w, h, m)
        sp, w, h, m = self._cache[key]
        _composite_clipped(img, sp, int((self.W - w) / 2 - m), int((self.H - h) / 2 - m))


def _lane_start(r: dict):
    lr = r["_info"]
    if r.get("started") and lr["start_delay"] is not None:
        return br(lr["start_delay"]), "s", False
    return "–", "", False


def _lane_rate(r: dict):
    # pisca (verde) no instante de cada ciclo marcado
    pulse = bool(r.get("pulse"))
    return (f"{60 / r['tempo']:.0f}", "/min", pulse) if r["tempo"] else ("–", "", False)


def _lane_time(r: dict):
    ft = r["_info"]["final_time"]
    return (clock_text(ft), "", True) if r["finished"] and ft is not None else ("–", "", False)


def _behind_text(v: float | None) -> str:
    if v is None:
        return "–"
    return "1º" if v == 0 else f"+{br(v)} s"


def _composite_clipped(dst: Image.Image, src: Image.Image, x: int, y: int) -> None:
    """alpha_composite que aceita sprite parcialmente fora do quadro."""
    x0, t = max(0, x), max(0, y)
    r, b = min(dst.width, x + src.width), min(dst.height, y + src.height)
    if r <= x0 or b <= t:
        return
    crop = (
        src
        if (x0, t, r, b) == (x, y, x + src.width, y + src.height)
        else src.crop((x0 - x, t - y, r - x, b - y))
    )
    dst.alpha_composite(crop, (x0, t))


def render_mp4(
    proxy: Path,
    pts: np.ndarray,
    tl: dict,
    out: Path,
    *,
    audio: Path | None = None,
    fps: float = 30.0,
    progress: Callable[[float], None] | None = None,
) -> Path:
    """Grava out (H.264 + AAC) com a sobreposição em cada quadro e o resumo no fim."""
    if not FONTS.exists():
        raise RenderError(f"fontes não encontradas em {FONTS}")
    fps = float(round(fps)) if abs(fps - round(fps)) < 0.05 else fps
    duration = float(pts[-1]) + 1.0 / fps
    n_main = int(math.floor(duration * fps))
    # resumo no fim sempre que houver algo medido (mesmo sem a chegada no vídeo)
    has_end = tl.get("t_finish") is not None or tl.get("lanes") or tl.get("summary")
    n_end = int(END_HOLD_S * fps) if has_end else 0
    total = n_main + n_end
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".partial.mp4")

    with av.open(str(proxy)) as src:
        st = src.streams.video[0]
        st.thread_type = "AUTO"
        W, H = st.codec_context.width, st.codec_context.height
        painter = Painter(tl, W, H)
        cmd = [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{W}x{H}",
            "-r",
            f"{fps}",
            "-i",
            "-",
        ]
        if audio is not None and audio.exists():
            cmd += [
                "-i",
                str(audio),
                "-map",
                "0:v",
                "-map",
                "1:a",
                "-af",
                "apad",
                "-c:a",
                "aac",
                "-b:a",
                "160k",
                "-shortest",
            ]
        cmd += [
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(tmp),
        ]  # fmt: skip
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            frames = src.decode(st)
            cur = next(frames).to_image()
            idx = 0  # índice do quadro do proxy em cur
            last = cur
            for i in range(total):
                if i < n_main:
                    t = i / fps
                    # avança até o quadro do proxy mais próximo de t
                    while idx + 1 < len(pts) and abs(pts[idx + 1] - t) <= abs(pts[idx] - t):
                        try:
                            cur = next(frames).to_image()
                        except StopIteration:
                            break
                        idx += 1
                    img = painter.draw(cur, float(pts[idx]) if idx < len(pts) else t)
                    last = cur
                else:
                    # fim: último quadro escurecido com o resumo
                    if i == n_main:
                        dark = Image.blend(
                            last.convert("RGB"), Image.new("RGB", last.size, NAVY), 0.45
                        )
                        t_end = float(pts[-1])
                        if tl.get("t_finish") is not None:
                            t_end = max(t_end, tl["t_finish"] + CALLOUT_S * 1.6)
                    img = painter.draw(dark, t_end, force_summary=True)
                proc.stdin.write(img.tobytes())
                if progress and i % 15 == 0:
                    progress(i / total)
            proc.stdin.close()
        except BrokenPipeError:
            pass
        finally:
            # fecha a entrada antes de ler o erro: com ela aberta o ffmpeg espera mais
            # quadros e a leitura nunca termina (travava quando o desenho falhava)
            if proc.stdin and not proc.stdin.closed:
                with contextlib.suppress(BrokenPipeError):
                    proc.stdin.close()
            err = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
            code = proc.wait()
    if code != 0:
        tmp.unlink(missing_ok=True)
        raise RenderError(f"ffmpeg falhou ao gravar o vídeo: {err[-800:]}")
    tmp.replace(out)
    if progress:
        progress(1.0)
    return out


def _speed_label(span: list | None) -> str:
    """Média de um trecho entre marcas: o trecho vai no rótulo ("Vel. 5–15 m")."""
    if not span:
        return "Velocidade"
    a, b = (f"{round(d, 1):g}".replace(".", ",") for d in span)
    return f"Vel. {a}–{b} m"
