#!/usr/bin/env python3
"""Build the sim_to_real MuJoCo asset tree from NVIDIA RoboLab's asset library (run by images/sim_to_real/Dockerfile).

    OMP_NUM_THREADS=1 python build_assets.py <robolab repo root> <out dir> [--manifest manifest.sha256]   (without: writes <out>/manifest.sha256)

Inputs (RoboLab v0.3.1, assets/): scanned YCB objects (MIT, YCB-Video / BOP), RoboLab's fruit models and grey tote
(Apache-2.0), the Oak wood texture, and the `reading_room_2k` HDRI (Poly Haven, CC0). Only redistributable subsets are
used; HOPE / HANDAL (CC BY-NC-SA) and HOT3D (Meta licence) are not.

Per object: the visual mesh with its UVs (`visual.obj`) and texture downscaled to 1024 px (`texture.png`), a convex
decomposition for collision (CoACD, `col_NN.obj`, canonical order; single-threaded so it is reproducible) and
`meta.json` (bounding box, mass = the YCB dataset's measured mass of the physical object, hull volumes). The tote keeps
RoboLab's mesh for rendering; its collision is box walls fitted in rcb_yam.py. The HDRI becomes six tone-mapped skybox
faces. Every output file is listed with its sha256 in manifest.sha256; the image build fails if a rebuild differs (the
frozen instances' state hashes depend on these meshes).
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np
from pxr import Usd, UsdGeom, UsdShade  # before coacd: importing coacd first makes the pxr import segfault

OBJECTS = {  # name: (RoboLab asset, mass kg: the YCB object set's published mass of the physical object)
    "bowl": ("objects/ycb/bowl.usd", 0.147),
    "banana": ("objects/ycb/banana.usd", 0.066),
    "mug": ("objects/ycb/mug.usd", 0.118),
    "tomato_soup_can": ("objects/ycb/tomato_soup_can.usd", 0.349),
    "spam_can": ("objects/ycb/spam_can.usd", 0.370),  # YCB 010 potted meat can
    "foam_brick": ("objects/ycb/brick.usd", 0.028),  # YCB 061
    "marker": ("objects/ycb/dry_erase_marker.usd", 0.016),  # YCB 040 large marker
    "lemon": ("objects/fruits_veggies/lemon1.usd", 0.029),  # YCB's plastic lemon / orange weights
    "orange": ("objects/fruits_veggies/orange1.usd", 0.047),
}
TOTE = "fixtures/grey_bin.usda"
OAK = "materials/Base/Wood/Oak/Oak_BaseColor.png"
HDRI = "backgrounds/indoors/reading_room_2k.hdr"
TEX_PX = 1024
SKY_PX = 1024


def mesh_world(prim, M_root):
    m = UsdGeom.Mesh(prim)
    pts = np.array(m.GetPointsAttr().Get(), dtype=np.float64)
    M = (
        np.array(UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default()), dtype=np.float64)
        @ M_root
    )
    pts = (np.c_[pts, np.ones(len(pts))] @ M)[:, :3]
    counts = np.array(m.GetFaceVertexCountsAttr().Get())
    idx = np.array(m.GetFaceVertexIndicesAttr().Get())
    st = next(
        (p for n in ("st", "st0", "UVMap", "uv") if (p := UsdGeom.PrimvarsAPI(prim).GetPrimvar(n)) and p.HasValue()),
        None,
    )
    tris, corners, k = [], [], 0
    for c in counts:
        for j in range(1, c - 1):
            tris.append((idx[k], idx[k + j], idx[k + j + 1]))
            corners.append((k, k + j, k + j + 1))
        k += c
    tris, corners = np.array(tris), np.array(corners)
    if st is None:
        return pts, tris, None, None
    uv = np.array(st.Get(), dtype=np.float64)
    ui = np.array(st.GetIndices()) if st.IsIndexed() else None
    base = corners if st.GetInterpolation() == "faceVarying" else tris
    return pts, tris, uv, (ui[base] if ui is not None else base)


def write_obj(path: Path, pts, tris, uv=None, fv=None) -> None:
    lines = [f"v {p[0]:.6f} {p[1]:.6f} {p[2]:.6f}" for p in pts]
    if uv is not None:
        lines += [f"vt {t[0]:.6f} {t[1]:.6f}" for t in uv]
        lines += [f"f {a[0]}/{b[0]} {a[1]}/{b[1]} {a[2]}/{b[2]}" for a, b in zip(tris + 1, fv + 1)]
    else:
        lines += [f"f {a[0]} {a[1]} {a[2]}" for a in tris + 1]
    path.write_text("\n".join(lines) + "\n")


def diffuse_texture(stage, prims):
    for p in prims:
        mat = UsdShade.MaterialBindingAPI(p).ComputeBoundMaterial()[0]
        if not mat:
            continue
        for sh in Usd.PrimRange(mat.GetPrim()):
            if sh.GetTypeName() == "Shader":
                i = UsdShade.Shader(sh).GetInput("diffuse_texture")
                if i and i.Get() and i.Get().resolvedPath:
                    return i.Get().resolvedPath
    return None


def save_texture(src, dst: Path, px: int) -> None:
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = None
    im = Image.open(src).convert("RGB")
    im.thumbnail((px, px), Image.LANCZOS)
    im.save(dst)


def convert_object(src: Path, out: Path, mass: float) -> dict:
    import coacd
    import trimesh

    st = Usd.Stage.Open(str(src))
    root = st.GetDefaultPrim()
    M_root = np.linalg.inv(
        np.array(UsdGeom.Xformable(root).ComputeLocalToWorldTransform(Usd.TimeCode.Default()), dtype=np.float64)
    )
    mpu = UsdGeom.GetStageMetersPerUnit(st)
    prims = [p for p in Usd.PrimRange(root) if p.GetTypeName() == "Mesh"]
    P, T, UV, FV, off, uoff = [], [], [], [], 0, 0
    for p in prims:
        pts, tris, uv, fv = mesh_world(p, M_root)
        P.append(pts * mpu)
        T.append(tris + off)
        off += len(pts)
        if uv is not None:
            UV.append(uv)
            FV.append(fv + uoff)
            uoff += len(uv)
    P, T = np.vstack(P), np.vstack(T)
    UV, FV = (np.vstack(UV), np.vstack(FV)) if UV else (None, None)
    out.mkdir(parents=True, exist_ok=True)
    write_obj(out / "visual.obj", P, T, UV, FV)
    tex = diffuse_texture(st, prims)
    if tex:
        save_texture(tex, out / "texture.png", TEX_PX)
    tm = trimesh.Trimesh(P, T, process=True)
    parts = coacd.run_coacd(
        coacd.Mesh(tm.vertices, tm.faces), threshold=0.04, max_convex_hull=24, seed=0, resolution=2000
    )
    parts = sorted(parts, key=lambda vf: tuple(np.round(np.asarray(vf[0]).mean(0), 5)))
    vols = []
    for i, (v, f) in enumerate(parts):
        write_obj(out / f"col_{i:02d}.obj", np.asarray(v), np.asarray(f))
        vols.append(abs(float(trimesh.Trimesh(np.asarray(v), np.asarray(f)).convex_hull.volume)))
    meta = {
        "source": f"RoboLab assets/{src.relative_to(src.parents[2])}",
        "mass": mass,
        "n_hulls": len(parts),
        "hull_volume": round(sum(vols), 9),
        "bbox_min": np.round(P.min(0), 6).tolist(),
        "bbox_max": np.round(P.max(0), 6).tolist(),
        "texture": bool(tex),
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=1) + "\n")
    return meta


def convert_tote(src: Path, out: Path) -> None:
    st = Usd.Stage.Open(str(src))
    p = st.GetPrimAtPath("/grey_bin/Tote_B09_01")
    pts, tris, uv, fv = mesh_world(p, np.eye(4))
    out.mkdir(parents=True, exist_ok=True)
    write_obj(out / "visual.obj", pts, tris, uv, fv)
    meta = {
        "source": "RoboLab assets/fixtures/grey_bin.usda (Tote_B09, scale 0.007)",
        "bbox_min": np.round(pts.min(0), 6).tolist(),
        "bbox_max": np.round(pts.max(0), 6).tolist(),
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=1) + "\n")


def skybox(src: Path, out: Path, n: int = SKY_PX, exposure: float = 1.0) -> None:
    """Equirect HDR -> six faces (MuJoCo skybox file{right,left,up,down,front,back}), Reinhard tone map, gamma 2.2."""
    import cv2
    from PIL import Image

    eq = cv2.imread(str(src), cv2.IMREAD_ANYDEPTH | cv2.IMREAD_COLOR)[..., ::-1].astype(np.float32)
    H, W, _ = eq.shape
    a = (np.arange(n) + 0.5) / n * 2 - 1
    s, t = np.meshgrid(a, -a)
    faces = {
        "px": ((1, 0, 0), (0, -1, 0), (0, 0, 1)),
        "nx": ((-1, 0, 0), (0, 1, 0), (0, 0, 1)),
        "py": ((0, 1, 0), (1, 0, 0), (0, 0, 1)),
        "ny": ((0, -1, 0), (-1, 0, 0), (0, 0, 1)),
        "pz": ((0, 0, 1), (0, -1, 0), (-1, 0, 0)),
        "nz": ((0, 0, -1), (0, -1, 0), (1, 0, 0)),
    }
    out.mkdir(parents=True, exist_ok=True)
    for k, (f, r, u) in faces.items():
        d = np.array(f)[None, None] + s[..., None] * np.array(r)[None, None] + t[..., None] * np.array(u)[None, None]
        lon = np.arctan2(d[..., 1], d[..., 0])
        lat = np.arcsin(np.clip(d[..., 2] / np.linalg.norm(d, axis=-1), -1, 1))
        uu = (((0.5 - lon / (2 * np.pi)) % 1.0) * (W - 1)).astype(np.float32)
        vv = ((0.5 - lat / np.pi) * (H - 1)).astype(np.float32)
        x = cv2.remap(eq, uu, vv, cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP) * exposure
        Image.fromarray((np.clip(x / (1 + x), 0, 1) ** (1 / 2.2) * 255).astype(np.uint8)).save(out / f"{k}.png")


def manifest(root: Path) -> str:
    rows = [
        f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(root)}"
        for p in sorted(root.rglob("*"))
        if p.is_file()
    ]
    return "\n".join(rows) + "\n"


def main(argv: list[str]) -> int:
    src, out = Path(argv[0]) / "assets", Path(argv[1])
    if os.environ.get("OMP_NUM_THREADS") != "1":
        print("set OMP_NUM_THREADS=1 (CoACD is only reproducible single-threaded)")
        return 2
    for name, (rel, mass) in OBJECTS.items():
        print(name, json.dumps(convert_object(src / rel, out / "objects" / name, mass)))
    convert_tote(src / TOTE, out / "fixtures" / "tote")
    (out / "materials").mkdir(parents=True, exist_ok=True)
    save_texture(src / OAK, out / "materials" / "oak.png", TEX_PX)
    skybox(src / HDRI, out / "sky" / "reading_room")
    m = manifest(out)
    if "--manifest" not in argv:
        (out / "manifest.sha256").write_text(m)
        print("wrote", out / "manifest.sha256")
    if "--manifest" in argv:
        exp = Path(argv[argv.index("--manifest") + 1]).read_text()
        if exp != m:
            import difflib

            print(
                "".join(list(difflib.unified_diff(exp.splitlines(True), m.splitlines(True), "expected", "built"))[:60])
            )
            print("FAIL: the converted assets differ from manifest.sha256")
            return 1
        print("ok: assets match manifest.sha256")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
