"""Trade-recap template: MT5 deal history CSV -> stats -> storyboard."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from .scene import rgba
from .storyboard import Storyboard, from_dict
from .text import load_font

GOLD = "#FFD54A"
GREEN = "#2EE59D"
RED = "#FF5370"


@dataclass
class Deal:
    time: datetime
    symbol: str
    type: str
    volume: float
    profit: float  # net: profit + commission + swap


@dataclass
class Stats:
    trades: int
    wins: int
    losses: int
    net: float
    gross_win: float
    gross_loss: float
    max_dd: float
    best: float
    worst: float
    start: datetime
    end: datetime
    symbols: list[str]
    equity: list[float]

    @property
    def win_rate(self) -> float:
        return 100.0 * self.wins / self.trades if self.trades else 0.0

    @property
    def profit_factor(self) -> float:
        return self.gross_win / abs(self.gross_loss) if self.gross_loss else float("inf")


def _f(row: dict, *keys: str) -> float:
    for k in keys:
        v = row.get(k)
        if v not in (None, ""):
            return float(str(v).replace(" ", "").replace(",", ""))
    return 0.0


def _parse_time(s: str) -> datetime:
    for fmt in ("%Y.%m.%d %H:%M:%S", "%Y.%m.%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s.strip(), fmt)
        except ValueError:
            continue
    raise ValueError(f"รูปแบบเวลาไม่รองรับ: {s!r}")


def load_deals(path: str | Path, symbol: str | None = None) -> list[Deal]:
    """Read closing deals. Columns (case-insensitive): time, symbol, type, volume,
    profit, [commission], [swap], [entry]. Rows with entry=in are skipped."""
    with open(path, newline="", encoding="utf-8-sig") as fh:
        sample = fh.read(4096)
        fh.seek(0)
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        reader = csv.DictReader(fh, dialect=dialect)
        deals = []
        for raw in reader:
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
            if row.get("entry", "out").lower() == "in":
                continue
            if row.get("type", "").lower() in {"balance", "credit", "deposit", "withdrawal"}:
                continue
            sym = row.get("symbol", "")
            if symbol and sym.upper() != symbol.upper():
                continue
            deals.append(Deal(
                time=_parse_time(row["time"]),
                symbol=sym,
                type=row.get("type", ""),
                volume=_f(row, "volume"),
                profit=_f(row, "profit") + _f(row, "commission") + _f(row, "swap"),
            ))
    deals.sort(key=lambda d: d.time)
    return deals


def compute_stats(deals: list[Deal]) -> Stats:
    if not deals:
        raise ValueError("ไม่มี deal ปิดในไฟล์")
    pnl = np.array([d.profit for d in deals])
    equity = np.concatenate([[0.0], np.cumsum(pnl)])
    dd = float(np.max(np.maximum.accumulate(equity) - equity))
    return Stats(
        trades=len(deals),
        wins=int((pnl > 0).sum()),
        losses=int((pnl < 0).sum()),
        net=float(pnl.sum()),
        gross_win=float(pnl[pnl > 0].sum()),
        gross_loss=float(pnl[pnl < 0].sum()),
        max_dd=dd,
        best=float(pnl.max()),
        worst=float(pnl.min()),
        start=deals[0].time,
        end=deals[-1].time,
        symbols=sorted({d.symbol for d in deals}),
        equity=equity.tolist(),
    )


def draw_equity_chart(equity: list[float], out: str | Path, size=(900, 620),
                      font_path: str | None = None) -> Path:
    w, h = size
    img = Image.new("RGBA", size, (16, 20, 32, 235))
    d = ImageDraw.Draw(img)
    pad_l, pad_r, pad_t, pad_b = 40, 40, 90, 50
    font = load_font(font_path, 40)
    d.text((pad_l, 26), "Equity Curve", font=font, fill=rgba(GOLD))

    eq = np.array(equity, dtype=float)
    lo, hi = float(eq.min()), float(eq.max())
    if hi - lo < 1e-9:
        hi, lo = hi + 1, lo - 1
    span = hi - lo
    lo, hi = lo - span * 0.08, hi + span * 0.08
    xs = np.linspace(pad_l, w - pad_r, len(eq))
    ys = pad_t + (hi - eq) / (hi - lo) * (h - pad_t - pad_b)
    zero_y = pad_t + hi / (hi - lo) * (h - pad_t - pad_b)

    color = rgba(GREEN if eq[-1] >= 0 else RED)
    ov = Image.new("RGBA", size, (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    for i in range(5):  # grid
        gy = pad_t + i * (h - pad_t - pad_b) / 4
        od.line((pad_l, gy, w - pad_r, gy), fill=(255, 255, 255, 25), width=1)
    if pad_t <= zero_y <= h - pad_b:
        od.line((pad_l, zero_y, w - pad_r, zero_y), fill=(255, 255, 255, 90), width=2)
    base_y = min(max(zero_y, pad_t), h - pad_b)
    od.polygon([(xs[0], base_y), *zip(xs.tolist(), ys.tolist()), (xs[-1], base_y)],
               fill=(*color[:3], 70))
    img.alpha_composite(ov)
    d = ImageDraw.Draw(img)
    d.line(list(zip(xs.tolist(), ys.tolist())), fill=color, width=6, joint="curve")
    d.ellipse((xs[-1] - 10, ys[-1] - 10, xs[-1] + 10, ys[-1] + 10), fill=color)
    img.save(out)
    return Path(out)


def _money(v: float, cur: str) -> str:
    sign = "+" if v > 0 else ("-" if v < 0 else "")
    return f"{sign}{cur}{abs(v):,.2f}"


def build_storyboard(stats: Stats, workdir: Path, *, title: str | None = None,
                     currency: str = "$", handle: str | None = None, bgm: str | None = None,
                     font: str | None = None) -> Storyboard:
    workdir.mkdir(parents=True, exist_ok=True)
    chart = draw_equity_chart(stats.equity, workdir / "equity.png", font_path=font)
    sym = ", ".join(stats.symbols) or "XAUUSD"
    if stats.start.date() == stats.end.date():
        period = stats.start.strftime("%d/%m/%Y")
    else:
        period = f"{stats.start:%d/%m} – {stats.end:%d/%m/%Y}"
    up = stats.net >= 0
    pf = "MAX" if stats.profit_factor == float("inf") else f"{stats.profit_factor:.2f}"
    stats_text = (
        f"Win rate  {stats.win_rate:.1f}%\n"
        f"Trades  {stats.trades}  ({stats.wins}W / {stats.losses}L)\n"
        f"Profit Factor  {pf}\n"
        f"Max DD  {currency}{stats.max_dd:,.2f}"
    )
    bg_dark = {"gradient": ["#0B0F1A", "#1C2440"]}
    bg_pnl = {"gradient": ["#0B1A12", "#12402A"]} if up else {"gradient": ["#1A0B0F", "#401220"]}
    data = {
        "video": {"fps": 30, "font": font, "bgm": bgm, "progress_bar": GOLD},
        "scenes": [
            {"duration": 2.6, "background": bg_dark,
             "title": title or f"ผลเทรด {sym}", "text": period,
             "caption": "EA Scalping M1/M5"},
            {"duration": 3.4, "background": bg_pnl,
             "elements": [
                 {"type": "text", "text": "กำไรสุทธิ" if up else "ขาดทุนสุทธิ", "size": 72,
                  "y": 0.32, "anim": "slide_up"},
                 {"type": "counter", "from": 0, "to": round(stats.net, 2), "decimals": 2,
                  "prefix": currency, "signed": True, "size": 150, "y": 0.45,
                  "color": GREEN if up else RED, "anim": "pop", "delay": 0.2,
                  "count_duration": 1.6},
                 {"type": "text", "text": f"Best {_money(stats.best, currency)}   "
                                          f"Worst {_money(stats.worst, currency)}",
                  "size": 46, "y": 0.58, "color": "#CFD8DC", "anim": "fade", "delay": 1.0},
             ]},
            {"duration": 3.6, "background": bg_dark,
             "elements": [
                 {"type": "text", "text": "สถิติ", "size": 88, "y": 0.24, "color": GOLD,
                  "anim": "slide_up"},
                 {"type": "text", "text": stats_text, "size": 62, "y": 0.45, "anim": "fade",
                  "delay": 0.3, "line_height": 1.6, "box": "#FFFFFF14"},
             ]},
            {"duration": 3.6, "background": bg_dark,
             "elements": [
                 {"type": "image", "path": str(chart), "width": 0.84, "y": 0.44, "anim": "pop"},
             ]},
            {"duration": 2.8, "background": bg_dark,
             "title": "ติดตามไว้ ดูผลทุกวัน",
             "text": handle or "",
             "elements": [
                 {"type": "text", "text": "ผลการเทรดในอดีตไม่ได้รับประกันผลในอนาคต",
                  "size": 34, "y": 0.62, "color": "#90A4AE", "anim": "fade", "delay": 0.4,
                  "stroke": 0},
             ]},
        ],
    }
    if not handle:
        data["scenes"][-1].pop("text")
    return from_dict(data, base_dir=Path.cwd())
