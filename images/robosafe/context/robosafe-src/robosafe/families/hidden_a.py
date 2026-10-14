"""Shared pieces of `hazard_hidden` (0.5.0) for the families whose evidence is a label, a device's state or what a
container holds (docs/hidden/hidden-a.md): a label turned away from the cameras (`other_side`) and a carton stood in
front of a label (`move_first`).

The fixed cameras look from the front of the table (`front`, at x = 0) and from straight above (`top`). A label that
faces the side of the table away from its middle (+x on the right half, -x on the left half) is out of the `front`
camera's view and is never faced by the `top` camera; the wrist camera reads it after a `look` from that side. A
carton stood close in front of a label hides it from the `front` camera and from a `look` from the front; it has to
be taken away first (or the thing behind it taken out)."""
from __future__ import annotations

# A carton of the kind that stands on a bench or a counter: narrow enough for the gripper (taken from above across its
# width, so that the fingers stay clear of the thing behind it), tall enough to hide a label from the `front` camera
# while the shoulders of a bottle show above it, light. Its own print names what is in it.
CARTON = {"width": 0.08, "depth": 0.06, "height": 0.17, "mass": 0.18, "grip": True}
TOWARD_MIDDLE = 0.008   # m: the `front` camera stands at the middle of the table and sees a thing on one side a little from that side
CARTON_GAP = 0.012      # m between the back of the carton and the front of the thing it hides


def away(x: float) -> float:
    """+1 when the side of the table away from its middle is +x (the thing stands on the right half), else -1."""
    return 1.0 if x >= 0.0 else -1.0


def away_side(x: float) -> str:
    """The `look` side from which a label turned away from the middle of the table is read."""
    return "right" if away(x) > 0 else "left"


def turned_away(yaw: float, x: float) -> float:
    """The yaw of a thing whose label faces the front (-y) at `yaw`, turned so that the label faces away from the
    middle of the table."""
    return yaw + 90.0 * away(x)


def carton(name: str, front_of, radius: float, text: str) -> dict:
    """A closed carton standing just in front of a thing (`front_of`: its [x, y]; `radius`: its half depth)."""
    y = front_of[1] - radius - CARTON_GAP - CARTON["depth"] / 2.0
    x = front_of[0] - TOWARD_MIDDLE * away(front_of[0])
    return {"name": name, "kind": "cardboard_box", "pos": [round(x, 3), round(y, 3), 0.0],
            "params": {**CARTON, "text": text}}
