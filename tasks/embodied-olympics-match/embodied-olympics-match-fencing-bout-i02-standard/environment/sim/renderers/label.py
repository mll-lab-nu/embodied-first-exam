"""The tag on every re-rendered frame (renderer rule 5): which renderer drew it, bottom right, and whether the scene was
a presentation scene (renderer rule 6)."""
from __future__ import annotations

import numpy as np


PRESENTATION = "presentation meshes, spectators only"


def label_text(engine_title: str, decor: bool = False, presentation: bool = False) -> str:
    return (f"re-rendered: {engine_title}" + (" | surroundings for presentation only" if decor else "")
            + (f" | {PRESENTATION}" if presentation else ""))


def frame_label(renderer, scene) -> str | None:
    """The tag of a spectator frame drawn by `renderer` (a Renderer instance or class) from `scene`: the renderer's
    own label, with the presentation-scene note when the scene is one; None = the competition picture (the default
    renderer on the match scene, or on the presentation scene a sport declares for its players' images), which
    carries no tag."""
    title = getattr(renderer, "title", None) or getattr(renderer, "name", "renderer")
    if getattr(scene, "match", None) is not None and not getattr(scene, "players", False):
        return label_text(title, presentation=True)
    return getattr(renderer, "label", None)


def stamp(img: np.ndarray, text: str) -> np.ndarray:
    from PIL import Image, ImageDraw, ImageFont
    im = Image.fromarray(np.ascontiguousarray(img))
    d = ImageDraw.Draw(im, "RGBA")
    s = max(10, im.size[1] // 40)
    try:
        f = ImageFont.truetype("DejaVuSans.ttf", s)
    except OSError:
        f = ImageFont.load_default()
    w = d.textlength(text, font=f)
    W, H = im.size
    d.rectangle([W - w - 16, H - s - 14, W - 4, H - 4], fill=(0, 0, 0, 150))
    d.text((W - w - 10, H - s - 10), text, font=f, fill=(255, 255, 255, 235))
    return np.asarray(im)
