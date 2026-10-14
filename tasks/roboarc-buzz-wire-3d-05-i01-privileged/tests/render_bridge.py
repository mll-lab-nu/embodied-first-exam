"""render_bridge.py -- Nyx frames for MuJoCo states: RoboTangle's physics moves to MuJoCo, its rendering does not change.

Route A (docs/rcb/RENDER_BRIDGE.md). The frozen instance's Genesis scene, built by the same TopoGym code as the 0.2.22
runtime (same entities, generated visual assets, materials, lights, HDRI, Nyx camera rig and Nyx settings), is kept only
as Nyx's render host: it never integrates physics. Each frame, `update(mj_model, mj_data)` copies the MuJoCo joint
coordinates into the host's rigid solver (one `set_qpos`, bit for bit); Genesis forward kinematics turns them into the
same link and visual-geometry poses that Genesis physics would hold in that state, wrist cameras follow their links, and
the unchanged sensor path renders them: Nyx RGB (one shared pass for the whole rig) and Genesis raster depth.

    import render_bridge
    bridge = render_bridge.build("/path/instance.json")   # the 0.2.22 scene and rig; never stepped
    bridge.update(mj_model, mj_data)                       # MuJoCo joint coordinates -> host
    rgb = bridge.render()                                  # {camera: (H, W, 3) uint8}, Nyx
    depth = bridge.depth()                                 # {camera: (H, W) float32 m along the optical axis, 0 = none}
    meta = bridge.camera_metadata()                        # {camera: pinhole intrinsics + world pose in this state}

The MuJoCo model is matched to the host by names (see map_joints): a Genesis joint takes the MuJoCo joint of the same
name (robot `left/waist`), the entity-prefixed name (`piece_0::root_joint`), or the k-th joint of the MuJoCo body named
like its child link (`piece_0::piece_0` with an unnamed or `piece_0::root` free joint; `lead_00` with its ball joint);
`aliases` renames entities, `overrides` pins single joints.
Only the visual consequences of a state are transferred: no velocity, contact or constraint state reaches the host,
and the host's own physics state is never advanced or read back by anyone.

Deformables stream as vertices. `bind_chain("rope", model, data)` lets a MuJoCo capsule chain skin a FEM rope's mesh
(by material arc length); `bind_flex("blanket", model, data)` lets a 2D flex carry a PBD cloth's particles. Bind once,
at birth; `update()` then writes them every frame (FEM `set_pos`, PBD `set_particles_pos`), and Nyx and the depth
camera read them as they read Genesis physics today.

Process model: the host imports Genesis 1.2.1 and gs-nyx in the calling process (the image's Python 3.11). Genesis
itself imports `mujoco` (MJCF parsing), so the MuJoCo physics shares that one module; the bridge reads only `qpos`
(and `xpos`/`xquat` in check_fk), which every MuJoCo 3.x provides.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np

# Genesis gs.JOINT_TYPE -> MuJoCo mjtJoint: REVOLUTE->HINGE, PRISMATIC->SLIDE, SPHERICAL->BALL, FREE->FREE
_GS_TO_MJ_JOINT = {1: 3, 2: 2, 3: 1, 4: 0}
_MJ_QPOS_SIZE = {0: 7, 1: 4, 2: 1, 3: 1}
_GS_JOINT_NAMES = {0: "fixed", 1: "revolute", 2: "prismatic", 3: "spherical", 4: "free"}
_MJ_JOINT_NAMES = {0: "free", 1: "ball", 2: "slide", 3: "hinge"}
_SEPARATORS = ("::", "/", "_")     # <entity>::<joint> (the MuJoCo core's scene builder), <entity>/<joint>, <entity>_<joint>
DEPTH_LIMIT_M = 65.535      # the 16-bit millimetre range of the published depth (SensorSuite.depth_frame)


class MappingError(ValueError):
    """The MuJoCo model does not cover the host's moving joints (or covers them ambiguously)."""


@dataclass(frozen=True)
class JointMap:
    """host qpos[dst] = mj_data.qpos[src]; built once per MuJoCo model."""
    dst: np.ndarray
    src: np.ndarray
    pairs: tuple            # ((genesis "entity/joint", mujoco joint label, rule), ...)
    kept: tuple             # genesis joints explicitly kept at the frozen birth value
    model_nq: int

    def report(self) -> dict:
        rules: dict[str, int] = {}
        for _, _, rule in self.pairs:
            rules[rule] = rules.get(rule, 0) + 1
        return dict(joints=len(self.pairs), coordinates=int(self.dst.size), model_nq=self.model_nq,
                    rules=rules, kept=list(self.kept))


@dataclass(frozen=True)
class BridgeFrame:
    rgb: Mapping[str, np.ndarray]
    camera_metadata: Mapping[str, Any]
    depth: Mapping[str, np.ndarray] = field(default_factory=dict)


def _mj_names(mj_model, kind: str, count: int) -> list:
    import mujoco
    obj = getattr(mujoco.mjtObj, kind)
    return [mujoco.mj_id2name(mj_model, obj, i) for i in range(count)]


def _rigid_entities(env) -> list:
    solver = env._world.scene.sim.rigid_solver
    return [(name, entity) for name, entity in env._world.entities.items()
            if getattr(entity, "_solver", None) is solver and getattr(entity, "n_qs", 0)]


def _body_candidates(prefix: str, entity, link) -> list[str]:
    """MuJoCo body names that may carry a Genesis link: prefixed first, then the bare link name, then (base link) the
    entity's own name."""
    return ([f"{prefix}{sep}{link.name}" for sep in _SEPARATORS] + [link.name]
            + ([prefix] if link.idx == entity.base_link_idx else []))


