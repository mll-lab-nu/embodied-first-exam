"""Presentation scenes (docs/framework_zh.md §3.1, renderer rule 6): a sport may dress its match scene for spectators,
e.g. draw its robot arms with a manufacturer-grade visual model instead of their collision meshes. A presentation
scene is the match scene plus visual-only geoms on the SAME bodies; nothing that moves or collides changes
(scene_check.same_kinematics, checked by every renderer before it draws one), so a recorded match replays and
re-renders with identical body poses. By default it is for spectator renderers only (replay videos, re-renders,
stills): the players' images use the match scene (core/observe.CameraWorker refuses a presentation scene).

Players' images (core 0.2.9): a sport may declare `players = "<meshes>"` below; then the players' images are drawn
from the presentation scene too, with the meshes named ("full" = the upstream files, or a level of detail of lod.json,
e.g. "25k": decimated, a few MB, cheap on the CPU). tools/sportlib.assemble_sim then copies this directory and the
models' files (verified by sha256, with their licences) into the simulator directory (<sim>/sport/presentation/,
assets under assets/), so they are part of source_sha and a match needs no cache or network; `players_scene` builds
that scene (Scene.players set: CameraWorker accepts it, after the same kinematics check), `players_model` compiles it
for a sport that draws its own images. Changing the declaration changes the players' images: bump the sport's
revision.

Declaration: sports/<sport>/presentation/presentation.toml (outside the simulator directory: tools/sportlib.NOT_IN_SIM,
so source_sha, the golden replays and the task directories do not change):

    [presentation]
    version = 1                                  # bump on any change of the dressing
    label = "Franka Panda visual meshes (MuJoCo Menagerie)"
    [[presentation.robot]]
    model = "franka_emika_panda"                 # a model of the asset manifest (renderers/presentation/menagerie.json),
                                                 # or "./<path>.xml": a (self-authored) model in this directory
    bodies = '^(?P<pre>[AB]_)?link(?P<n>[0-7])$' # scene bodies to dress (Python regex, full match) ...
    body = "link{n}"                             # ... and the model body whose visual geoms each one gets
    hide = "all"                                 # the dressed bodies' own geoms: "all" (default) | "mesh" | "none"
                                                 # are hidden (moved to group 3), not removed
    hide_bodies = '^...$'                        # optional: hide only in these dressed bodies (default: all of them)
    colors = { white = [0.92, 0.5, 0.42, 1] }    # optional: a model material's colour for this robot (e.g. a side colour)
    scenes = ["sim/scene/a.xml"]                 # optional: the match scene files (relative to the sport directory),
                                                 # for spectator tools when the sport has no Sport.scene()
    players = "25k"                              # optional, top level: the players' images use this scene too, with
                                                 # these meshes ("full" or a level of lod.json); absent = spectators only

The model's visual geoms (contype = conaffinity = 0, group 0..2) are copied, with their meshes, materials and poses
in the body frame, onto each matching scene body; a body whose parent is dressed too must sit in its parent's frame
exactly as the model's does (else the declaration names the wrong bodies and dressing fails). The models' files come
from the asset cache (renderers/presentation/assets.py: pinned commit, sha256 per file; `python3 -m
renderers.presentation.assets fetch`), never from the repository.

    from renderers.presentation import for_plugin
    scene = for_plugin("sports/tabletennis/plugin.py", match_scene)    # None if the sport declares no presentation
"""
from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

from ..base import Scene
from ..scene_check import VISUAL_PREFIX

DECL = "presentation.toml"
BUNDLE = "assets"                  # <sim>/sport/presentation/assets: the models' files bundled into a simulator
CLASS = "ro_presentation"          # the default class of the added geoms (inherits nothing from a robot's childclass)
HIDDEN_GROUP = "3"                 # renderers draw groups 0..2; the dressed bodies' own geoms move here
FRAME_TOL = 1e-6


class PresentationUnavailable(RuntimeError):
    """The sport declares a presentation scene that cannot be built here (e.g. the model assets are not fetched)."""


def match_scenes(sport_dir: str | os.PathLike) -> list:
    """The match scene files a presentation declares (`scenes`), as Scenes; [] if none."""
    d = Path(sport_dir) / "presentation"
    if not declared(d):
        return []
    return [Scene.from_file(Path(sport_dir) / f) for f in load_decl(d).get("scenes", [])]


def directory(plugin: str | os.PathLike) -> Path:
    return Path(plugin).resolve().parent / "presentation"


def declared(d: str | os.PathLike) -> bool:
    return (Path(d) / DECL).is_file()


