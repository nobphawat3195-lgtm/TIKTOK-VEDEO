import subprocess
from pathlib import Path

import pytest

from tiktok_video import from_dict, render, render_still
from tiktok_video.recap import build_storyboard, compute_stats, load_deals
from tiktok_video.renderer import plan_durations, probe_duration
from tiktok_video.scene import format_counter
from tiktok_video.text import load_font, tokenize, wrap

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "examples" / "deals_sample.csv"


def _tone(path: Path, seconds: float, freq: int = 440) -> Path:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    f"sine=frequency={freq}:duration={seconds}", str(path)], check=True)
    return path


def _probe_streams(path: Path) -> str:
    return subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
                           "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout


def test_thai_tokenize_keeps_combining_marks_attached():
    from tiktok_video.text import _THAI_LEADING, _THAI_NO_LINE_START, _clusters

    s = "น้ำใจเทรดทองคำไม่ต้องรีบ"
    toks = _clusters(s)
    assert "".join(toks) == s == "".join(tokenize(s))
    assert all(ord(t[0]) not in _THAI_NO_LINE_START for t in toks)
    assert all(ord(t[-1]) not in _THAI_LEADING for t in toks)


def test_wrap_respects_width():
    font = load_font(None, 64)
    lines = wrap("กฎการเทรดทองคำแบบสแกลป์ปิ้งบนกราฟหนึ่งนาทีที่ต้องรู้ก่อนเปิด EA", font, 500)
    assert len(lines) > 1
    assert all(font.getlength(ln) <= 500 for ln in lines)


def test_counter_format():
    assert format_counter(1234.5, {"decimals": 2, "prefix": "$", "signed": True}) == "+$1,234.50"
    assert format_counter(-12, {"prefix": "$"}) == "-$12"


def test_recap_stats():
    stats = compute_stats(load_deals(SAMPLE, symbol="XAUUSD"))
    assert stats.trades == 28
    assert stats.wins + stats.losses <= stats.trades
    assert stats.net == pytest.approx(stats.gross_win + stats.gross_loss)
    assert stats.max_dd >= 0
    assert len(stats.equity) == stats.trades + 1


def test_load_deals_skips_entry_in_and_semicolon(tmp_path):
    p = tmp_path / "d.csv"
    p.write_text("Time;Symbol;Type;Entry;Volume;Profit;Commission\n"
                 "2026.11.06 09:00:00;XAUUSD;buy;in;0.10;0;-0.7\n"
                 "2026.11.06 09:05:00;XAUUSD;buy;out;0.10;12.5;-0.7\n"
                 "2026.11.06 09:06:00;EURUSD;buy;out;0.10;3;0\n")
    deals = load_deals(p, symbol="XAUUSD")
    assert len(deals) == 1 and deals[0].profit == pytest.approx(11.8)


def test_voice_sets_scene_duration(tmp_path):
    voice = _tone(tmp_path / "v.wav", 1.2)
    sb = from_dict({"scenes": [{"title": "x", "voice": str(voice)}]})
    assert plan_durations(sb)[0] == pytest.approx(1.6, abs=0.05)


def test_render_with_voice_and_bgm(tmp_path):
    voice = _tone(tmp_path / "v.wav", 0.8)
    bgm = _tone(tmp_path / "bgm.wav", 0.5, 220)  # shorter than video -> must loop
    sb = from_dict({
        "video": {"width": 270, "height": 480, "fps": 15, "bgm": str(bgm)},
        "scenes": [
            {"title": "ทดสอบ", "caption": "คำบรรยาย", "duration": 0.7},
            {"text": "เสียงพากย์", "voice": str(voice)},
            {"elements": [{"type": "counter", "to": 99.5, "decimals": 1, "suffix": "%"}],
             "duration": 0.6},
        ],
    })
    out = render(sb, tmp_path / "o.mp4", preset="ultrafast", quiet=True)
    assert set(_probe_streams(out).split()) == {"video", "audio"}
    assert probe_duration(str(out)) == pytest.approx(0.7 + 1.2 + 0.6, abs=0.15)


def test_render_silent_has_audio_track(tmp_path):
    sb = from_dict({"video": {"width": 180, "height": 320, "fps": 10},
                    "scenes": [{"title": "a", "duration": 0.5}]})
    out = render(sb, tmp_path / "s.mp4", preset="ultrafast", quiet=True)
    assert "audio" in _probe_streams(out)


def test_recap_storyboard_still(tmp_path):
    stats = compute_stats(load_deals(SAMPLE))
    sb = build_storyboard(stats, tmp_path / "assets", handle="@me")
    assert len(sb.scenes) == 5
    for i in range(len(sb.scenes)):
        img = render_still(sb, i, 2.0, tmp_path / f"{i}.png")
        assert img.exists()
