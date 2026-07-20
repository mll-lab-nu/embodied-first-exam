from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

import numpy as np


HudSource = Callable[[], str | Iterable[str] | None] | str | Iterable[str] | None


def hud_lines(source: HudSource) -> list[str]:
    if source is None:
        return []
    value = source() if callable(source) else source
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(line) for line in value]


def draw_hud_overlay(frame: Any, lines: Iterable[str]) -> Any:
    """Draw a compact text HUD onto a recorded RGB frame.

    The overlay is intentionally optional: if OpenCV is unavailable or the frame
    format is unusual, the original frame is returned unchanged.
    """
    lines = [line for line in lines if line]
    if not lines:
        return frame

    try:
        import cv2
    except ImportError:
        cv2 = None

    image = np.asarray(frame)
    if image.ndim < 3 or image.shape[-1] < 3:
        return frame

    original_dtype = image.dtype
    work = image.copy()
    if original_dtype != np.uint8:
        max_value = float(np.nanmax(work)) if work.size else 1.0
        scale = 255.0 if max_value <= 1.0 else 1.0
        work = np.clip(work * scale, 0, 255).astype(np.uint8)

    if cv2 is None:
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            return frame

        image_pil = Image.fromarray(work[..., :3])
        draw = ImageDraw.Draw(image_pil, "RGBA")
        pad = 12
        line_height = 20
        box_width = min(work.shape[1] - 2 * pad, 360)
        box_height = pad * 2 + line_height * len(lines)
        draw.rectangle((pad, pad, pad + box_width, pad + box_height), fill=(20, 20, 20, 180))
        for index, line in enumerate(lines):
            draw.text((pad * 2, pad * 2 + index * line_height), line, fill=(255, 255, 255, 255))
        work[..., :3] = np.asarray(image_pil)
        if original_dtype != np.uint8 and np.issubdtype(original_dtype, np.floating):
            return work.astype(original_dtype) / 255.0
        return work

    height, width = work.shape[:2]
    scale = max(0.45, min(width, height) / 900.0)
    thickness = max(1, int(round(scale * 2)))
    pad = int(round(12 * scale))
    line_height = int(round(24 * scale))
    box_width = min(width - 2 * pad, max(int(round(320 * scale)), int(width * 0.34)))
    box_height = pad * 2 + line_height * len(lines)

    overlay = work.copy()
    cv2.rectangle(overlay, (pad, pad), (pad + box_width, pad + box_height), (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.68, work, 0.32, 0.0, work)

    x = pad * 2
    y = pad * 2 + int(round(14 * scale))
    for index, line in enumerate(lines):
        if "terminal=True" in line or "success=True" in line:
            color = (110, 245, 150)
        elif "terminal=False" in line or "success=False" in line:
            color = (245, 245, 245)
        else:
            color = (255, 255, 255)
        cv2.putText(
            work,
            line,
            (x, y + index * line_height),
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            color,
            thickness,
            cv2.LINE_AA,
        )

    if original_dtype != np.uint8 and np.issubdtype(original_dtype, np.floating):
        return work.astype(original_dtype) / 255.0
    return work