def load_decl(d: str | os.PathLike) -> dict:
    import tomllib
    p = (tomllib.loads((Path(d) / DECL).read_text()).get("presentation") or {})
    if int(p.get("version", 0)) < 1 or not p.get("robot"):
        raise ValueError(f"{Path(d) / DECL}: [presentation] needs version >= 1 and at least one [[presentation.robot]]")
    for r in p["robot"]:
        for k in ("model", "bodies", "body"):
            if k not in r:
                raise ValueError(f"{Path(d) / DECL}: a [[presentation.robot]] needs {k!r}")
        if r.get("hide", "all") not in ("all", "mesh", "none"):
            raise ValueError(f"{Path(d) / DECL}: hide is all | mesh | none")
    pl = p.get("players")
    if pl is not None and (not isinstance(pl, str) or not (pl == "full" or re.fullmatch(r"\d+k", pl))):
        raise ValueError(f"{Path(d) / DECL}: players is \"full\" or a level of detail like \"25k\"")
    return p


def players_meshes(d: str | os.PathLike) -> str | None:
    """The meshes the players' images use ("full" or a level of detail), None = spectators only (the default)."""
    return load_decl(d).get("players") if declared(d) else None


def players_scene(sport_dir: str | os.PathLike, match: Scene) -> Scene:
    """The scene of the players' images: the presentation scene of `sport_dir` (the sport's directory, or the
    simulator's sport/) when it declares `players`, else `match` itself."""
    d = Path(sport_dir) / "presentation"
    meshes = players_meshes(d)
    return match if meshes is None else dress(match, d, meshes=meshes, players=True)


def players_model(sport_dir: str | os.PathLike, match: Scene):
    """For a sport that draws its own images: the compiled MjModel of the players' scene, after the same kinematics
    check against the match scene; None when the sport does not declare `players` (draw the match model)."""
    sc = players_scene(sport_dir, match)
    if sc is match:
        return None
    import mujoco as mj
    from ..scene_check import same_kinematics
    m = mj.MjSpec.from_string(sc.xml, assets=dict(sc.assets or {})).compile()
    bad = same_kinematics(mj.MjSpec.from_string(match.xml, assets=dict(match.assets or {})).compile(), m)
    if bad:
        raise RuntimeError(f"the players' presentation scene's kinematics differ from the match scene: {bad[:8]}")
    return m


def for_plugin(plugin, match: Scene) -> Scene | None:
    """The presentation scene of the sport whose plugin is `plugin`, dressing `match` (the sport's scene for the same
    configuration); None when the sport declares none. Raises PresentationUnavailable when it cannot be built. Inside a
    simulator directory (a bundle, players' presentation) it is the players' scene."""
    d = directory(plugin)
    if not declared(d):
        return None
    meshes = players_meshes(d)
    if meshes is not None and (d / BUNDLE).is_dir():    # inside a simulator: only the players' meshes are bundled
        return dress(match, d, meshes=meshes, players=True)
    return dress(match, d)


# ------------------------------------------------------------------------------------------------ robot models
def _f(v) -> str:
    return " ".join(repr(float(x)) for x in np.asarray(v, float).reshape(-1))


def _unitq(q):
    q = np.asarray(q, float)
    return q / np.linalg.norm(q)


def model_parts(xml_path: str | os.PathLike) -> dict:
    """The visual model of a robot description (parsed by MuJoCo's MJCF parser, nothing compiled or executed):
    {"bodies": {name: {"parent", "pos", "quat", "geoms": [{"mesh", "material", "rgba", "pos", "quat"}]}},
     "meshes": {name: {"file" (relative to the description's directory), "scale", "refpos", "refquat"}},
     "materials": {name: {"rgba", "specular", "shininess", "reflectance", "emission"}}}"""
    import mujoco as mj
    xml_path = Path(xml_path)
    spec = mj.MjSpec.from_file(str(xml_path))
    meshdir = spec.meshdir or ""
    meshes = {}
    for me in spec.meshes:
        if not me.file:
            raise ValueError(f"{xml_path.name}: mesh {me.name!r} has no file (only file meshes are supported)")
        name = me.name or Path(me.file).stem
        meshes[name] = {"file": os.path.normpath(os.path.join(meshdir, me.file)), "scale": list(me.scale),
                        "refpos": list(me.refpos), "refquat": list(me.refquat)}
    materials = {mt.name: {"rgba": list(mt.rgba), "specular": float(mt.specular), "shininess": float(mt.shininess),
                           "reflectance": float(mt.reflectance), "emission": float(mt.emission)}
                 for mt in spec.materials}
    bodies, used = {}, set()
    for b in spec.bodies:
        if not b.name or b.name == "world":
            continue
        if b.alt.type != mj.mjtOrientation.mjORIENTATION_QUAT:
            raise ValueError(f"{xml_path.name}: body {b.name} uses an alternative orientation")
        geoms = []
        for g in b.geoms:
            if g.type != mj.mjtGeom.mjGEOM_MESH or g.contype or g.conaffinity or not 0 <= g.group <= 2:
                continue
            if g.alt.type != mj.mjtOrientation.mjORIENTATION_QUAT:
                raise ValueError(f"{xml_path.name}: a visual geom of {b.name} uses an alternative orientation")
            geoms.append({"mesh": g.meshname, "material": g.material or None, "rgba": list(g.rgba),
                          "pos": list(g.pos), "quat": list(g.quat)})
            used.add(g.meshname)
            if g.material:
                used.add(("mat", g.material))
        bodies[b.name] = {"parent": b.parent.name if b.parent is not None else "world", "pos": list(b.pos),
                          "quat": list(b.quat), "geoms": geoms}
    return {"bodies": bodies, "meshes": {n: v for n, v in meshes.items() if n in used},
            "materials": {n: v for n, v in materials.items() if ("mat", n) in used}}