def nyx_inputs(world) -> dict[str, np.ndarray]:
    """What the last Nyx pass read: the rigid visual-geometry poses and the camera poses it uploaded (Genesis Z-up,
    wxyz, float32), plus deformable vertices when a scene has them."""
    renderer = None
    for camera in world.cameras.values():
        sensor = getattr(camera, "sensor", None)
        if sensor is not None:
            renderer = sensor._shared_metadata.renderer
            break
    if renderer is None:
        return {}
    out = dict(geom_pos=renderer._geom_pos_tensor_cuda, geom_quat=renderer._geom_rot_tensor_cuda)
    if renderer._cam_pos_tensor_cuda is not None:
        out.update(cam_pos=renderer._cam_pos_tensor_cuda, cam_quat=renderer._cam_rot_tensor_cuda)
    if renderer._num_deform_verts:
        out["deform_verts"] = renderer._deformable_verts_cuda
    return {k: v.detach().cpu().numpy().copy() for k, v in out.items()}


def map_joints(env, mj_model, *, aliases: Mapping[str, str] | None = None,
               overrides: Mapping[str, str] | None = None, keep: Iterable[str] = ()) -> JointMap:
    """Match every moving joint of the host to one MuJoCo joint of the same type and size.

    Rules, in order: `overrides["<entity>/<joint>"] = "<mujoco joint>"`; the MuJoCo joint `<prefix>::<joint>`,
    `<prefix>/<joint>` or `<prefix>_<joint>` (prefix = aliases.get(entity, entity)); the bare joint name when it is
    unique among the host's joints; the k-th joint of the MuJoCo body named `<prefix>::<link>`, `<prefix>/<link>`,
    `<prefix>_<link>`, `<link>` or, for a base link, `<prefix>` (MuJoCo's world body never matches).
    `keep` lists `<entity>/<joint>` left at the frozen birth value (they are reported). Anything else unmatched,
    a type/size mismatch or a MuJoCo joint claimed twice raises MappingError.
    """
    aliases, overrides, keep = dict(aliases or {}), dict(overrides or {}), set(keep)
    jnames = _mj_names(mj_model, "mjOBJ_JOINT", mj_model.njnt)
    bnames = _mj_names(mj_model, "mjOBJ_BODY", mj_model.nbody)
    joint_id = {n: i for i, n in enumerate(jnames) if n}
    body_id = {n: i for i, n in enumerate(bnames) if n}
    entities = _rigid_entities(env)
    bare_count: dict[str, int] = {}
    for _, entity in entities:
        for joint in entity.joints:
            if len(joint.qs_idx_local):
                bare_count[joint.name] = bare_count.get(joint.name, 0) + 1
    dst, src, pairs, kept, problems, claimed = [], [], [], [], [], {}
    for ename, entity in entities:
        prefix = aliases.get(ename, ename)
        seen_on_link: dict[str, int] = {}
        for joint in entity.joints:
            qs = [int(i) for i in joint.qs_idx_local]
            if not qs:
                continue
            key = f"{ename}/{joint.name}"
            link = joint.link
            k = seen_on_link.get(link.name, 0)
            seen_on_link[link.name] = k + 1
            gtype = int(joint.type)
            want = _GS_TO_MJ_JOINT.get(gtype)
            jid, rule = None, None
            if key in overrides:
                jid, rule = joint_id.get(overrides[key]), "override"
                if jid is None:
                    problems.append(f"{key}: override {overrides[key]!r} is not a MuJoCo joint")
                    continue
            else:
                names = [f"{prefix}{sep}{joint.name}" for sep in _SEPARATORS]
                for cand, why in [(n, "prefixed name") for n in names] + [
                        (joint.name if bare_count.get(joint.name) == 1 else None, "name")]:
                    if cand is not None and cand in joint_id and int(mj_model.jnt_type[joint_id[cand]]) == want:
                        jid, rule = joint_id[cand], why
                        break
                if jid is None:
                    for bname in _body_candidates(prefix, entity, link):
                        b = body_id.get(bname)
                        if not b:       # absent, or MuJoCo's world body (a Genesis link may be called "world")
                            continue
                        start, count = int(mj_model.body_jntadr[b]), int(mj_model.body_jntnum[b])
                        if 0 <= start and k < count:
                            jid, rule = start + k, "body"
                            break
            if jid is None:
                if key in keep:
                    kept.append(key)
                else:
                    problems.append(f"{key} ({_GS_JOINT_NAMES.get(gtype, gtype)}): no MuJoCo joint")
                continue
            mtype = int(mj_model.jnt_type[jid])
            label = jnames[jid] or f"#{jid} (body {bnames[int(mj_model.jnt_bodyid[jid])]})"
            if mtype != want or _MJ_QPOS_SIZE[mtype] != len(qs):
                problems.append(f"{key} ({_GS_JOINT_NAMES.get(gtype, gtype)}, {len(qs)} q) -> {label} "
                                f"({_MJ_JOINT_NAMES.get(mtype, mtype)}): type or size differs")
                continue
            if jid in claimed:
                problems.append(f"{key} -> {label}: already used by {claimed[jid]}")
                continue
            claimed[jid] = key
            adr = int(mj_model.jnt_qposadr[jid])
            dst.extend(int(entity.q_start) + q for q in qs)
            src.extend(range(adr, adr + len(qs)))
            pairs.append((key, label, rule))
    if problems:
        raise MappingError("MuJoCo model does not match the render host:\n  " + "\n  ".join(problems))
    return JointMap(np.asarray(dst, dtype=np.int64), np.asarray(src, dtype=np.int64), tuple(pairs), tuple(kept),
                    int(mj_model.nq))


