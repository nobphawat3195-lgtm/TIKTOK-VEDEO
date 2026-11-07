"""CLI: python -m tiktok_video {render,still,recap} ..."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import recap, renderer, storyboard


def _cmd_render(a: argparse.Namespace) -> None:
    sb = storyboard.load(a.storyboard)
    out = renderer.render(sb, a.output, crf=a.crf, preset=a.preset)
    print(out)


def _cmd_still(a: argparse.Namespace) -> None:
    sb = storyboard.load(a.storyboard)
    print(renderer.render_still(sb, a.scene - 1, a.t, a.output))


def _cmd_recap(a: argparse.Namespace) -> None:
    deals = recap.load_deals(a.csv, symbol=a.symbol)
    stats = recap.compute_stats(deals)
    out = Path(a.output)
    sb = recap.build_storyboard(stats, out.parent / f"{out.stem}_assets", title=a.title,
                                currency=a.currency, handle=a.handle, bgm=a.bgm, font=a.font)
    print(f"trades={stats.trades} net={stats.net:.2f} winrate={stats.win_rate:.1f}% "
          f"pf={stats.profit_factor:.2f} maxdd={stats.max_dd:.2f}", file=sys.stderr)
    print(renderer.render(sb, out, crf=a.crf, preset=a.preset))


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="tiktok_video", description="สร้างคลิป TikTok 9:16")
    sub = p.add_subparsers(dest="cmd", required=True)

    def enc(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--crf", type=int, default=20)
        sp.add_argument("--preset", default="medium")

    r = sub.add_parser("render", help="render storyboard (.yaml/.json) เป็น mp4")
    r.add_argument("storyboard")
    r.add_argument("-o", "--output", default="out/video.mp4")
    enc(r)
    r.set_defaults(fn=_cmd_render)

    s = sub.add_parser("still", help="render เฟรมเดียวเป็น PNG เพื่อพรีวิว")
    s.add_argument("storyboard")
    s.add_argument("--scene", type=int, default=1, help="ลำดับ scene (เริ่มที่ 1)")
    s.add_argument("--t", type=float, default=1.5, help="วินาทีภายใน scene")
    s.add_argument("-o", "--output", default="out/still.png")
    s.set_defaults(fn=_cmd_still)

    c = sub.add_parser("recap", help="สร้างคลิปสรุปผลเทรดจาก CSV ที่ export จาก MT5")
    c.add_argument("csv")
    c.add_argument("-o", "--output", default="out/recap.mp4")
    c.add_argument("--symbol", default=None, help="กรองเฉพาะ symbol เช่น XAUUSD")
    c.add_argument("--title", default=None)
    c.add_argument("--currency", default="$")
    c.add_argument("--handle", default=None, help="เช่น @mygoldea")
    c.add_argument("--bgm", default=None, help="ไฟล์เพลงประกอบ")
    c.add_argument("--font", default=None)
    enc(c)
    c.set_defaults(fn=_cmd_recap)

    a = p.parse_args(argv)
    Path(getattr(a, "output", "out/x")).parent.mkdir(parents=True, exist_ok=True)
    a.fn(a)


if __name__ == "__main__":
    main()
