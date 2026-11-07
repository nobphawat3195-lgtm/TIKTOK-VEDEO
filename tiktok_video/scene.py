"""Per-scene layer pre-rendering and per-frame composition."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

import numpy as np
from PIL import Image, ImageColor, ImageDraw, ImageOps

from .storyboard import Element, Scene, Storyboard
from .text import load_font, wrap

ANIM_IN = 0.35  # seconds for entrance animations
MARGIN_X = 0.09  # fraction of width kept clear on each side (TikTok UI overlays)


def rgba(color: str | tuple) -> tuple[int, int, int, int]:
    if isinstance(color, tuple):
        return color if len(color) == 4 else (*color, 255)
    c = ImageColor.getrgb(color)
    return c if len(c) == 4 else (*c, 255)


def _ease_out(p: float) -> float:
    return 1 - (1 - p) ** 3


def _ease_out_back(p: float) -> float:
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (p - 1) ** 3 + c1 * (p - 1) ** 2


# ---------------------------------------------------------------- background
def render_background(bg: dict, w: int, h: int, sb: Storyboard) -> tuple[Image.Image, bool]:
    """Return (image, ken_burns). Ken Burns images are rendered oversized."""
    zoom = bool(bg.get("zoom", "image" in bg))
    bw, bh = (int(w * 1.1), int(h * 1.1)) if zoom else (w, h)
    if "image" in bg:
        img = Image.open(sb.resolve(bg["image"])).convert("RGB")
        img = ImageOps.fit(img, (bw, bh), Image.LANCZOS)
        dim = float(bg.get("dim", 0.35))
        if dim > 0:
            img = Image.blend(img, Image.new("RGB", img.size, (0, 0, 0)), dim)
    elif "gradient" in bg:
        top, bottom = (np.array(rgba(c)[:3], dtype=np.float32) for c in bg["gradient"][:2])
        t = np.linspace(0, 1, bh, dtype=np.float32)[:, None, None]
        arr = top * (1 - t) + bottom * t
        img = Image.fromarray(np.broadcast_to(arr, (bh, bw, 3)).astype(np.uint8), "RGB")
    else:
        img = Image.new("RGB", (bw, bh), rgba(bg.get("color", "#000000"))[:3])
    return img, zoom


# ------------------------------------------------------------------ elements
def render_text_block(text: str, props: dict, sb: Storyboard) -> Image.Image:
    w = sb.width
    size = int(props.get("size", 64))
    font = load_font(sb.resolve(props.get("font")) or sb.resolve(sb.font), size)
    max_w = int(props.get("max_width", w * (1 - 2 * MARGIN_X)))
    lines = wrap(text, font, max_w)
    lh = int(size * float(props.get("line_height", 1.4)))
    stroke = int(props.get("stroke", max(2, size // 14)))
    pad = int(props.get("padding", size * 0.35)) if props.get("box") else stroke + 4
    content_w = max((font.getlength(ln) for ln in lines), default=0)
    cw = int(content_w + 2 * pad + 2 * stroke)
    ch = int(lh * len(lines) + 2 * pad)
    img = Image.new("RGBA", (max(cw, 1), max(ch, 1)), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if props.get("box"):
        d.rounded_rectangle((0, 0, cw - 1, ch - 1), radius=int(size * 0.35), fill=rgba(props["box"]))
    align = props.get("align", "center")
    for i, ln in enumerate(lines):
        y = pad + i * lh + lh / 2
        if align == "left":
            x, anchor = pad + stroke, "lm"
        else:
            x, anchor = cw / 2, "mm"
        d.text((x, y), ln, font=font, fill=rgba(props.get("color", "#FFFFFF")), anchor=anchor,
               stroke_width=stroke, stroke_fill=rgba(props.get("stroke_color", "#000000")))
    return img


def render_image(props: dict, sb: Storyboard) -> Image.Image:
    img = Image.open(sb.resolve(props["path"])).convert("RGBA")
    tw = int(sb.width * float(props.get("width", 0.82)))
    img = img.resize((tw, max(1, int(img.height * tw / img.width))), Image.LANCZOS)
    radius = int(props.get("radius", 28))
    if radius:
        mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, *img.size), radius=radius, fill=255)
        img.putalpha(Image.fromarray(np.minimum(np.array(img.getchannel("A")), np.array(mask))))
    return img


def format_counter(value: float, props: dict) -> str:
    decimals = int(props.get("decimals", 0))
    body = f"{abs(value):,.{decimals}f}"
    sign = "-" if value < 0 else ("+" if props.get("signed") and value > 0 else "")
    return f"{sign}{props.get('prefix', '')}{body}{props.get('suffix', '')}"


@dataclass
class Layer:
    el: Element
    static: Image.Image | None
    dynamic: Callable[[float], Image.Image] | None = None

    def image_at(self, t: float) -> Image.Image:
        return self.static if self.static is not None else self.dynamic(t)  # type: ignore[misc]


def build_layer(el: Element, sb: Storyboard) -> Layer:
    if el.type == "text":
        return Layer(el, render_text_block(str(el.get("text", "")), el.props, sb))
    if el.type == "image":
        return Layer(el, render_image(el.props, sb))
    if el.type == "counter":
        start, end = float(el.get("from", 0)), float(el.get("to", 0))
        dur, delay = float(el.get("count_duration", 1.2)), float(el.get("delay", 0))
        cache: dict[str, Image.Image] = {}

        def dyn(t: float) -> Image.Image:
            p = _ease_out(min(1.0, max(0.0, (t - delay) / dur)))
            txt = format_counter(start + (end - start) * p, el.props)
            if txt not in cache:
                cache[txt] = render_text_block(txt, el.props, sb)
            return cache[txt]

        return Layer(el, None, dyn)
    raise ValueError(f"ไม่รู้จัก element type: {el.type}")


def element_state(el: Element, t: float) -> tuple[float, float, float]:
    """Return (alpha, dy_px, scale) for an element at scene-local time t."""
    delay = float(el.get("delay", 0))
    anim = el.get("anim", "fade")
    if t < delay:
        return 0.0, 0.0, 1.0
    p = min(1.0, (t - delay) / float(el.get("anim_duration", ANIM_IN)))
    if anim == "none":
        return 1.0, 0.0, 1.0
    if anim == "slide_up":
        e = _ease_out(p)
        return e, (1 - e) * 80, 1.0
    if anim == "pop":
        return min(1.0, p * 2), 0.0, 0.6 + 0.4 * _ease_out_back(p)
    return _ease_out(p), 0.0, 1.0  # fade


# --------------------------------------------------------------------- scene
class SceneRenderer:
    def __init__(self, scene: Scene, sb: Storyboard, duration: float):
        self.scene, self.sb, self.duration = scene, sb, duration
        self.bg, self.zoom = render_background(scene.background, sb.width, sb.height, sb)
        self.layers = [build_layer(el, sb) for el in scene.elements]

    def _background_at(self, t: float) -> Image.Image:
        w, h = self.sb.width, self.sb.height
        if not self.zoom:
            return self.bg.copy()
        p = min(1.0, t / max(self.duration, 1e-6))
        s = 1.0 + 0.09 * (1 - p)  # slow zoom-in (scale crop window down)
        cw, ch = w * s, h * s
        cx, cy = self.bg.width / 2, self.bg.height / 2
        box = (cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2)
        return self.bg.resize((w, h), Image.BILINEAR, box=box)

    def frame(self, t: float) -> Image.Image:
        w, h = self.sb.width, self.sb.height
        frame = self._background_at(t)
        for layer in self.layers:
            alpha, dy, scale = element_state(layer.el, t)
            if alpha <= 0.01:
                continue
            img = layer.image_at(t)
            if abs(scale - 1) > 1e-3:
                img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))),
                                 Image.BILINEAR)
            if alpha < 0.999:
                a = np.array(img.getchannel("A"), dtype=np.float32) * alpha
                img = img.copy()
                img.putalpha(Image.fromarray(a.astype(np.uint8)))
            cx = float(layer.el.get("x", 0.5)) * w
            cy = float(layer.el.get("y", 0.5)) * h + dy
            frame.paste(img, (int(cx - img.width / 2), int(cy - img.height / 2)), img)
        return frame


def draw_progress(frame: Image.Image, progress: float, color: str) -> None:
    d = ImageDraw.Draw(frame)
    bar_h = max(6, frame.height // 240)
    d.rectangle((0, 0, frame.width, bar_h), fill=(70, 70, 70))
    d.rectangle((0, 0, int(frame.width * progress), bar_h), fill=rgba(color)[:3])


def frames_for(duration: float, fps: int) -> int:
    return max(1, int(math.ceil(duration * fps)))