class ChainSkin:
    """A FEM rope's vertices driven by an ordered chain of MuJoCo bodies (linear-blend skinning keyed on material arc
    length). A vertex at material s blends the two links whose centres bracket s (only the end link beyond the first
    or last centre); each link carries the vertex's birth offset in its own frame, so at birth the skin reproduces the
    vertices exactly. Material s, not distance, picks the links: a knot's crossing strands never borrow each other."""

    def __init__(self, bodies, rest, material_s, link_s, pos, rot):
        self.bodies = np.asarray(bodies, dtype=np.int64)
        n = len(self.bodies)
        centres = 0.5 * (link_s[:-1] + link_s[1:])
        hi = np.clip(np.searchsorted(centres, material_s), 1, max(n - 1, 1)) if n > 1 else np.zeros(len(rest), int)
        lo = hi - 1 if n > 1 else hi
        span = np.where(hi > lo, centres[hi] - centres[lo], 1.0)
        self.lo, self.hi = lo, hi
        self.t = np.clip((material_s - centres[lo]) / span, 0.0, 1.0)[:, None]
        self.local_lo = np.einsum("nji,nj->ni", rot[lo], rest - pos[lo])      # R^T (v - p) at birth
        self.local_hi = np.einsum("nji,nj->ni", rot[hi], rest - pos[hi])

    def __call__(self, xpos, xmat) -> np.ndarray:
        pos = np.asarray(xpos)[self.bodies]
        rot = np.asarray(xmat)[self.bodies].reshape(-1, 3, 3)
        a = np.einsum("nij,nj->ni", rot[self.lo], self.local_lo) + pos[self.lo]
        b = np.einsum("nij,nj->ni", rot[self.hi], self.local_hi) + pos[self.hi]
        return a + self.t * (b - a)


class SurfaceSkin:
    """Points carried by a triangle surface: each point is bound (birth) to its nearest triangle by the barycentric
    weights of the nearest point plus its offset from it in the triangle's own frame. Exact at birth; a surface whose
    vertices are the points carries them vertex for vertex."""

    def __init__(self, points, vertices, faces):
        import trimesh
        used = np.unique(faces)
        local = np.searchsorted(used, faces)
        surface = trimesh.Trimesh(vertices=vertices[used], faces=local, process=False)
        closest, _, tri = trimesh.proximity.closest_point(surface, points)
        self.corners = faces[tri]
        self.weights = trimesh.triangles.points_to_barycentric(vertices[self.corners], closest)
        self.offset = np.einsum("nij,ni->nj", _triangle_frames(vertices, self.corners), points - closest)

    def __call__(self, vertices) -> np.ndarray:
        v = np.asarray(vertices)
        p = np.einsum("nk,nki->ni", self.weights, v[self.corners])
        return p if not self.offset.any() else p + np.einsum("nij,nj->ni", _triangle_frames(v, self.corners), self.offset)


