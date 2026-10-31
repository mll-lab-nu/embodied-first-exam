"""Kinematic MPM collider descriptions of the dough tools (pure Python; dimensions mirror the tool meshes of the assets).

Tool frame: ``press_tool`` origin = centre of the pressing face, +z away from the dough; ``scraper_tool`` origin = centre of the
blade's bottom edge, blade normal +x.  ``tool_spec`` returns a dict for the dough world (``cfg["tools"]``).
"""

from __future__ import annotations

from typing import Dict, Optional

HANDLE_R, HANDLE_H = 0.009, 0.070  # square handle: half side 9 mm (18 x 18 mm), 7 cm long
PRESS_HEAD = (0.050, 0.050, 0.008)
STAMP_HEAD = (0.016, 0.016, 0.008)  # narrow press head: imprints strokes
CARRIER_HEAD = (
    0.018,
    0.018,
    0.008,
)  # fem_plug_insert carrier variant: the gripper holds the carrier, the plug hangs below its bottom face
SCRAPER_BLADE = (0.004, 0.080, 0.030)  # thickness (x), width (y), height (z)

#: where the gripper holds the tool, along the tool z axis from the working face [m] (middle of the handle)
GRIP_Z = {
    "press_tool": PRESS_HEAD[2] + 0.5 * HANDLE_H,
    "scraper_tool": SCRAPER_BLADE[2] + 0.5 * HANDLE_H,
    "stamp_tool": STAMP_HEAD[2] + 0.5 * HANDLE_H,
    "plug_carrier": CARRIER_HEAD[2] + 0.5 * HANDLE_H,
}


def tool_spec(kind: str, name: Optional[str] = None, mu: Optional[float] = None) -> Dict:
    """MPM collider of a tool (``kind``: ``press_tool`` | ``scraper_tool`` | ``stamp_tool``)."""
    if kind in ("press_tool", "stamp_tool"):
        head = PRESS_HEAD if kind == "press_tool" else STAMP_HEAD
        hx, hy, hz = (0.5 * v for v in head)
        shapes = [
            {"type": "box", "half": [hx, hy, hz], "offset": [0, 0, hz]},
            {"type": "box", "half": [HANDLE_R, HANDLE_R, 0.5 * HANDLE_H], "offset": [0, 0, head[2] + 0.5 * HANDLE_H]},
        ]
    elif kind == "scraper_tool":
        hx, hy, hz = (0.5 * v for v in SCRAPER_BLADE)
        shapes = [
            {"type": "box", "half": [hx, hy, hz], "offset": [0, 0, hz]},
            {
                "type": "box",
                "half": [HANDLE_R, HANDLE_R, 0.5 * HANDLE_H],
                "offset": [0, 0, SCRAPER_BLADE[2] + 0.5 * HANDLE_H],
            },
        ]
    else:
        raise KeyError(kind)
    spec = {"name": name or kind, "shapes": shapes}
    if mu is not None:
        spec["mu"] = float(mu)
    return spec
