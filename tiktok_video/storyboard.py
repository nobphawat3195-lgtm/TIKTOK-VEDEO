"""Storyboard model: a video is a list of scenes, each scene a list of elements."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Shorthand keys on a scene -> default element style.
_SHORTHAND = {
    "title": {"size": 96, "y": 0.26, "color": "#FFFFFF", "anim": "slide_up"},
    "text": {"size": 64, "y": 0.47, "color": "#FFFFFF", "anim": "fade", "delay": 0.25},
    "caption": {"size": 52, "y": 0.70, "color": "#FFD54A", "anim": "pop", "delay": 0.5,
                "box": "#000000AA"},
}


@dataclass
class Element:
    type: str  # text | image | counter
    props: dict[str, Any]

    def get(self, key: str, default: Any = None) -> Any:
        return self.props.get(key, default)


@dataclass
class Scene:
    duration: float | None
    background: dict[str, Any]
    elements: list[Element]
    voice: str | None = None


@dataclass
class Storyboard:
    scenes: list[Scene]
    width: int = 1080
    height: int = 1920
    fps: int = 30
    font: str | None = None
    bgm: str | None = None
    bgm_volume: float = 0.25
    progress_bar: str | None = "#FFD54A"
    base_dir: Path = field(default_factory=Path.cwd)

    def resolve(self, p: str | None) -> str | None:
        if not p:
            return None
        path = Path(p).expanduser()
        return str(path if path.is_absolute() else (self.base_dir / path))


def _parse_background(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {"gradient": ["#141E30", "#243B55"]}
    if isinstance(raw, str):
        if raw.startswith("#"):
            return {"color": raw}
        return {"image": raw}
    return dict(raw)


def _parse_scene(raw: dict[str, Any], defaults: dict[str, Any]) -> Scene:
    elements: list[Element] = []
    for key, style in _SHORTHAND.items():
        if key in raw and raw[key] is not None:
            elements.append(Element("text", {**style, "text": str(raw[key])}))
    for el in raw.get("elements", []) or []:
        el = dict(el)
        elements.append(Element(el.pop("type", "text"), el))
    return Scene(
        duration=raw.get("duration", defaults.get("duration")),
        background=_parse_background(raw.get("background", defaults.get("background"))),
        elements=elements,
        voice=raw.get("voice"),
    )


def from_dict(data: dict[str, Any], base_dir: Path | None = None) -> Storyboard:
    video = data.get("video", {}) or {}
    defaults = data.get("defaults", {}) or {}
    scenes = [_parse_scene(s, defaults) for s in data.get("scenes", [])]
    if not scenes:
        raise ValueError("storyboard ต้องมีอย่างน้อย 1 scene")
    return Storyboard(
        scenes=scenes,
        width=int(video.get("width", 1080)),
        height=int(video.get("height", 1920)),
        fps=int(video.get("fps", 30)),
        font=video.get("font"),
        bgm=video.get("bgm"),
        bgm_volume=float(video.get("bgm_volume", 0.25)),
        progress_bar=video.get("progress_bar", "#FFD54A"),
        base_dir=base_dir or Path.cwd(),
    )


def load(path: str | Path) -> Storyboard:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        import yaml

        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    return from_dict(data, base_dir=path.parent.resolve())