class RenderBridge:
    """A built, never-stepped TopoGym/Genesis scene used only to render states with Nyx (see module doc)."""

    def __init__(self, env, *, instance: dict | None = None, instance_path: Path | None = None,
                 aliases: Mapping[str, str] | None = None, overrides: Mapping[str, str] | None = None,
                 keep: Iterable[str] = ()):
        import torch
        import genesis as gs
        self.env = env
        self.world = env._world
        self.scene = self.world.scene
        self.solver = self.scene.sim.rigid_solver
        self.instance, self.instance_path = instance, instance_path
        self.aliases, self.overrides, self.keep = dict(aliases or {}), dict(overrides or {}), tuple(keep)
        self._torch, self._gs = torch, gs
        self.q_birth = self._read_qpos()
        self._q = self.q_birth.copy()
        self._map: JointMap | None = None
        self._map_model = None
        self._rgb: dict | None = None
        self._meta: dict | None = None
        self._depth: dict | None = None
        self._deformables: dict = {}          # entity name -> (entity, kind "fem" | "pbd", vertex function of mj_data)
        self._bodies: dict = {}               # host entity -> (its free joint's q indices, MuJoCo body, birth offset)
        self.chain_cord: dict | None = None   # a FEM cord shown on a MuJoCo chain (build(): cord_model "chain")
        self.timing = dict(update_s=0.0, render_s=0.0, depth_s=0.0, updates=0, renders=0, depths=0)

    # ------------------------------------------------------------------ state in
    @property
    def cameras(self) -> tuple[str, ...]:
        return tuple(self.world.cameras)

    @property
    def nq(self) -> int:
        return int(self.solver.n_qs)

    def _read_qpos(self) -> np.ndarray:
        from topogym.utils.arrays import to_numpy
        return np.array(to_numpy(self.solver.get_qpos()), dtype=np.float64).reshape(-1)

    def qpos(self) -> np.ndarray:
        """The host's current joint coordinates (Genesis solver order)."""
        return self._read_qpos()

    def bind(self, mj_model) -> JointMap:
        """Build (and keep) the joint map for this MuJoCo model; update() calls it on first use."""
        self._map = map_joints(self.env, mj_model, aliases=self.aliases, overrides=self.overrides, keep=self.keep)
        self._map_model = mj_model
        if self.chain_cord is not None:
            # The FEM host's cord and rigid parts are bound at the chain's authored pose (the model's qpos0), which is
            # where the host shows them: the chain and the parts are laid along the same authored cord.
            import mujoco
            birth = mujoco.MjData(mj_model)
            mujoco.mj_forward(mj_model, birth)
            spec = self.chain_cord
            self.chain_cord_report = dict(
                bodies={host: self.bind_body(host, mj_model, birth, body) for host, body in spec["bodies"].items()},
                cord=self.bind_chain(spec["entity"], mj_model, birth, bodies=spec["chain"], link_s=spec["link_s_m"]))
        return self._map

    def update(self, mj_model, mj_data) -> None:
        """Copy MuJoCo's joint coordinates into the host; the next render/depth shows this state."""
        t = time.perf_counter()
        joint_map = self._map if self._map_model is mj_model else self.bind(mj_model)
        if int(mj_model.nq) != joint_map.model_nq:
            raise MappingError("MuJoCo model changed size since bind()")
        self._q[joint_map.dst] = np.asarray(mj_data.qpos, dtype=np.float64)[joint_map.src]
        for qs, body, offset_p, offset_r in self._bodies.values():
            r = _quat_matrix(mj_data.xquat[body])
            self._q[qs[:3]] = np.asarray(mj_data.xpos[body]) + r @ offset_p
            self._q[qs[3:]] = _matrix_quat(r @ offset_r)
        self._push(self._q)                   # also marks the visual clocks stale for the deformables written next
        for entity, kind, vertices in self._deformables.values():
            self._write_vertices(entity, kind, vertices(mj_data))
        self.timing["update_s"] += time.perf_counter() - t
        self.timing["updates"] += 1

    # ------------------------------------------------------------------ deformables
    def bind_chain(self, entity: str, mj_model, mj_data, bodies=None, link_s=None) -> dict:
        """Let MuJoCo body chain `bodies` (ids or names, rope order; default: the bodies named `<entity>::*` or
        `<entity>/*` in id order) drive the FEM entity `entity` (its visual mesh: same vertices, same triangles). Call
        once, with mj_data in the shape the host shows now (birth). `link_s`: material arc length at the start of every
        link and the end of the last (default: the entity's material range in equal parts, checked against the chain)."""
        from topogym.world.physics.fem import read_vertices
        e = self.world.entities[entity]
        ids = _chain_bodies(mj_model, entity, bodies)
        rest = np.asarray(read_vertices(e)["position_m"], dtype=np.float64)
        material_s = np.asarray(e.material_coordinates[:, 0], dtype=np.float64)
        pos = np.asarray(mj_data.xpos, dtype=np.float64)[ids]
        rot = np.asarray(mj_data.xmat, dtype=np.float64)[ids].reshape(-1, 3, 3)
        if link_s is None:
            link_s = np.linspace(material_s.min(), material_s.max(), len(ids) + 1)
            joints = np.linalg.norm(np.diff(pos, axis=0), axis=1)
            if len(ids) > 1 and np.abs(joints - np.diff(link_s)[:-1]).max() > 0.05 * np.diff(link_s).max():
                raise MappingError(f"{entity}: chain links are not equal material spans; pass link_s")
        link_s = np.asarray(link_s, dtype=np.float64)
        if link_s.shape != (len(ids) + 1,) or np.any(np.diff(link_s) <= 0):
            raise MappingError(f"{entity}: link_s needs {len(ids) + 1} increasing values")
        skin = ChainSkin(ids, rest, material_s, link_s, pos, rot)
        self._deformables[entity] = (e, "fem", lambda data, skin=skin: skin(data.xpos, data.xmat))
        error = np.linalg.norm(skin(mj_data.xpos, mj_data.xmat) - rest, axis=1).max()
        return dict(entity=entity, kind="fem chain skin", vertices=len(rest), links=len(ids),
                    birth_max_error_m=float(error))

    def bind_body(self, entity: str, mj_model, mj_data, body) -> dict:
        """Let MuJoCo body `body` (name or id) carry the host's free rigid entity `entity` (its free root joint, which
        map_joints leaves to it: list it in `keep`). Call once, with mj_data in the pose the host shows now (birth): the
        body's frame and the host link's may differ (a URDF part authored in the assembly frame, the same part as a body
        of an MJCF chain file), so the birth offset between them is kept: host pose = body pose * offset."""
        import mujoco
        e = self.world.entities[entity]
        free = [j for j in e.joints if int(j.type) == 4]
        if len(free) != 1 or e.n_qs != 7:
            raise MappingError(f"{entity}: bind_body needs a single free rigid body")
        b = body if isinstance(body, (int, np.integer)) else mujoco.mj_name2id(mj_model, mujoco.mjtObj.mjOBJ_BODY, body)
        if b <= 0:
            raise MappingError(f"{entity}: no MuJoCo body {body!r}")
        qs = int(e.q_start) + np.asarray(free[0].qs_idx_local, dtype=np.int64)
        p, r = np.asarray(mj_data.xpos[b], dtype=np.float64), _quat_matrix(mj_data.xquat[b])
        host_p, host_r = self.q_birth[qs[:3]], _quat_matrix(self.q_birth[qs[3:]])
        self._bodies[entity] = (qs, int(b), r.T @ (host_p - p), r.T @ host_r)
        return dict(body=mujoco.mj_id2name(mj_model, mujoco.mjtObj.mjOBJ_BODY, int(b)),
                    offset_m=float(np.linalg.norm(host_p - p)))

    def bind_flex(self, entity: str, mj_model, mj_data, flex=None) -> dict:
        """Let a MuJoCo 2D flex (name or id; default: the one named `entity`, else the only one) drive the PBD cloth
        `entity`. Every particle is bound now (birth) to the flex triangle nearest to it: barycentric weights of the
        nearest point plus the particle's offset from it in the triangle's own frame, so the binding reproduces the
        birth particles exactly, a flex built on the particles carries them vertex for vertex and a coarser flex carries
        them on its surface. The report gives the largest offset."""
        import mujoco
        e = self.world.entities[entity]
        if isinstance(flex, str) or flex is None:
            fid = mujoco.mj_name2id(mj_model, mujoco.mjtObj.mjOBJ_FLEX, flex or entity)
            flex = 0 if fid < 0 and flex is None and mj_model.nflex == 1 else fid
        if not 0 <= flex < mj_model.nflex or int(mj_model.flex_dim[flex]) != 2:
            raise MappingError(f"{entity}: no 2D MuJoCo flex to drive it")
        adr, num = int(mj_model.flex_vertadr[flex]), int(mj_model.flex_vertnum[flex])
        start, count = int(mj_model.flex_elemdataadr[flex]), int(mj_model.flex_elemnum[flex])
        faces = np.asarray(mj_model.flex_elem[start:start + 3 * count]).reshape(-1, 3) + adr
        particles = np.asarray(e.get_particles_pos().cpu().numpy(), dtype=np.float64).reshape(-1, 3)
        skin = SurfaceSkin(particles, np.asarray(mj_data.flexvert_xpos, dtype=np.float64), faces)
        self._deformables[entity] = (e, "pbd", lambda data, skin=skin: skin(data.flexvert_xpos))
        error = np.linalg.norm(skin(mj_data.flexvert_xpos) - particles, axis=1).max()
        return dict(entity=entity, kind="pbd particles on a flex", particles=len(particles), flex_vertices=num,
                    flex_triangles=count, birth_max_error_m=float(error),
                    max_offset_m=float(np.linalg.norm(skin.offset, axis=1).max()))

    def _write_vertices(self, entity, kind, vertices) -> None:
        v = np.asarray(vertices, dtype=np.float64)
        if not np.isfinite(v).all():
            raise FloatingPointError("non-finite deformable vertices")
        tensor = self._torch.as_tensor(v, dtype=self._gs.tc_float, device=self._gs.device)
        if kind == "fem":
            entity.set_pos(int(self.scene.sim.cur_substep_local), tensor[None])
        else:
            entity.set_particles_pos(tensor)

    def set_qpos(self, qpos) -> None:
        """Write a complete host qpos (Genesis solver order), e.g. from another engine or a Genesis record."""
        q = np.asarray(qpos, dtype=np.float64).reshape(-1)
        if q.size != self.nq:
            raise ValueError(f"host qpos has {self.nq} entries, got {q.size}")
        self._q = q.copy()
        self._push(self._q)

    def _push(self, q: np.ndarray) -> None:
        if not np.isfinite(q).all():
            raise FloatingPointError("non-finite joint coordinates")
        self.solver.set_qpos(self._torch.as_tensor(q, dtype=self._gs.tc_float, device=self._gs.device))
        self._invalidate()

    def _invalidate(self) -> None:
        # The host's clock never advances, so mark everything that Genesis keys on scene.t as outdated, exactly as a
        # tick or scene.reset() does: the visual geometry (Nyx path) and the raster context (depth path) refresh lazily
        # from the new forward kinematics; every Nyx camera of the shared pass and the observation cache re-render.
        visualizer = self.scene.visualizer
        visualizer._t = -1
        context = getattr(visualizer, "_context", None)
        if context is not None:
            context._t = -1
        for camera in self.world.cameras.values():
            invalidate = getattr(camera, "invalidate_frame", None)
            if invalidate is not None:
                invalidate()
        sensors = getattr(self.env, "_sensors", None)
        if sensors is not None:
            sensors.invalidate()
        self._rgb = self._meta = self._depth = None

    # ------------------------------------------------------------------ frames out
    def _names(self, cameras) -> list[str]:
        names = list(self.cameras) if cameras is None else [cameras] if isinstance(cameras, str) else list(cameras)
        unknown = [n for n in names if n not in self.world.cameras]
        if unknown:
            raise KeyError(f"unknown camera(s) {unknown}; cameras: {list(self.cameras)}")
        return names

    def render(self, cameras=None, *, force: bool = False) -> dict[str, np.ndarray]:
        """RGB (H, W, 3) uint8 per camera, the 0.2.22 Nyx path (SensorSuite.sample): one shared pass renders the rig."""
        from topogym.sensors.camera_info import pinhole_intrinsics, pose_metadata
        from topogym.sensors.cameras import update_dynamic_camera
        if self._rgb is None or force:
            t = time.perf_counter()
            for camera in self.world.cameras.values():
                invalidate = getattr(camera, "invalidate_frame", None)
                if invalidate is not None:
                    invalidate()
            rgb, meta = {}, {}
            for name, camera in self.world.cameras.items():
                update_dynamic_camera(camera)
                output = camera.render(rgb=True)
                pixels = output[0] if isinstance(output, (tuple, list)) else output
                if hasattr(pixels, "detach"):
                    pixels = pixels.detach().cpu().numpy()
                pixels = np.array(pixels, copy=True)
                if pixels.dtype != np.uint8 or pixels.ndim != 3 or pixels.shape[2] != 3:
                    raise ValueError(f"Camera {name} must produce HxWx3 uint8 RGB")
                rgb[name] = pixels
                meta[name] = dict(**pinhole_intrinsics(camera.res, camera.fov), **pose_metadata(camera.transform))
            self._rgb, self._meta = rgb, meta
            self.timing["render_s"] += time.perf_counter() - t
            self.timing["renders"] += 1
        return {n: self._rgb[n] for n in self._names(cameras)}

    def camera_metadata(self, cameras=None) -> dict[str, dict]:
        """Pinhole intrinsics and world pose of each camera in the current state (as SensorFrame.camera_metadata)."""
        if self._meta is None:
            from topogym.sensors.camera_info import pinhole_intrinsics, pose_metadata
            from topogym.sensors.cameras import update_dynamic_camera
            meta = {}
            for name, camera in self.world.cameras.items():
                update_dynamic_camera(camera)
                meta[name] = dict(**pinhole_intrinsics(camera.res, camera.fov), **pose_metadata(camera.transform))
            self._meta = meta
        return {n: self._meta[n] for n in self._names(cameras)}

    def depth(self, cameras=None) -> dict[str, np.ndarray]:
        """z-depth (H, W) float32 metres per camera: Genesis raster depth at the Nyx rig (SensorSuite.depth_frame)."""
        if self._depth is None:
            t = time.perf_counter()
            depths = {}
            for name, camera in self.world.cameras.items():
                output = camera.render(rgb=False, depth=True)
                value = output[1]
                if hasattr(value, "detach"):
                    value = value.detach().cpu().numpy()
                value = np.asarray(value, dtype=np.float32).copy()
                if value.ndim == 3:
                    value = value[..., 0]
                value[~np.isfinite(value) | (value <= 0) | (value > min(float(camera.far), DEPTH_LIMIT_M))] = 0
                depths[name] = value
            self._depth = depths
            self.timing["depth_s"] += time.perf_counter() - t
            self.timing["depths"] += 1
        return {n: self._depth[n] for n in self._names(cameras)}

    def frame(self, *, depth: bool = False, cameras=None) -> BridgeFrame:
        rgb = self.render(cameras)
        return BridgeFrame(rgb=rgb, camera_metadata=self.camera_metadata(cameras),
                           depth=self.depth(cameras) if depth else {})

    def nyx_inputs(self) -> dict[str, np.ndarray]:
        return nyx_inputs(self.world)

    # ------------------------------------------------------------------ checks
    def check_fk(self, mj_model, mj_data, *, links: Iterable[str] | None = None) -> dict:
        """Host link world poses vs MuJoCo body poses (bodies named like the links, alias prefixes allowed); call after
        update() and mj_forward/mj_kinematics. A frame-convention or mapping error shows up here, not in pixels."""
        import mujoco
        from topogym.utils.arrays import to_numpy
        pos = np.asarray(to_numpy(self.solver.get_links_pos()), dtype=np.float64).reshape(-1, 3)
        quat = np.asarray(to_numpy(self.solver.get_links_quat()), dtype=np.float64).reshape(-1, 4)
        wanted = None if links is None else set(links)
        worst_p, worst_r, worst_link, rows = 0.0, 0.0, None, 0
        for ename, entity in self.world.entities.items():
            if getattr(entity, "_solver", None) is not self.solver:
                continue
            prefix = self.aliases.get(ename, ename)
            for link in entity.links:
                if wanted is not None and f"{ename}/{link.name}" not in wanted:
                    continue
                b = next((i for i in (mujoco.mj_name2id(mj_model, mujoco.mjtObj.mjOBJ_BODY, c)
                                      for c in _body_candidates(prefix, entity, link)) if i > 0), 0)
                if not b:
                    continue
                dp = float(np.linalg.norm(pos[link.idx] - np.asarray(mj_data.xpos[b])))
                q1, q2 = quat[link.idx], np.asarray(mj_data.xquat[b], dtype=np.float64)
                # angle of q1^-1 q2, well conditioned near zero: 2 atan2(|vector part|, |scalar part|)
                w = q1[0] * q2[0] + q1[1:] @ q2[1:]
                v = q1[0] * q2[1:] - q2[0] * q1[1:] - np.cross(q1[1:], q2[1:])
                dr = float(2 * np.arctan2(np.linalg.norm(v), abs(w)))
                rows += 1
                if dp > worst_p or dr > worst_r:
                    worst_link = f"{ename}/{link.name}"
                worst_p, worst_r = max(worst_p, dp), max(worst_r, dr)
        return dict(links_compared=rows, max_position_error_m=worst_p, max_rotation_error_rad=worst_r,
                    worst_link=worst_link)

    def close(self) -> None:
        if self.env is not None:
            self.env.close()
            self.env = None