# ------------------------------------------------------------------------------------------------ dressing
def _meshdir(root) -> str:
    c = root.find("compiler")
    if c is None:
        return ""
    return c.get("meshdir") or c.get("assetdir") or ""


def _asset_key(meshdir: str, file: str) -> str:
    return os.path.normpath(os.path.join(meshdir, file)) if meshdir else file


def _local_frame(el) -> tuple:
    pos = np.array([float(x) for x in el.get("pos", "0 0 0").split()])
    if any(el.get(a) is not None for a in ("euler", "axisangle", "xyaxes", "zaxis")):
        return pos, None
    return pos, _unitq([float(x) for x in el.get("quat", "1 0 0 0").split()])


def dress(match: Scene, d: str | os.PathLike, meshes: str = "full", players: bool = False) -> Scene:
    """The presentation scene declared in directory `d` for the match scene `match` (see the module docstring), the
    models with `meshes` ("full" or a level of detail); players: the scene of the players' images (Scene.players).
    The models' files come from `d`/assets when it exists (a simulator's bundle), else from the cache / lod/."""
    from . import assets
    if match.engine != "mujoco":
        raise PresentationUnavailable(f"presentation scenes need an MJCF scene, not {match.engine!r}")
    decl = load_decl(d)
    if players and decl.get("players") is None:
        raise ValueError(f"{Path(d) / DECL}: the players' images use a presentation scene only when it declares players")
    bundled = Path(d) / BUNDLE
    bundle_root = bundled if bundled.is_dir() else None
    root = ET.fromstring(match.xml)
    meshdir = _meshdir(root)
    out_assets = dict(match.assets or {})
    asset_el = root.find("asset")
    if asset_el is None:
        asset_el = ET.Element("asset")
        root.insert(0, asset_el)
    default = root.find("default")
    if default is None:
        default = ET.Element("default")
        root.insert(0, default)
    cls = ET.SubElement(default, "default", {"class": CLASS})
    ET.SubElement(cls, "geom", {"type": "mesh", "contype": "0", "conaffinity": "0", "group": "2", "mass": "0",
                                "density": "0", "rgba": "0.5 0.5 0.5 1"})
    parents = {c: p for p in root.iter() for c in p}
    bodies = {b.get("name"): b for b in root.iter("body") if b.get("name")}
    credits, n_added, dressed_all, meshes_added = [], 0, set(), set()
    for ri, rob in enumerate(decl["robot"]):
        if rob["model"].startswith("./"):                # a model shipped in the presentation directory itself
            xml_file = (Path(d) / rob["model"]).resolve()
            if Path(d).resolve() not in xml_file.parents:
                raise ValueError(f"{DECL}: a local model must lie inside the presentation directory")
            credit = rob.get("credit", f"{rob['model']} (shipped with the sport)")
        else:
            xml_file, credit = assets.model_xml(rob["model"], meshes, bundle_root), assets.credit(rob["model"])
            if meshes != "full":
                credit += f", visual meshes decimated to level {meshes} (renderers/presentation/lod.json)"
        parts = model_parts(xml_file)
        tag = re.sub(r"[^A-Za-z0-9_]", "_", rob["model"])
        pat = re.compile(rob["bodies"])
        dressed = {}
        for name, el in bodies.items():
            mt = pat.fullmatch(name)
            if not mt:
                continue
            mbody = rob["body"].format(**{k: v or "" for k, v in mt.groupdict().items()})
            if mbody not in parts["bodies"]:
                raise ValueError(f"{DECL}: scene body {name} -> {mbody}, which {rob['model']} does not have")
            dressed[name] = mbody
        if not dressed:
            raise ValueError(f"{DECL}: no scene body matches {rob['bodies']!r}")
        if dressed.keys() & dressed_all:
            raise ValueError(f"{DECL}: bodies dressed twice: {sorted(dressed.keys() & dressed_all)}")
        dressed_all |= dressed.keys()
        for name, mbody in dressed.items():             # the declaration must name bodies in the model's frames
            par = parents.get(bodies[name])
            pname = par.get("name") if par is not None and par.tag == "body" else None
            if pname in dressed and dressed[pname] == parts["bodies"][mbody]["parent"]:
                pos, quat = _local_frame(bodies[name])
                mb = parts["bodies"][mbody]
                if quat is None or np.abs(pos - mb["pos"]).max() > FRAME_TOL or min(
                        np.abs(quat - _unitq(mb["quat"])).max(), np.abs(quat + _unitq(mb["quat"])).max()) > FRAME_TOL:
                    raise ValueError(f"{DECL}: scene body {name} does not sit in its parent's frame as "
                                     f"{rob['model']}'s {mbody} does")
        # assets: the model's meshes and materials, once per robot entry
        colors = rob.get("colors", {})
        if set(colors) - set(parts["materials"]) or any(len(v) != 4 for v in colors.values()):
            raise ValueError(f"{DECL}: colors names materials of {rob['model']} ({sorted(parts['materials'])}), "
                             "each an rgba of 4 numbers")
        for mname, mat in parts["materials"].items():
            ET.SubElement(asset_el, "material", {"name": f"ro_{tag}_{ri}_{mname}",
                                                 "rgba": _f(colors.get(mname, mat["rgba"])),
                                                 "specular": repr(mat["specular"]),
                                                 "shininess": repr(mat["shininess"]),
                                                 "reflectance": repr(mat["reflectance"]),
                                                 "emission": repr(mat["emission"])})
        for mname, me in parts["meshes"].items():          # meshes once per model, materials per robot entry
            if f"ro_{tag}_{mname}" in meshes_added:
                continue
            meshes_added.add(f"ro_{tag}_{mname}")
            rel = f"ro_presentation/{tag}/{me['file']}"
            attrs = {"name": f"ro_{tag}_{mname}", "file": rel, "scale": _f(me["scale"])}
            if np.any(np.asarray(me["refpos"]) != 0) or np.any(np.asarray(me["refquat"]) != [1, 0, 0, 0]):
                attrs.update(refpos=_f(me["refpos"]), refquat=_f(me["refquat"]))
            ET.SubElement(asset_el, "mesh", attrs)
            out_assets[_asset_key(meshdir, rel)] = (xml_file.parent / me["file"]).read_bytes()
        hide = rob.get("hide", "all")
        hide_pat = re.compile(rob["hide_bodies"]) if rob.get("hide_bodies") else None
        for name, mbody in dressed.items():
            body = bodies[name]
            if hide != "none" and (hide_pat is None or hide_pat.fullmatch(name)):
                for g in body.findall("geom"):
                    if hide == "all" or g.get("type") == "mesh" or (g.get("mesh") and g.get("type") is None):
                        g.set("group", HIDDEN_GROUP)
            kids = list(body)
            at = max([i for i, e in enumerate(kids) if e.tag in ("geom", "inertial", "joint", "freejoint")] + [-1]) + 1
            for j, g in enumerate(parts["bodies"][mbody]["geoms"]):
                attrs = {"name": f"{VISUAL_PREFIX}{name}:{j}", "class": CLASS, "mesh": f"ro_{tag}_{g['mesh']}",
                         "pos": _f(g["pos"]), "quat": _f(g["quat"])}
                if g["material"]:
                    attrs["material"] = f"ro_{tag}_{ri}_{g['material']}"
                elif not np.allclose(g["rgba"], [0.5, 0.5, 0.5, 1]):
                    attrs["rgba"] = _f(g["rgba"])
                body.insert(at + j, ET.Element("geom", attrs))
                n_added += 1
        credits.append(credit)
    xml = ET.tostring(root, encoding="unicode")
    return Scene(engine=match.engine, xml=xml, assets=out_assets, look=match.look, match=match, players=players,
                 credits=tuple(credits) + (f"{decl.get('label', 'presentation scene')} (v{decl['version']}, "
                                           f"{n_added} visual geoms" + (", the players' images" if players else "")
                                           + ")",))
