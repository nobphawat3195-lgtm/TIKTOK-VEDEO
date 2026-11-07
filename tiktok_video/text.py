"""Font loading and Thai-aware line wrapping."""
from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

# Thai combining marks (above/below vowels, tone marks) must stay attached to
# their base consonant, otherwise wrapping can split a glyph cluster.
_THAI_COMBINING = {0x0E31, *range(0x0E34, 0x0E3B), *range(0x0E47, 0x0E4F)}
# Following vowels / repetition mark that may not start a line (ะ า ำ ๅ ๆ).
_THAI_NO_LINE_START = _THAI_COMBINING | {0x0E30, 0x0E32, 0x0E33, 0x0E45, 0x0E46}
# Leading vowels that may not end a line (เ แ โ ใ ไ).
_THAI_LEADING = set(range(0x0E40, 0x0E45))
_THAI_RANGE = re.compile(r"[\u0E00-\u0E7F]")

_FONT_CANDIDATES = [
    "assets/fonts/Kanit-Bold.ttf",
    "assets/fonts/Prompt-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansThai-Bold.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansThai-Bold.ttf",
    "/usr/share/fonts/opentype/tlwg/Loma-Bold.otf",
    "/usr/share/fonts/truetype/tlwg/Loma-Bold.ttf",
    "/usr/share/fonts/truetype/tlwg/Garuda-Bold.ttf",
    "/Library/Fonts/Thonburi.ttc",
    "C:/Windows/Fonts/tahomabd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def find_default_font() -> str:
    env = os.environ.get("TIKTOK_VIDEO_FONT")
    if env and Path(env).exists():
        return env
    for cand in _FONT_CANDIDATES:
        if Path(cand).exists():
            return cand
    raise FileNotFoundError(
        "ไม่พบฟอนต์ภาษาไทย: ตั้ง TIKTOK_VIDEO_FONT หรือใส่ 'font:' ใน storyboard"
    )


@lru_cache(maxsize=64)
def load_font(path: str | None, size: int) -> ImageFont.FreeTypeFont:
    path = path or find_default_font()
    layout = ImageFont.Layout.RAQM if ImageFont.core.HAVE_RAQM else ImageFont.Layout.BASIC
    return ImageFont.truetype(path, size, layout_engine=layout)


def _clusters(s: str) -> list[str]:
    out: list[str] = []
    for ch in s:
        if out and (ord(ch) in _THAI_NO_LINE_START or ord(out[-1][-1]) in _THAI_LEADING):
            out[-1] += ch
        else:
            out.append(ch)
    return out


def tokenize(s: str) -> list[str]:
    """Split into breakable tokens.

    Uses pythainlp word segmentation when installed (best quality);
    otherwise Latin words stay whole and Thai breaks on glyph clusters.
    """
    if _THAI_RANGE.search(s):
        try:
            from pythainlp.tokenize import word_tokenize  # type: ignore

            return word_tokenize(s, engine="newmm", keep_whitespace=True)
        except Exception:
            pass
    tokens: list[str] = []
    for part in re.findall(r"\s+|[^\s\u0E00-\u0E7F]+|[\u0E00-\u0E7F]+", s):
        if _THAI_RANGE.match(part):
            tokens.extend(_clusters(part))
        else:
            tokens.append(part)
    return tokens


def wrap(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines: list[str] = []
    for para in text.split("\n"):
        line = ""
        for tok in tokenize(para):
            cand = line + tok
            if line and font.getlength(cand) > max_width:
                lines.append(line.rstrip())
                line = tok.lstrip()
            else:
                line = cand
        lines.append(line.rstrip())
    return lines