def _quat_matrix(q) -> np.ndarray:
    """Rotation matrix of a wxyz quaternion (MuJoCo and Genesis order)."""
    from scipy.spatial.transform import Rotation
    q = np.asarray(q, dtype=np.float64)
    return Rotation.from_quat(q[[1, 2, 3, 0]]).as_matrix()


def _matrix_quat(r) -> np.ndarray:
    from scipy.spatial.transform import Rotation
    return Rotation.from_matrix(r).as_quat()[[3, 0, 1, 2]]


def _triangle_frames(vertices, corners) -> np.ndarray:
    """(n, 3, 3) orthonormal frames, columns = first edge, in-plane normal to it, triangle normal."""
    a, b, c = (vertices[corners[:, k]] for k in range(3))
    e1 = b - a
    e1 /= np.maximum(np.linalg.norm(e1, axis=1, keepdims=True), 1e-300)
    n = np.cross(b - a, c - a)
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-300)
    return np.stack([e1, np.cross(n, e1), n], axis=2)


def _chain_bodies(mj_model, entity: str, bodies) -> list[int]:
    import mujoco
    if bodies is None:
        names = _mj_names(mj_model, "mjOBJ_BODY", mj_model.nbody)
        ids = [i for i, n in enumerate(names) if n and n.split("::", 1)[0].split("/", 1)[0] == entity]
    else:
        ids = [b if isinstance(b, (int, np.integer)) else mujoco.mj_name2id(mj_model, mujoco.mjtObj.mjOBJ_BODY, b)
               for b in bodies]
    if not ids or min(ids) <= 0:
        raise MappingError(f"{entity}: no MuJoCo body chain found")
    return [int(i) for i in ids]


