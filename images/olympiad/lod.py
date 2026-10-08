"""Levels of detail of the presentation models (players' images, renderer rule 6): a model's visual meshes decimated
to a triangle budget, so that a sport can draw its players' images with fine meshes on the CPU at a small cost and
bundle them into its simulator directory (a few MB instead of 30).

    python3 -m renderers.presentation.lod build MODEL LEVEL      e.g. build franka_emika_panda 25k

reads the model's verified upstream files from the asset cache (assets.py fetch first), decimates every visual mesh by
the same ratio (quadric error metrics; meshes under MIN_FACES keep at least MIN_FACES triangles), writes
renderers/presentation/lod/<LEVEL>/<model path>/... (OBJ or binary STL as upstream, vertices and faces only: MuJoCo computes the normals) plus a
copy of the model's MJCF file, and records every file's sha256 in lod.json. The levels are committed (derived works of
the upstream files, same licence: LICENSE.<model>); renders read them like the upstream files (assets.model_xml with
meshes=LEVEL), verified by sha256. Building needs `pip install trimesh==5.1.1 fast-simplification==0.2.0` (a developer
step, never run by a match); a rebuild with these versions reproduces the files.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

from . import assets

MIN_FACES = 64
TOOLS = {"trimesh": "5.1.1", "fast-simplification": "0.2.0"}


def target_of(level: str) -> int:
    m = re.fullmatch(r"(\d+)k", level)
    if not m:
        raise ValueError(f"a level is <N>k (N thousand triangles per model), not {level!r}")
    return int(m.group(1)) * 1000


def build(name: str, level: str, log=print) -> dict:
    import numpy as np
    import trimesh
    import fast_simplification as fs
    from . import model_parts
    target = target_of(level)
    xml = assets.model_xml(name)                      # the verified upstream files
    src = xml.parent
    parts = model_parts(xml)
    _, mod = assets._find(name)
    out_base = assets.HERE / "lod" / level
    model_dir = out_base / Path(mod["xml"]).parent
    if model_dir.exists():
        shutil.rmtree(model_dir)
    model_dir.mkdir(parents=True)
    rel_xml = mod["xml"]
    shutil.copyfile(xml, out_base / rel_xml)
    meshes = {}
    for mn, me in parts["meshes"].items():
        t = trimesh.load(src / me["file"], force="mesh", process=False)
        t.merge_vertices(merge_tex=True, merge_norm=True)
        meshes[mn] = (me["file"], t)
    total = sum(len(t.faces) for _, t in meshes.values())
    ratio = min(1.0, target / total)
    n_out, written = 0, {rel_xml: None}
    for mn, (f, t) in sorted(meshes.items()):
        nf = len(t.faces)
        keep = max(MIN_FACES, int(round(nf * ratio)))
        if keep < nf:
            v, fc = fs.simplify(np.asarray(t.vertices, np.float32), np.asarray(t.faces, np.int32),
                                target_reduction=1 - keep / nf)
            t = trimesh.Trimesh(v, fc, process=False)
        n_out += len(t.faces)
        rel = str(Path(rel_xml).parent / f)
        dst = out_base / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.suffix.lower() == ".obj":
            dst.write_text(_obj(t))
        elif dst.suffix.lower() == ".stl":
            dst.write_bytes(_stl(t))
        else:
            raise ValueError(f"{rel}: only OBJ and STL meshes are decimated (got {dst.suffix})")
        written[rel] = None
    shas = {p: assets._sha(out_base / p) for p in sorted(written)}
    man = assets.lods() or {"name": "lod", "note": __doc__.split("\n\n")[0].replace("\n", " "), "models": {}}
    man["tools"] = TOOLS
    man["models"].setdefault(name, {})[level] = {
        "source": f"menagerie@{assets._find(name)[0]['commit']}", "target_triangles": target,
        "source_triangles": total, "triangles": n_out, "files": shas}
    (assets.HERE / assets.LOD_MANIFEST).write_text(json.dumps(man, indent=1, sort_keys=True) + "\n")
    size = sum((out_base / p).stat().st_size for p in shas)
    log(f"{name} {level}: {total} -> {n_out} triangles, {len(shas)} files, {size / 1e6:.2f} MB in {model_dir}")
    return man["models"][name][level]


def _obj(t) -> str:
    """Vertices and triangles only, fixed precision (the same bytes for the same mesh)."""
    import numpy as np
    v = np.asarray(t.vertices, float)
    f = np.asarray(t.faces, int) + 1
    return ("".join(f"v {a:.6f} {b:.6f} {c:.6f}\n" for a, b, c in v)
            + "".join(f"f {a} {b} {c}\n" for a, b, c in f))


def _stl(t) -> bytes:
    """Binary STL (zero normals: MuJoCo computes them), the same bytes for the same mesh."""
    import numpy as np
    tri = np.asarray(t.vertices, np.float32)[np.asarray(t.faces, int)]          # (n, 3, 3)
    rec = np.zeros(len(tri), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    rec["v"] = tri
    return b"\0" * 80 + np.uint32(len(tri)).astype("<u4").tobytes() + rec.tobytes()


def main(argv) -> int:
    if len(argv) != 3 or argv[0] != "build":
        print(__doc__)
        return 2
    build(argv[1], argv[2])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
