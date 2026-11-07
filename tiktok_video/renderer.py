"""Stream composed frames into ffmpeg and mux voice-over + background music."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from .scene import SceneRenderer, draw_progress, frames_for
from .storyboard import Storyboard

DEFAULT_SCENE_SECONDS = 3.0
VOICE_TAIL = 0.4  # breathing room after voice-over ends


def probe_duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out)


def plan_durations(sb: Storyboard) -> list[float]:
    durs = []
    for sc in sb.scenes:
        if sc.duration is not None:
            durs.append(float(sc.duration))
        elif sc.voice:
            durs.append(probe_duration(sb.resolve(sc.voice)) + VOICE_TAIL)
        else:
            durs.append(DEFAULT_SCENE_SECONDS)
    return durs


def _audio_args(sb: Storyboard, starts: list[float], total: float) -> tuple[list[str], list[str]]:
    """Return (input args, output/mapping args) for the audio part of the ffmpeg call."""
    inputs: list[str] = []
    filters: list[str] = []
    labels: list[str] = []
    idx = 1  # 0 is the raw video pipe
    for sc, start in zip(sb.scenes, starts):
        if not sc.voice:
            continue
        inputs += ["-i", sb.resolve(sc.voice)]
        ms = int(start * 1000)
        filters.append(f"[{idx}:a]aresample=44100,adelay={ms}|{ms}[v{idx}]")
        labels.append(f"[v{idx}]")
        idx += 1
    voice_mix = None
    if labels:
        filters.append(f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0,"
                       f"apad,atrim=0:{total:.3f}[voice]")
        voice_mix = "[voice]"
    if sb.bgm:
        inputs += ["-stream_loop", "-1", "-i", sb.resolve(sb.bgm)]
        fade_st = max(0.0, total - 1.0)
        filters.append(f"[{idx}:a]aresample=44100,volume={sb.bgm_volume},atrim=0:{total:.3f},"
                       f"afade=t=out:st={fade_st:.3f}:d=1[bgm]")
        if voice_mix:
            # duck the music under the voice-over
            filters.append("[voice]asplit=2[vo][sc]")
            filters.append("[bgm][sc]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=300[duck]")
            filters.append("[duck][vo]amix=inputs=2:normalize=0[aout]")
        else:
            filters.append("[bgm]anull[aout]")
    elif voice_mix:
        filters.append("[voice]anull[aout]")
    else:
        inputs += ["-f", "lavfi", "-t", f"{total:.3f}", "-i", "anullsrc=r=44100:cl=stereo"]
        filters.append(f"[{idx}:a]anull[aout]")
    return inputs, ["-filter_complex", ";".join(filters), "-map", "0:v", "-map", "[aout]"]


def render(sb: Storyboard, output: str | Path, *, crf: int = 20, preset: str = "medium",
           quiet: bool = False) -> Path:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ต้องติดตั้ง ffmpeg ก่อน")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)

    durs = plan_durations(sb)
    frame_counts = [frames_for(d, sb.fps) for d in durs]
    starts, acc = [], 0
    for n in frame_counts:
        starts.append(acc / sb.fps)
        acc += n
    total_frames = acc
    total = total_frames / sb.fps

    a_in, a_out = _audio_args(sb, starts, total)
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{sb.width}x{sb.height}",
        "-r", str(sb.fps), "-i", "-",
        *a_in, *a_out,
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p",
        "-profile:v", "high", "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        "-t", f"{total:.3f}", "-movflags", "+faststart", str(output),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None
    done = 0
    try:
        for i, (scene, dur, n) in enumerate(zip(sb.scenes, durs, frame_counts)):
            r = SceneRenderer(scene, sb, dur)
            for f in range(n):
                frame = r.frame(f / sb.fps)
                if sb.progress_bar:
                    draw_progress(frame, (done + 1) / total_frames, sb.progress_bar)
                proc.stdin.write(frame.tobytes())
                done += 1
            if not quiet:
                print(f"  scene {i + 1}/{len(sb.scenes)} ({dur:.1f}s) ✓", file=sys.stderr)
        proc.stdin.close()
    except BrokenPipeError:
        pass
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg ล้มเหลว (exit {proc.returncode})")
    return output


def render_still(sb: Storyboard, scene_index: int, t: float, output: str | Path) -> Path:
    """Render one frame to PNG — quick preview without encoding the whole video."""
    durs = plan_durations(sb)
    r = SceneRenderer(sb.scenes[scene_index], sb, durs[scene_index])
    img = r.frame(t)
    img.save(output)
    return Path(output)