def _resolve_config(path: Path, inst: dict) -> dict:
    """The frozen simulator configuration, with instance-relative dependencies resolved (as rcb_topogym.Session)."""
    cfg = dict(inst["simulator"])
    cfg["task_parameters"] = dict(cfg.get("task_parameters", {}))
    dependency = cfg["task_parameters"].get("initial_state_path")
    if dependency and not Path(dependency).is_absolute():
        cfg["task_parameters"]["initial_state_path"] = str(path.parent / dependency)
    settled = cfg.get("ipc_settled_state")
    if settled and not Path(settled).is_absolute():
        cfg["ipc_settled_state"] = str(path.parent / settled)
    return cfg


def _chain_cord_host(cfg: dict) -> tuple[dict, dict]:
    """A FEM setting whose cord is a MuJoCo chain (slotted_post_ring and orbits on MuJoCo: task parameter cord_model
    "chain") is rendered as the FEM setting it is: the host is its FEM+IPC scene, never stepped and born in the authored
    shape; the cord's vertices follow the chain's links (bind_chain) and its free rigid parts the MuJoCo bodies that
    carry them (bind_body). Returns (the task's render_host_binding, the host's simulator configuration: the family's
    IPC settings, CUDA, no settling)."""
    import tempfile
    from topogym.config.registry import task_definition
    from topogym.config.scene import load_scene_config
    from topogym.simulator.config import SimulatorConfig
    task = task_definition(cfg["task_id"], cfg["variation_id"])(dict(cfg["task_parameters"]), seed=int(cfg["seed"]))
    table = load_scene_config(SimulatorConfig(**cfg)).env.world.table
    with tempfile.TemporaryDirectory() as tmp:
        task.declare(Path(tmp), float(table.pos[2] + table.size[2] / 2))
    binding = task.render_host_binding()
    family = _task_tooling().TASKS[cfg["task_id"]]["simulator"]
    host = {k: v for k, v in cfg.items() if k not in ("physics_engine", "mujoco_scene", "mujoco_settled_state")}
    host.update(task_parameters={**cfg["task_parameters"], "cord_model": "fem"}, compute_backend="cuda", precision="64",
                solver_substeps=int(family["solver_substeps"]), ipc_options=dict(family["ipc_options"]), rigid_options={},
                reset_physics_steps=0)
    return binding, host


