"""Family C1 exemplars: hidden stroke programs (authored for the benchmark, CC0). Paper millimetres on the main sheet (X right, Y towards
the robot, 0..227). Each stroke: colour (a palette well), control points, press depth (mm) at each control point, speed (mm/s)."""
from __future__ import annotations
import json, math, sys
import numpy as np

PROGRAMS = {}


def wave(x0, x1, y, amp, n=6, phase=0.0, freq=1.0):
    xs = np.linspace(x0, x1, n)
    return [[round(float(x), 2), round(float(y + amp * math.sin(phase + freq * 2 * math.pi * (x - x0) / (x1 - x0))), 2)] for x in xs]


def arc(cx, cy, r, a0, a1, n=6):
    return [[round(cx + r * math.cos(math.radians(a)), 2), round(cy + r * math.sin(math.radians(a)), 2)] for a in np.linspace(a0, a1, n)]


def presses(n, lo, hi):
    """a press profile: light start, full middle, light end (lo -> hi -> lo)"""
    return [round(float(lo + (hi - lo) * math.sin(math.pi * (i + 0.5) / n)), 2) for i in range(n)]


# ---- 1: a small landscape (sky bands, a glowing horizon, the sun, hills, a tree, a foreground field)
L = []
for k, y in enumerate((40, 52, 64, 76)):
    L.append({"color": "sky", "points_mm": wave(32, 195, y, 1.5, 6, k), "press_mm": presses(6, 4.0, 6.5), "speed_mm_s": 40})
for k, y in enumerate((88, 98)):
    L.append({"color": "glow", "points_mm": wave(195, 32, y, 1.2, 6, 0.5 + k), "press_mm": presses(6, 3.5, 6.0), "speed_mm_s": 40})
L.append({"color": "sun", "points_mm": arc(142, 82, 7, 200, 520, 8), "press_mm": presses(8, 3.0, 5.5), "speed_mm_s": 25})
L.append({"color": "sun", "points_mm": arc(142, 82, 3, 0, 300, 6), "press_mm": presses(6, 3.0, 5.0), "speed_mm_s": 25})
for k, (y, a) in enumerate(((118, 6), (126, 5), (134, 4))):
    L.append({"color": "hill", "points_mm": wave(32, 195, y, a, 7, 2.0 + 0.7 * k, 0.8), "press_mm": presses(7, 4.5, 7.0), "speed_mm_s": 35})
for k, y in enumerate((144, 152)):
    L.append({"color": "dark", "points_mm": wave(195, 32, y, 3, 7, 1.0 + k, 1.1), "press_mm": presses(7, 4.0, 6.5), "speed_mm_s": 35})
L.append({"color": "trunk", "points_mm": [[70, 150], [69.5, 136], [70.5, 122], [70, 108]], "press_mm": [3.0, 4.0, 3.5, 2.0], "speed_mm_s": 20})
L.append({"color": "trunk", "points_mm": [[74, 150], [73.5, 138], [74.5, 124], [74, 112]], "press_mm": [2.5, 3.5, 3.0, 1.5], "speed_mm_s": 20})
for (cx, cy, a0) in ((66, 100, 180), (78, 96, 250), (72, 88, 120), (60, 92, 300), (84, 106, 30)):
    L.append({"color": "dark", "points_mm": arc(cx, cy, 6, a0, a0 + 230, 6), "press_mm": presses(6, 4.0, 7.0), "speed_mm_s": 25})
for k, y in enumerate((166, 178, 190)):
    L.append({"color": "ochre", "points_mm": wave(32 + 4 * k, 195 - 3 * k, y, 1.0, 6, 0.3 * k), "press_mm": presses(6, 4.0, 6.5), "speed_mm_s": 40})
PROGRAMS["landscape"] = {"palette": [["sky", "#8fb8de"], ["glow", "#f3dfae"], ["sun", "#f08a24"], ["hill", "#5b9442"], ["dark", "#2e5a2a"],
                                     ["trunk", "#6b4a2f"], ["ochre", "#c9a14a"]], "strokes": L,
                         "description": "a small landscape: sky bands, a glowing horizon, the sun, hills, a tree, a field"}

# ---- 2: a still life (background, table, a blue vase, three fruits, shadows)
S = []
for k, y in enumerate((40, 54, 68, 82, 96)):
    S.append({"color": "wall", "points_mm": wave(32 if k % 2 == 0 else 195, 195 if k % 2 == 0 else 32, y, 1.0, 6, k), "press_mm": presses(6, 5.0, 7.0), "speed_mm_s": 45})
for k, y in enumerate((132, 146, 160)):
    S.append({"color": "table", "points_mm": wave(32, 195, y, 0.8, 6, 0.4 * k), "press_mm": presses(6, 5.0, 7.0), "speed_mm_s": 40})
for (x0, bow) in ((86, -9), (94, -4), (102, 4), (110, 9)):
    S.append({"color": "vase", "points_mm": [[x0 - bow * 0.2, 62], [x0 + bow * 0.3, 80], [x0 + bow, 100], [x0 + bow * 0.6, 118], [x0, 128]],
              "press_mm": [3.0, 4.5, 6.0, 5.5, 3.5], "speed_mm_s": 22})
S.append({"color": "apple", "points_mm": arc(134, 142, 8, 90, 450, 9), "press_mm": presses(9, 4.0, 6.5), "speed_mm_s": 22})
S.append({"color": "apple", "points_mm": arc(134, 142, 3.5, 0, 330, 6), "press_mm": presses(6, 4.0, 6.0), "speed_mm_s": 22})
S.append({"color": "orange", "points_mm": arc(160, 146, 7, 270, 630, 9), "press_mm": presses(9, 4.0, 6.5), "speed_mm_s": 22})
S.append({"color": "lemon", "points_mm": [[104, 152], [112, 148], [121, 150], [122, 156], [112, 159], [104, 156]], "press_mm": [3.5, 5.5, 6.0, 5.5, 5.0, 3.5], "speed_mm_s": 22})
for (x, y, L_) in ((128, 154, 14), (156, 158, 12), (103, 164, 16), (92, 134, 14)):
    S.append({"color": "shadow", "points_mm": [[x - L_ / 2, y], [x, y + 1], [x + L_ / 2, y]], "press_mm": [2.0, 3.5, 2.0], "speed_mm_s": 30})
PROGRAMS["stilllife"] = {"palette": [["wall", "#d9cdb8"], ["table", "#8a5a3b"], ["vase", "#2f5d9c"], ["apple", "#c8342b"], ["orange", "#e8892a"],
                                     ["lemon", "#e8cf3a"], ["shadow", "#4a4038"]], "strokes": S,
                         "description": "a still life: a wall, a table, a blue vase, an apple, an orange, a lemon, shadows"}

if __name__ == "__main__":
    for name, prog in PROGRAMS.items():
        json.dump(prog, open(f"program_{name}.json", "w"), indent=1)
        print(name, len(prog["strokes"]), "strokes,", len(prog["palette"]), "colours")


# ---- programs made by the stroke-based painting optimiser (P, 2026-09-28): programs_json/<name>.json next to this file
import os as _os
_pj = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "programs_json")
if _os.path.isdir(_pj):
    for _f in sorted(_os.listdir(_pj)):
        if _f.endswith(".json"):
            PROGRAMS[_f[:-5]] = json.load(open(_os.path.join(_pj, _f)))
