"""TradingView-style candlestick chart element (dark theme, right price axis)."""
from __future__ import annotations

import math
import random

from PIL import Image, ImageDraw

from .text import load_font

BG = (19, 23, 34)
GRID = (42, 46, 57)
AXIS_TEXT = (134, 139, 153)
UP = (38, 166, 154)
DOWN = (239, 83, 80)
WHITE = (209, 212, 220)


def generate_candles(n: int = 40, start: float = 2650.0, seed: int = 7, drift: float = 0.0,
                     vol: float = 2.2) -> list[tuple[float, float, float, float]]:
    """Seeded random-walk OHLC. Illustrative data only — label clips accordingly."""
    rng = random.Random(seed)
    out, price = [], start
    for _ in range(n):
        o = price
        c = o + rng.gauss(drift, vol)
        h = max(o, c) + abs(rng.gauss(0, vol * 0.6))
        l = min(o, c) - abs(rng.gauss(0, vol * 0.6))
        out.append((o, h, l, c))
        price = c
    return out


def _nice_step(span: float, target: int = 6) -> float:
    raw = span / target
    mag = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag:
            return m * mag
    return 10 * mag


def render_chart(candles: list[tuple[float, float, float, float]], progress: float,
                 size: tuple[int, int], *, levels: list[dict] | None = None,
                 symbol: str = "XAUUSD", timeframe: str = "M5", font_path: str | None = None,
                 t_label: str = "") -> Image.Image:
    """Render the chart with `progress` (0..1) of the candles revealed."""
    w, h = size
    n = len(candles)
    axis_w = int(w * 0.14)
    head_h = int(h * 0.09)
    foot_h = int(h * 0.06)
    plot = (0, head_h, w - axis_w, h - foot_h)  # left, top, right, bottom
    pw, ph = plot[2] - plot[0], plot[3] - plot[1]

    shown = progress * n
    full = int(shown)
    frac = shown - full
    vis = [list(c) for c in candles[:min(n, full + 1)]]
    if full < n and vis:  # last candle still forming: grow its close/high/low from open
        o, hi, lo, cl = vis[-1]
        cur = o + (cl - o) * frac
        vis[-1] = [o, max(o, cur) + (hi - max(o, cl)) * frac, min(o, cur) - (min(o, cl) - lo) * frac, cur]
    if full == 0 and frac == 0:
        vis = vis[:1]

    # y-range fixed on the whole dataset so the axis doesn't jitter while revealing
    lo_all = min(c[2] for c in candles)
    hi_all = max(c[1] for c in candles)
    for lv in levels or []:
        lo_all, hi_all = min(lo_all, lv["price"]), max(hi_all, lv["price"])
    pad = (hi_all - lo_all) * 0.12
    lo_p, hi_p = lo_all - pad, hi_all + pad

    def y_of(p: float) -> float:
        return plot[1] + (hi_p - p) / (hi_p - lo_p) * ph

    img = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(img)
    f_axis = load_font(font_path, max(18, int(h * 0.032)))
    f_head = load_font(font_path, max(20, int(h * 0.04)))

    last_y = y_of(vis[-1][3])
    tag_h = f_axis.size + 14
    # grid + price axis
    step = _nice_step(hi_p - lo_p)
    p = math.ceil(lo_p / step) * step
    while p < hi_p:
        y = y_of(p)
        d.line((plot[0], y, plot[2], y), fill=GRID, width=1)
        if abs(y - last_y) > tag_h * 0.75:  # don't print under the last-price tag
            d.text((plot[2] + 12, y), f"{p:,.2f}" if step < 1 else f"{p:,.0f}", font=f_axis,
                   fill=AXIS_TEXT, anchor="lm")
        p += step
    cols = 6
    for i in range(1, cols):
        x = plot[0] + pw * i / cols
        d.line((x, plot[1], x, plot[3]), fill=GRID, width=1)
    d.line((plot[2], plot[1], plot[2], h), fill=GRID, width=2)
    d.line((0, plot[3], w, plot[3]), fill=GRID, width=2)
    if t_label:
        d.text((8, plot[3] + foot_h / 2), t_label, font=f_axis, fill=AXIS_TEXT, anchor="lm")

    # header: symbol · timeframe · last OHLC
    d.text((14, head_h / 2), f"{symbol} · {timeframe}", font=f_head, fill=WHITE, anchor="lm")

    # candles
    slot = pw / (n + 2)
    bw = max(3, int(slot * 0.68))
    for i, (o, hi, lo, cl) in enumerate(vis):
        x = plot[0] + slot * (i + 1.5)
        col = UP if cl >= o else DOWN
        d.line((x, y_of(hi), x, y_of(lo)), fill=col, width=max(2, bw // 6))
        top, bot = sorted((y_of(o), y_of(cl)))
        if bot - top < 2:
            bot = top + 2
        d.rectangle((x - bw / 2, top, x + bw / 2, bot), fill=col)

    # levels (support / resistance) fade in once the price has passed their start candle
    for lv in levels or []:
        if shown < lv.get("from_candle", 0):
            continue
        col = tuple(int(lv.get("color", "#FFB74D").lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
        y = y_of(lv["price"])
        x0 = plot[0] + slot * (lv.get("from_candle", 0) + 1.5)
        x = x0
        while x < plot[2]:  # dashed
            d.line((x, y, min(x + 14, plot[2]), y), fill=col, width=3)
            x += 24
        label = lv.get("label", "")
        if label:
            tw = f_axis.getlength(label)
            d.rounded_rectangle((plot[2] - tw - 28, y - 34, plot[2] - 8, y - 4), radius=6, fill=col)
            d.text((plot[2] - 18 - tw / 2, y - 19), label, font=f_axis, fill=(19, 23, 34),
                   anchor="mm")

    # last-price tag on the axis
    last = vis[-1][3]
    col = UP if vis[-1][3] >= vis[-1][0] else DOWN
    y = y_of(last)
    d.line((plot[0], y, plot[2], y), fill=col, width=1)
    tag = f"{last:,.2f}"
    th = f_axis.size + 14
    d.rectangle((plot[2], y - th / 2, w, y + th / 2), fill=col)
    d.text((plot[2] + 10, y), tag, font=f_axis, fill=(255, 255, 255), anchor="lm")
    return img.convert("RGBA")