def asset_identity(env) -> dict[str, str]:
    """sha256 of every generated asset, temporary root normalized (identical to rcb_topogym.Session._asset_identity)."""
    build = env._asset_build
    root = str(build.root.resolve()).encode()
    return {name: hashlib.sha256((build.root / name).read_bytes().replace(root, b"<instance-assets>")).hexdigest()
            for name in sorted(build.files)}


def build(frozen_instance, *, aliases: Mapping[str, str] | None = None, overrides: Mapping[str, str] | None = None,
          keep: Iterable[str] = (), require_assets: bool = True) -> RenderBridge:
    """Build the render host for a frozen instance (path to instance.json): the 0.2.22 TopoGym Env construction
    (Env(SimulatorConfig(**instance["simulator"])).reset(seed)) with RGB deferred, so nothing renders and no physics
    step runs. `require_assets` checks the generated visual assets against the instance's asset_identity."""
    path = Path(frozen_instance).resolve()
    inst = json.loads(path.read_text())
    cfg = _resolve_config(path, inst)
    chain_cord = None
    if cfg["task_parameters"].get("cord_model") == "chain":
        chain_cord, cfg = _chain_cord_host(cfg)
        require_assets = False                   # the host is the FEM scene; the instance froze the chain scene's
    if cfg.get("ipc_settled_state") or chain_cord is not None:
        _task_tooling().uipc_build_in_use()      # the libuipc build of this GPU, chosen before uipc is imported
    if (path.parent / "runtime_binding.json").is_file():
        # As rcb_topogym.Session does for a bound instance: the frozen generated assets (IPC rope volumes) replace the
        # regenerated ones, and the stored IPC / PBD birth states accept this host's asset bytes.
        tooling = _task_tooling()
        tooling._accept_realized_identities()
        tooling._install_frozen_assets(path.parent, inst.get("asset_identity") or {})
    if not cfg.get("enable_rgb", True):
        raise ValueError("this instance has no RGB rig to render")
    t0 = time.perf_counter()
    if cfg.get("compute_backend") == "cpu":
        import torch
        # Genesis' CPU getters are torch CPU ops; an uncapped pool spins under a container quota (as the Session).
        if torch.get_num_threads() > 4:
            torch.set_num_threads(4)
    from topogym.simulator.config import SimulatorConfig
    from topogym.simulator.env import Env
    for key in ("physics_engine", "mujoco_scene", "mujoco_settled_state"):   # the MuJoCo core's switches: the host is the Genesis scene
        cfg.pop(key, None)
    env = Env(SimulatorConfig(**cfg))
    env.defer_rgb = True
    # Env.reset reseeds the process RNGs and registers itself as the process's one Env. The host never steps, so it
    # leaves both as it found them: the physics Env (MuJoCo) stays the active one and its random streams are untouched.
    active, rngs = Env._active_env, _rng_states()
    Env._active_env = None
    try:
        env.reset(seed=int(cfg["seed"]))
        if chain_cord is not None:          # the parts carried by bind_body keep their joints out of the joint map
            keep = tuple(keep) + tuple(f"{name}/{j.name}" for name in chain_cord["bodies"]
                                       for j in env._world.entities[name].joints if len(j.qs_idx_local))
        bridge = RenderBridge(env, instance=inst, instance_path=path, aliases=aliases, overrides=overrides, keep=keep)
        bridge.chain_cord = chain_cord
        bridge.build_s = time.perf_counter() - t0
        bridge.asset_identity = asset_identity(env)
        expected = inst.get("asset_identity") or {}
        bridge.asset_differences = sorted(n for n in set(expected) | set(bridge.asset_identity)
                                          if expected.get(n) != bridge.asset_identity.get(n))
        if require_assets and expected and bridge.asset_differences:
            raise RuntimeError("render host assets differ from the frozen instance: "
                               + ", ".join(bridge.asset_differences[:8]))
    except BaseException:
        env.close()
        raise
    finally:
        Env._active_env = active
        _set_rng_states(rngs)
    return bridge


