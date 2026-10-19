"""Runtime integration of the reviewed CPU realism assets.

Derived from the frozen pilot realizer; provenance and licenses travel with the data.
This module performs MuJoCo visual mesh/material replacement, without a Blender dependency.

`catalog.build` and `catalog.write` apply this profile by default. Native source
geometry remains available through `build_files` and the explicit native profile.

What changes is only what is drawn: collision geoms, masses, inertia, joints, sites, actuators stay as RSB built them.
Kept as RSB draws them in every mode: labels and pictograms (geoms with a textured RSB material), `liquid`, the geoms a
look recolours, glass, and the names a kind's plan keeps. Parameter -> variant mapping (also on the review page):
  figures   pose -> the posed variant; skin -> base person of that skin group (light: light, fair; medium: medium,
            olive; dark: brown, dark) and a multiplicative tint within the group; which base of the group: a stable hash
            of the other look parameters (hair, shirt, trousers, height); hair, shirt, trousers -> the hair and the
            clothes recoloured to the RSB colour (luminance kept); toddler and infant likewise.
  hand      skin -> as above; side -> mirrored hand; scale -> scale; sleeve -> RSB's sleeve geoms, kept.
  cat, dog  pose -> standing or lying model; fur -> the fur recoloured to the RSB colour (pattern kept).
  things    the colour parameter -> the texture recoloured (whole object, or only its saturated parts); size parameters
            -> the mesh scaled with the RSB box.
  material  RSB's own shapes keep their colours; their finish becomes a textured material.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

import numpy as np

DATA = Path(__file__).with_name("data") / "realism_v3"
_CONFIG = json.loads((DATA / "plan.json").read_text())
P = SimpleNamespace(**_CONFIG)
PACKS = str(DATA / "packs")
MATLIB_DIR = str(DATA / "matlib")
MATLIB = json.loads((DATA / "matlib" / "matlib.json").read_text())
COL = json.loads((DATA / "rsb_colors.json").read_text())
PROFILE = "realism_v3"
SOURCE_COMMIT = "b5bf3128ffb2435129ea2a85e46206e081f388f1"

_PACK_CACHE: dict = {}
_IMAGE_HASHES: dict[str, str] = {}
SKIN_REF = {"light": COL["SKIN"]["light"], "medium": COL["SKIN"]["medium"], "dark": COL["SKIN"]["brown"]}
GLASS = {"glass", "glass_clear", "glass_frosted", "plastic_clear"}


def pack(kind):
    if kind not in _PACK_CACHE:
        p = os.path.join(PACKS, kind, "pack.json")
        _PACK_CACHE[kind] = json.load(open(p)) if os.path.exists(p) else None
    return _PACK_CACHE[kind]


def _rgba(g):
    s = g.get("rgba")
    return [float(x) for x in s.split()] if s else None


def _lum(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def skin_group(rgb):
    y = _lum(rgb)
    return "light" if y > 0.70 else ("medium" if y > 0.47 else "dark")


def stable_index(obj, n):
    h = hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()
    return int(h[:8], 16) % max(1, n)


def recolor(path, rgb, mode):
    """A copy of the texture recoloured to `rgb` with its light and dark kept (cached next to the pack)."""
    from PIL import Image

    if path not in _IMAGE_HASHES:
        _IMAGE_HASHES[path] = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    color = np.asarray(rgb, dtype=float).tolist()
    key = hashlib.sha256(f"{_IMAGE_HASHES[path]}|{mode}|{color}|clip0.3-1.25".encode()).hexdigest()[:16]
    from .catalog import cache_dir

    cdir = str(cache_dir() / "realism_colors")
    os.makedirs(cdir, exist_ok=True)
    out = os.path.join(cdir, f"{os.path.basename(path)[:-4]}_{key}.png")
    if os.path.exists(out):
        return out
    a = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32) / 255.0
    lum = 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]
    valid = lum > 0.02
    m = np.clip(lum / max(1e-6, float(lum[valid].mean())), 0.3, 1.25) if valid.any() else lum
    if max(rgb[:3]) < 0.12:
        m = 0.25 + 0.75 * m
        rgb = [max(float(x), 0.12) for x in rgb[:3]]
    t = np.asarray(rgb[:3], dtype=np.float32)
    new = np.clip(t[None, None, :] * m[..., None], 0, 1)
    if mode == "saturated":
        mx, mn = a.max(axis=2), a.min(axis=2)
        sat = (mx - mn) / np.maximum(mx, 1e-6)
        w = np.clip((sat - 0.15) / 0.2, 0, 1)[..., None]
        new = a * (1 - w) + new * w
    tmp = out + f".{os.getpid()}.tmp"
    Image.fromarray((new * 255).astype(np.uint8)).save(tmp, format="PNG")
    os.replace(tmp, out)
    return out


_VERTS: dict = {}


def _obj_verts(path):
    """The vertices of an OBJ we wrote (cached)."""
    if path not in _VERTS:
        with open(path) as f:
            _VERTS[path] = np.array([[float(x) for x in ln.split()[1:4]] for ln in f if ln.startswith("v ")])
    return _VERTS[path]


def umeyama(src, dst):
    """s, R, t minimising |s R src + t - dst| (proper rotation)."""
    src, dst = np.asarray(src, float), np.asarray(dst, float)
    mu_s, mu_d = src.mean(0), dst.mean(0)
    xs, xd = src - mu_s, dst - mu_d
    C = xd.T @ xs / len(src)
    U, S, Vt = np.linalg.svd(C)
    D = np.eye(3)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        D[2, 2] = -1
    R = U @ D @ Vt
    var = (xs ** 2).sum() / len(src)
    s = float(np.trace(np.diag(S) @ D) / var)
    t = mu_d - s * R @ mu_s
    return s, R, t


def mat2quat(R):
    import mujoco

    q = np.zeros(4)
    mujoco.mju_mat2Quat(q, np.asarray(R, dtype=np.float64).reshape(-1))
    return q


class _Doc:
    def __init__(self, path):
        self.tree = ET.parse(path)
        self.root = self.tree.getroot()
        self.asset = self.root.find("asset")
        if self.asset is None:
            self.asset = ET.SubElement(self.root, "asset")
        self.textured = {m.get("name") for m in self.asset.findall("material") if m.get("texture")}
        self.mats = {m.get("name"): m for m in self.asset.findall("material")}
        self.added = set()

    def add_lib_material(self, mid):
        name = "rx_" + mid
        if name in self.added:
            return name
        L = MATLIB[mid]
        ET.SubElement(self.asset, "texture", {"name": name, "type": "cube", "file": os.path.join(MATLIB_DIR, L["file"])})
        ET.SubElement(self.asset, "material", {"name": name, "texture": name, "texuniform": "false",
                                               "texrepeat": f"{L['texrepeat'][0]} {L['texrepeat'][1]}", "specular": str(L["specular"]),
                                               "shininess": str(L["shininess"]), "reflectance": str(L["reflectance"])})
        self.added.add(name)
        return name

    def add_mesh_geom(self, body, name, obj, png, rgba, scale, pos, quat, mat=None, index=0):
        ET.SubElement(self.asset, "mesh", {"name": name, "file": obj, "inertia": "shell", "scale": " ".join(f"{v:.6f}" for v in scale)})
        mattr = {"name": name}
        if png:
            ET.SubElement(self.asset, "texture", {"name": name, "type": "2d", "file": png})
            mattr["texture"] = name
        mattr["rgba"] = " ".join(f"{v:.4f}" for v in rgba)
        mattr.update(mat or {"specular": "0.15", "shininess": "0.25"})
        ET.SubElement(self.asset, "material", mattr)
        attrs = {"name": name, "class": "rsb_visual", "type": "mesh", "mesh": name, "material": name,
                 "pos": " ".join(f"{v:.6f}" for v in pos), "quat": " ".join(f"{v:.8f}" for v in quat)}
        body.insert(index, ET.Element("geom", attrs))


def _protected(doc, g, meta, keep):
    name = g.get("name", "")
    looks = set()
    for lk in (meta.get("looks") or {}).values():
        looks |= set(lk)
    return (name in keep or name == "liquid" or name in looks or g.get("material") in doc.textured
            or g.get("material") in GLASS or (g.get("material") or "").startswith("rx_"))


def _material_only(doc, kind, meta, plan):
    finish, geom_mat = plan.get("finish", P.DEFAULT_FINISH), plan.get("geom_mat", {})
    changed = 0
    for g in doc.root.iter("geom"):
        if g.get("class") not in ("rsb_visual", "rsb_solid") or _protected(doc, g, meta, set()):
            continue
        name, mat = g.get("name", ""), g.get("material")
        lib = next((v for k, v in geom_mat.items() if name.startswith(k)), None)
        # CPU_CARDBOARD_TAPE_SEGMENTS: top tape and both anonymous side strips.
        if lib is None and kind == "cardboard_box" and mat == "gloss":
            lib = "plastic"
        if lib is None:
            lib = P.BY_RSB_MATERIAL.get(mat, finish) if mat not in ("matte", "satin", "gloss", None) else finish
        if lib is None:
            continue
        rgba = _rgba(g)
        if lib == "wood":
            lib = "wood_light" if rgba is None else "painted"
        if rgba is None:
            rgba = list(COL["MATERIALS"].get(mat, [0.7, 0.7, 0.7, 1.0]))
        if not MATLIB[lib]["tint"]:
            rgba = [1.0, 1.0, 1.0, rgba[3]]
        g.set("material", doc.add_lib_material(lib))
        g.set("rgba", " ".join(f"{v:.4f}" for v in rgba))
        changed += 1
    return changed


def _part_centres(path):
    import mujoco

    m = mujoco.MjModel.from_xml_path(path)
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)
    return {m.geom(i).name: d.geom_xpos[i].copy() for i in range(m.ngeom) if m.geom(i).name}, \
           {m.geom(i).name: m.geom_rgba[i].copy() for i in range(m.ngeom) if m.geom(i).name}


FORCE: dict = {}          # kind -> variant id, for the review page's variant sheets only


def _choose_variant(kind, pk, params, rgba_of):
    plan = P.S[kind]
    if kind in FORCE:
        v = FORCE[kind]
        return v, pk["variants"][v].get("group")
    if pk["align"] == "points":
        poses = pk["poses"]
        default_pose = next(iter(poses))
        pose = params.get("pose", default_pose) if default_pose is not None else None
        our_pose = poses.get(pose, poses.get(default_pose))
        skin = rgba_of.get(plan["tint"]["skin"])
        group = skin_group(skin[:3]) if skin is not None else "light"
        cands = sorted(v for v, x in pk["variants"].items() if x["pose"] == our_pose and x["group"] == group)
        if not cands:
            cands = sorted(v for v, x in pk["variants"].items() if x["pose"] == our_pose)
        look = {k: params.get(k) for k in ("hair", "shirt", "trousers", "height", "suit")}
        return cands[stable_index(look, len(cands))], group
    if pk["align"] == "frame":
        skin = rgba_of.get(plan["tint"]["skin"])
        group = skin_group(skin[:3]) if skin is not None else "light"
        side = params.get("side", "right")
        cands = sorted(v for v, x in pk["variants"].items() if x["group"] == group and x["side"] == side)
        return cands[0], group
    if pk.get("animal"):
        return params.get("pose", "standing"), None
    if params.get("pose") and params["pose"] in pk["variants"]:
        return params["pose"], None
    return "default", None


def realize(kind, prop, out_suffix="_real"):
    plan = P.S.get(kind, {"mode": "material", "finish": P.DEFAULT_FINISH})
    if plan["mode"] == "kept":
        return prop
    meta = prop.meta
    params = dict(meta.get("params") or {})
    doc = _Doc(prop.path)
    if plan["mode"] == "material":
        _material_only(doc, kind, meta, plan)
    else:
        pk = pack(kind)
        if pk is None:
            raise FileNotFoundError(f"Missing realism_v3 mesh pack for {kind}: {PACKS}")
        centres, rgba_of = _part_centres(prop.path)
        vid, group = _choose_variant(kind, pk, params, rgba_of)
        var = pk["variants"][vid]
        keep = set(pk.get("keep") or [])
        hide_only = plan.get("hide_only", pk.get("hide_only"))
        for parent in doc.root.iter():
            for g in list(parent.findall("geom")):
                cls, name = g.get("class"), g.get("name", "")
                if cls not in ("rsb_visual", "rsb_solid"):
                    continue
                if hide_only is not None:
                    if name not in hide_only:
                        continue
                elif _protected(doc, g, meta, keep):
                    continue
                if cls == "rsb_visual":
                    parent.remove(g)
                else:
                    g.set("class", "rsb_collision")
        # where the mesh goes
        if pk["align"] == "points":
            support = var.get("support_fit") if kind == "person_down" else None
            if support:
                # The authored fallen rig is calibrated in its side/prone frame.
                # An unconstrained all-limb fit tilts the torso off the floor when
                # native and visual limb proportions differ. Preserve its pose and
                # use the reviewed trunk support plane, rather than a hand or shoe.
                s = float(params["height"]) / float(support["rest_height"])
                R = np.asarray(support["canonical_rotation"], dtype=float)
                t = np.mean([centres[n] - s * R @ np.asarray(var["points"][n])
                             for n in ("torso", "pelvis")], axis=0)
                t[2] = float(meta["bbox"][0][2]) - s * float(support["support_coordinate"])
            else:
                names = [n for n in var["points"] if n in centres]
                s, R, t = umeyama([var["points"][n] for n in names], [centres[n] for n in names])
                # rest on what the figure rests on: the lowest drawn point goes to the bottom of RSB's box
                zmin = min(float((s * (_obj_verts(os.path.join(PACKS, kind, gm["obj"])) @ R.T))[:, 2].min()) for gm in var["geoms"])
                t = np.asarray(t, dtype=float)
                t[2] = float(meta["bbox"][0][2]) - zmin
            scale, pos, quat = [s, s, s], t, mat2quat(R)
        elif pk["align"] == "frame":
            s = float(params.get("scale", 1.0))
            scale, pos, quat = [s, s, s], [0, 0, 0], [1, 0, 0, 0]
        else:
            lo, hi = np.asarray(meta["bbox"][0]), np.asarray(meta["bbox"][1])
            rlo, rhi = np.asarray(var["rsb_bbox"][0]), np.asarray(var["rsb_bbox"][1])
            ratio = (hi - lo) / np.maximum(rhi - rlo, 1e-9)
            fit = var.get("fit") or "max"
            if fit in ("xyz", "xy_z"):
                scale = ratio.tolist()
            else:
                i = "xyz".index(fit) if fit in ("x", "y", "z") else int(np.argmax(rhi - rlo))
                scale = [float(ratio[i])] * 3
            pos, quat = [0, 0, 0], [1, 0, 0, 0]
            if kind == "dog" and vid == "standing":
                # The standing scan faces -x; the original dog/head site faces +x.
                # A rigid half-turn about the actual visual bbox centre preserves
                # its bounds and every authored vertex/normal/UV/texture value.
                vertices = np.concatenate([_obj_verts(os.path.join(PACKS, kind, gm["obj"]))
                                           for gm in var["geoms"]])
                center = (vertices.min(axis=0)+vertices.max(axis=0))/2*np.asarray(scale)
                pos, quat = [float(2*center[0]), float(2*center[1]), 0], [0, 0, 0, 1]
            if kind == "flower_pot":
                # The scan is a pot, whereas meta.bbox also includes the plant.
                # Match the original vessel shell (bottom 4mm, rim at height),
                # retaining the original saucer, soil, stem and leaves.
                vlo, vhi = np.asarray(var["after_bbox"][0]), np.asarray(var["after_bbox"][1])
                radius, height = float(params.get("radius", .065)), float(params.get("height", .11))
                target_lo, target_hi = np.array([-radius, -radius, .004]), np.array([radius, radius, height])
                scale = ((target_hi-target_lo)/np.maximum(vhi-vlo, 1e-9)).tolist()
                pos = (target_lo-vlo*np.asarray(scale)).tolist()
        # colours
        tint = plan.get("tint") or {}
        rec = plan.get("recolor")
        body = doc.root.find("worldbody").find("body")
        first = list(body).index(body.find("geom")) if body.find("geom") is not None else 0
        kdir = os.path.join(PACKS, kind)
        for i, gm in enumerate(var["geoms"]):
            png = os.path.join(kdir, gm["png"]) if gm.get("png") else None
            rgba = list(gm.get("rgba", [1, 1, 1, 1])) if not png else [1, 1, 1, 1]
            role = plan.get("material_roles", {}).get(vid, {}).get(str(i), gm.get("role", "body"))
            if png and role == "skin" and tint.get("skin") in rgba_of:
                c = rgba_of[tint["skin"]][:3]
                ref = np.asarray(SKIN_REF[group or "light"])
                f = np.clip(np.asarray(c) / ref, 0.45, 1.0)
                rgba = [float(f[0]), float(f[1]), float(f[2]), 1.0]
            elif png and role in ("hair", "shirt", "trousers", "fur", "sleeve"):
                src_geom = "forearm" if role == "sleeve" else tint.get(role)
                c = rgba_of.get(src_geom) if src_geom else None
                if c is None and role == "trousers" and params.get("trousers") in COL["COLORS"]:
                    c = np.asarray(COL["COLORS"][params["trousers"]]) / 255.0
                if c is not None:
                    png = recolor(png, list(c[:3]), "whole")
            elif png and rec and role in rec.get("roles", ["body"]):
                c = rgba_of.get(rec["geom"])
                is_wood = False
                for g in ET.parse(prop.path).getroot().iter("geom"):
                    if g.get("name") == rec["geom"]:
                        is_wood = g.get("material") == "wood" and g.get("rgba") is None
                if c is not None and not (rec.get("keep_if") == "wood" and is_wood):
                    png = recolor(png, list(c[:3]), rec["mode"])
            from .visual_parts import partition

            parts = partition(os.path.join(kdir, gm["obj"]), prop, scale, pos, quat)
            for part, obj in parts:
                name = f"{part}_realism_{vid}_{i}" if part else f"rx_{vid}_{i}"
                doc.add_mesh_geom(body, name, obj, png, rgba, scale, pos, quat,
                                  mat=gm.get("material"), index=first + i)
    new = prop.path[:-4] + out_suffix + ".xml"
    ET.indent(doc.tree, "  ")
    doc.tree.write(new, encoding="unicode")
    return dataclasses.replace(prop, path=new)


def decorate(spec):
    """Apply the reviewed floor/table/wall textures before World compiles its MJCF."""
    import mujoco

    surfaces = {"floor": "floor_laminate", "table": "wood_light", "wall": "wall_paint"}
    added = set()
    for geom in spec.worldbody.find_all(mujoco.mjtObj.mjOBJ_GEOM):
        name = geom.name or ""
        key = "floor" if name == "floor" else "table" if name == "table" else "wall" if name.startswith("wall") else None
        if key is None:
            continue
        mid = surfaces[key]
        if mid not in added:
            material = MATLIB[mid]
            plane = key == "floor"
            spec.add_texture(name="rxw_" + mid,
                             type=mujoco.mjtTexture.mjTEXTURE_2D if plane else mujoco.mjtTexture.mjTEXTURE_CUBE,
                             file=str(DATA / "matlib" / material["file"]))
            mat = spec.add_material(name="rxw_" + mid)
            mat.textures[int(mujoco.mjtTextureRole.mjTEXROLE_RGB)] = "rxw_" + mid
            mat.texrepeat = list(material["texrepeat"])
            mat.texuniform = plane
            mat.specular = material["specular"]
            mat.shininess = material["shininess"]
            added.add(mid)
        geom.material = "rxw_" + mid
        geom.rgba = [1, 1, 1, 1]
