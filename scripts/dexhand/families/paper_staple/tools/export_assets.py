"""Authoring tool: write the T36 NOVUS B2 stapler meshes as OBJ files plus a sha256 manifest.

The source scene (scene-expansion T36, ``stapler_meta_delivery_polish_r1_trajectory_r1/legacy_geometry.py``) builds
its blue base/handle shells as lofted rounded sections and its anvil walls as extruded wedges directly in MJCF.
The section tables below are copied verbatim from that file so the packaged task loads offline meshes with the same
shape. Run once; the generated files are committed under ``assets/``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1] / "assets"

# (x, half width, low z, high z) in the part frame (legacy_geometry.add_scene)
BASE_SECTIONS = [(-0.066, 0.010, 0, 0.006), (-0.055, 0.015875, 0, 0.007), (0.048, 0.015875, 0, 0.007),
                 (0.066, 0.011, 0, 0.007)]
HANDLE_SECTIONS = [(0, 0.009, 0.026, 0.041), (0.014, 0.015, 0.025, 0.0435), (0.070, 0.015875, 0.023, 0.042),
                   (0.108, 0.0145, 0.018, 0.033), (0.120, 0.009, 0.019, 0.030)]
WEDGE_POINTS = [(0.053, 0.010), (0.067, 0.010), (0.067, 0.012), (0.053, 0.012)]


def loft(sections, n=16):
    vertices, faces = [], []
    for x, width, low, high in sections:
        for a in np.linspace(0, 2 * np.pi, n, endpoint=False):
            vertices.append((x, width * np.sin(a), (low + high) / 2 + (high - low) / 2 * np.cos(a)))
    for i in range(len(sections) - 1):
        for j in range(n):
            k = (j + 1) % n
            a, b, c, d = i * n + j, i * n + k, (i + 1) * n + k, (i + 1) * n + j
            faces.extend([(a, b, c), (a, c, d)])
    last = (len(sections) - 1) * n
    for j in range(1, n - 1):
        faces.extend([(0, j + 1, j), (last, last + j, last + j + 1)])
    return np.asarray(vertices), np.asarray(faces)


def wedge(points, y0, y1):
    p = np.asarray(points)
    v = np.vstack([np.c_[p[:, 0], np.full(len(p), y), p[:, 1]] for y in (y0, y1)])
    n = len(p)
    faces = []
    for i in range(1, n - 1):
        faces.extend([(0, i + 1, i), (n, n + i, n + i + 1)])
    for i in range(n):
        j = (i + 1) % n
        faces.extend([(i, j, j + n), (i, j + n, i + n)])
    return v, np.asarray(faces)


def write_obj(path, vertices, faces):
    lines = ["# NOVUS B2 envelope mesh (scene-expansion T36 legacy_geometry.py sections)"]
    lines += [f"v {x:.9f} {y:.9f} {z:.9f}" for x, y, z in vertices]
    lines += [f"f {a + 1} {b + 1} {c + 1}" for a, b, c in faces]
    path.write_text("\n".join(lines) + "\n")


def main():
    HERE.mkdir(parents=True, exist_ok=True)
    parts = {
        "stapler_base_shell.obj": loft(BASE_SECTIONS),
        "stapler_handle_shell.obj": loft(HANDLE_SECTIONS),
    }
    # scene.py of the source moves both outer anvil walls 2.2 mm outward
    for sign, label in ((-1, "right"), (1, "left")):
        parts[f"anvil_wall_{label}.obj"] = wedge(WEDGE_POINTS, sign * 0.0068 - 0.0012 + sign * 0.0022,
                                                 sign * 0.0068 + 0.0012 + sign * 0.0022)
    for name, (v, f) in parts.items():
        write_obj(HERE / name, v, f)
    files = {}
    for path in sorted(HERE.iterdir()):
        if path.name == "manifest.json":
            continue
        raw = path.read_bytes()
        files[path.name] = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    manifest = {
        "source": "scene-expansion T36 'Align and staple paper documents' "
                  "(robot_coding_bench/scripts/scene_expansion/repairs/stapler_meta_delivery_polish_r1_trajectory_r1/"
                  "legacy_geometry.py + scene.py); authored NOVUS B2 envelope estimate, not manufacturer CAD",
        "generator": "tools/export_assets.py",
        "files": files,
    }
    (HERE / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