def _task_tooling():
    """rcb_topogym, the task tooling shipped next to this file (libuipc build rule, frozen generated assets)."""
    import sys
    here = str(Path(__file__).resolve().parent)
    if here not in sys.path:
        sys.path.insert(0, here)
    import rcb_topogym
    return rcb_topogym


def _rng_states():
    import random
    import torch
    return (random.getstate(), np.random.get_state(), torch.get_rng_state(),
            torch.cuda.get_rng_state_all() if torch.cuda.is_available() else None)


def _set_rng_states(states) -> None:
    import random
    import torch
    python, numpy_state, torch_cpu, torch_cuda = states
    random.setstate(python)
    np.random.set_state(numpy_state)
    torch.set_rng_state(torch_cpu)
    if torch_cuda is not None:
        torch.cuda.set_rng_state_all(torch_cuda)


# ---------------------------------------------------------------------- rendering off
class _HeadlessCamera:
    """One camera of the rig without pixels: the calibration the sensor path reads (res, fov, near, far, and transform,
    camera -> world in OpenGL axes, as the Genesis camera holds it) and frames that are black (RGB) or have no reading
    (depth 0). A wrist camera follows its MuJoCo body as Genesis' Camera.move_to_attach does: link pose @ offset_T."""

    def __init__(self, rig, config: Mapping, body_names: tuple = ()):
        from topogym.sensors.camera_info import optical_transform
        self._rig, self._body_names, self._body, self._offset = rig, tuple(body_names), None, None
        self.res = (int(config["res"][0]), int(config["res"][1]))
        self.fov, self.near, self.far = float(config["fov"]), float(config.get("near", 0.1)), float(config.get("far", 20.0))
        self.transform = optical_transform(config["pos"], config["lookat"], config.get("up", [0, 0, 1]))
        attach = config.get("attach") or {}
        if attach.get("enabled", True) and attach:
            offset = attach.get("offset_T")
            self._offset = np.asarray(offset if offset is not None else optical_transform(
                attach.get("offset_pos", [0, 0, 0]), attach.get("offset_lookat", [0.1, 0, 0]),
                attach.get("offset_up", [0, 0, 1])), dtype=np.float64)

    @property
    def _attached_link(self):           # update_dynamic_camera() moves a camera that has one
        return self._body_names if self._offset is not None else None

    def bind(self, mj_model) -> None:
        import mujoco
        if self._offset is not None:
            ids = [mujoco.mj_name2id(mj_model, mujoco.mjtObj.mjOBJ_BODY, n) for n in self._body_names]
            self._body = next((i for i in ids if i > 0), None)
            if self._body is None:
                raise MappingError(f"no MuJoCo body for the camera mount {self._body_names}")

    def move_to_attach(self) -> None:
        data, b = self._rig.data, self._body
        link = np.eye(4)
        link[:3, :3] = np.asarray(data.xmat[b], dtype=np.float64).reshape(3, 3)
        link[:3, 3] = data.xpos[b]
        self.transform = link @ self._offset

    def render(self, rgb=True, depth=False, **_):
        w, h = self.res
        return (np.zeros((h, w, 3), np.uint8) if rgb else None, np.zeros((h, w), np.float32) if depth else None, None, None)


class HeadlessRig:
    """Rendering off: the frozen instance's camera rig with the same names, resolutions and calibration as the Nyx rig
    (the cameras of its scene configuration, topogym.config.scene.load_scene_config, as the Session's camera contract),
    and no renderer: black RGB, depth without a reading, no GPU, no Genesis. For runs whose frames nobody looks at, e.g.
    the Harbor oracle / nop checks (rcb_topogym: RCB_RENDER=off). The same interface as RenderBridge for MujocoWorld:
    .world.cameras, update(mj_model, mj_data), close()."""

    def __init__(self, configs: Mapping[str, Mapping]):
        from types import SimpleNamespace
        self.data = self._model = None
        self.world = SimpleNamespace(cameras={})
        for name, config in configs.items():
            attach = config.get("attach") or {}
            entity, link = str(attach.get("entity", "robot")), str(attach.get("link", "hand"))
            bodies = [f"{entity}{sep}{link}" for sep in _SEPARATORS] + [link]   # robot links keep their MJCF names
            self.world.cameras[str(name)] = _HeadlessCamera(self, config, tuple(bodies))

    def update(self, mj_model, mj_data) -> None:
        """Forward kinematics of MuJoCo's current joint coordinates, on a private MjData (the physics data is not touched)."""
        import mujoco
        if self._model is not mj_model:
            self._model, self.data = mj_model, mujoco.MjData(mj_model)
            for camera in self.world.cameras.values():
                camera.bind(mj_model)
        self.data.qpos[:] = mj_data.qpos
        self.data.mocap_pos[:] = mj_data.mocap_pos
        self.data.mocap_quat[:] = mj_data.mocap_quat
        mujoco.mj_kinematics(mj_model, self.data)

    def close(self) -> None:
        self.data = self._model = None


def headless(frozen_instance) -> HeadlessRig:
    """The camera rig of a frozen instance (path to instance.json) without pixels; see HeadlessRig."""
    from omegaconf import OmegaConf
    from topogym.config.scene import load_scene_config
    from topogym.simulator.config import SimulatorConfig
    path = Path(frozen_instance).resolve()
    cfg = _resolve_config(path, json.loads(path.read_text()))
    return HeadlessRig(OmegaConf.to_container(load_scene_config(SimulatorConfig(**cfg)).env.cameras, resolve=True))
