"""``SoftWorld``: one VBD soft body (cloth sheet / sleeve and / or cable) with kinematic colliders, run in the Newton sidecar.

Do not import this module from the Isaac process (use ``tactilelab_tasks.backends.newton_client.SoftWorldClient``); the service in
``sidecar/services.py`` imports it inside the sidecar.

Frames, units: env-local metres, quaternions ``xyzw``.  A control tick is ``1 / fps`` seconds = ``substeps`` VBD steps; the
colliders (robot fingers, tool bodies) are driven kinematically: their pose is interpolated linearly between the last tick's
and this tick's pose over the substeps, so VBD sees a smooth velocity.

Optional *anchors* make particles / cable segments follow a collider rigidly (an ideal pre-grasp, a clamp that moves) while
active; they are turned into kinematic bodies / particles when attached and restored when released.

Bending plasticity ("crease memory", :class:`PlasticHinge`) is an extension on top of Newton's elastic VBD bending: past a
yield angle the hinge's rest angle flows toward the current dihedral angle, and a hinge folded sharper than the crease angle
keeps the crease.  ``bend_plastic_rate = 0`` (default) is OFF.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import warp as wp

import newton
from newton.solvers import SolverVBD

from softbody_geom import spec


@wp.kernel
def _k_set_collider_poses(
    body_ids: wp.array[int],
    poses: wp.array2d[wp.transform],
    k: int,
    body_q: wp.array[wp.transform],
):
    i = wp.tid()
    body_q[body_ids[i]] = poses[k, i]


@wp.kernel
def _k_particle_anchors(
    pidx: wp.array[int],
    slot: wp.array[int],
    local: wp.array[wp.vec3],
    poses: wp.array2d[wp.transform],
    k: int,
    particle_q: wp.array[wp.vec3],
    particle_qd: wp.array[wp.vec3],
):
    i = wp.tid()
    s = slot[i]
    if s < 0:
        return
    particle_q[pidx[i]] = wp.transform_point(poses[k, s], local[i])
    particle_qd[pidx[i]] = wp.vec3(0.0, 0.0, 0.0)


@wp.kernel
def _k_body_anchors(
    bidx: wp.array[int],
    slot: wp.array[int],
    local: wp.array[wp.transform],
    poses: wp.array2d[wp.transform],
    k: int,
    body_q: wp.array[wp.transform],
):
    i = wp.tid()
    s = slot[i]
    if s < 0:
        return
    body_q[bidx[i]] = poses[k, s] * local[i]


@wp.kernel
def _k_plastic_hinge(
    particle_q: wp.array[wp.vec3],
    edge_indices: wp.array2d[wp.int32],
    yield_angle: float,
    crease_angle: float,
    rate: float,
    rest_angle: wp.array[float],
):
    e = wp.tid()
    if edge_indices[e, 0] == -1 or edge_indices[e, 1] == -1:
        return  # boundary edge: no hinge
    x0 = particle_q[edge_indices[e, 0]]
    x1 = particle_q[edge_indices[e, 1]]
    x2 = particle_q[edge_indices[e, 2]]
    x3 = particle_q[edge_indices[e, 3]]
    n1 = wp.cross(x2 - x0, x3 - x0)
    n2 = wp.cross(x3 - x1, x2 - x1)
    ed = x3 - x2
    n1n = wp.length(n1)
    n2n = wp.length(n2)
    en = wp.length(ed)
    if n1n < 1.0e-6 or n2n < 1.0e-6 or en < 1.0e-6:
        return
    n1h = n1 / n1n
    n2h = n2 / n2n
    sin_t = wp.dot(wp.cross(n1h, n2h), ed / en)
    cos_t = wp.dot(n1h, n2h)
    theta = wp.atan2(sin_t, cos_t)
    d = theta - rest_angle[e]
    pi = 3.14159265
    if d > pi:
        d = d - 2.0 * pi
    elif d < -pi:
        d = d + 2.0 * pi
    ad = wp.abs(d)
    if wp.abs(theta) > crease_angle:
        rest_angle[e] = rest_angle[e] + rate * d
    elif ad > yield_angle:
        excess = (ad - yield_angle) * wp.sign(d)
        rest_angle[e] = rest_angle[e] + rate * excess


class PlasticHinge:
    """Elastic-plastic hinge with crease memory on ``model.edge_rest_angle`` (same dihedral convention as the VBD bending
    kernel).  Per frame on the current particle positions::

        delta = wrap(theta - theta_rest)
        if |theta| > crease_angle:  theta_rest += rate * delta                       (a real fold: no residual spring-back)
        elif |delta| > yield:       theta_rest += rate * (delta - sign(delta) * yield)

    Construct once per world, call :meth:`apply` once per control frame."""

    def __init__(self, model, yield_angle: float, rate: float, crease_angle: float = 10.0):
        self.model = model
        self.yield_angle = float(yield_angle)
        self.crease_angle = float(crease_angle)
        self.rate = float(rate)
        self.rest0 = model.edge_rest_angle.numpy().copy()
        self.enabled = self.rate > 0.0 and int(model.edge_count) > 0

    def apply(self, particle_q: wp.array) -> None:
        if not self.enabled:
            return
        wp.launch(
            _k_plastic_hinge,
            dim=int(self.model.edge_count),
            inputs=[particle_q, self.model.edge_indices, self.yield_angle, self.crease_angle, self.rate],
            outputs=[self.model.edge_rest_angle],
            device=self.model.device,
        )

    def reset(self) -> None:
        """Forget the creases (back to the mesh's original rest angles)."""
        self.model.edge_rest_angle.assign(self.rest0)

    def rest_angles(self):
        return self.model.edge_rest_angle.numpy()


def _tf(pose7: np.ndarray):
    return wp.transform(wp.vec3(*[float(x) for x in pose7[:3]]), wp.quat(*[float(x) for x in pose7[3:7]]))


class SoftWorld:
    """See the module docstring.  ``cfg``: :func:`softbody_geom.spec.world_cfg`; ``collider_q0``: ``(C, 7)`` initial collider poses."""

    def __init__(
        self, cfg: Dict[str, Any], collider_q0: Optional[np.ndarray] = None, cable_points: Optional[np.ndarray] = None
    ):
        self.cfg = spec.world_cfg(cfg)
        c = self.cfg
        self.fps = int(c["fps"])
        self.substeps = int(c["substeps"])
        self.iterations = int(c["iterations"])
        self.frame_dt = 1.0 / self.fps
        self.dt = self.frame_dt / self.substeps
        self.colliders: List[Dict[str, Any]] = list(c["colliders"])
        C = len(self.colliders)
        q0 = np.zeros((C, 7), dtype=np.float32)
        q0[:, 2] = 5.0
        q0[:, 6] = 1.0
        if collider_q0 is not None and C:
            q0 = np.asarray(collider_q0, dtype=np.float32).reshape(C, 7)
        self.collider_q = q0.copy()
        self.has_cloth = "cloth" in c
        self.has_cable = "cable" in c
        self._build(cable_points)
        self._make_solver()
        self._init_state()

    # -- model -----------------------------------------------------------------------------------------------------------
    def _build(self, cable_points):
        c = self.cfg
        sc = c["soft_contact"]
        tb = c["table"]
        g = float(c["gravity"])
        b = newton.ModelBuilder(gravity=(0.0, 0.0, -g))
        b.rigid_gap = float(sc["gap"])

        # table (static box, top face at table.z)
        tcfg = newton.ModelBuilder.ShapeConfig(
            density=0.0, ke=1.0e4, kd=1.0e1, mu=float(tb["mu"]), margin=0.0, gap=float(sc["gap"])
        )
        th = float(tb["thickness"])
        b.add_shape_box(
            -1,
            xform=wp.transform(wp.vec3(tb["center"][0], tb["center"][1], tb["z"] - 0.5 * th), wp.quat_identity()),
            hx=float(tb["half"][0]),
            hy=float(tb["half"][1]),
            hz=0.5 * th,
            cfg=tcfg,
            label="table",
        )
        # static fixtures: boxes {name, pos, half, quat?, mu?}
        for i, s in enumerate(c["statics"]):
            scfg = newton.ModelBuilder.ShapeConfig(
                density=0.0, ke=1.0e4, kd=1.0e1, mu=float(s.get("mu", 0.8)), margin=0.0, gap=float(sc["gap"])
            )
            q = s.get("quat", [0.0, 0.0, 0.0, 1.0])
            b.add_shape_box(
                -1,
                xform=wp.transform(wp.vec3(*s["pos"]), wp.quat(*q)),
                hx=float(s["half"][0]),
                hy=float(s["half"][1]),
                hz=float(s["half"][2]),
                cfg=scfg,
                label=s.get("name", f"static{i}"),
            )

        # soft bodies first (their ids are stable), colliders after
        self.cloth_slice = None
        self.cable_bodies: List[int] = []
        self.cable_segs = 0
        if self.has_cloth:
            self._add_cloth(b)
        if self.has_cable:
            self._add_cable(b, cable_points)

        # kinematic colliders
        self.collider_body: List[int] = []
        for i, col in enumerate(self.colliders):
            fb = b.add_body(xform=_tf(self.collider_q[i]), is_kinematic=True, label=col["name"])
            fcfg = newton.ModelBuilder.ShapeConfig(
                density=0.0,
                ke=float(col.get("ke", 1.0e4)),
                kd=0.1,
                mu=float(col.get("mu", 1.0)),
                margin=0.0,
                gap=float(sc["gap"]),
            )
            if self.has_cloth and bool(c["cloth"].get("full_surface", True)):
                fcfg.configure_sdf(force_sdf=True)
            kind = col.get("shape", "box")
            if kind == "cylinder":  # axis = the collider frame's z
                b.add_shape_cylinder(
                    fb, radius=float(col["radius"]), half_height=float(col["half_height"]), cfg=fcfg, label=col["name"]
                )
            elif kind == "capsule":
                b.add_shape_capsule(
                    fb, radius=float(col["radius"]), half_height=float(col["half_height"]), cfg=fcfg, label=col["name"]
                )
            else:
                h = col["half"]
                b.add_shape_box(fb, hx=float(h[0]), hy=float(h[1]), hz=float(h[2]), cfg=fcfg, label=col["name"])
            self.collider_body.append(fb)

        b.color()
        self.model = b.finalize()
        self.model.soft_contact_ke = float(sc["ke"])
        self.model.soft_contact_kd = float(sc["kd"])
        self.model.soft_contact_mu = float(sc["mu"])
        self.builder = b
        self.device = self.model.device

    def _add_cloth(self, b):
        cl = self.cfg["cloth"]
        cells = tuple(int(v) for v in cl.get("cells", (1, 1)))
        if "tube" in cl:  # a closed sleeve around an axis instead of a flat sheet
            rest, tris = spec.tube_cloth(cl["tube"])
        else:
            rest = spec.cloth_rest_positions(cl)
            tris = spec.grid_triangles(cells)
        start = len(b.particle_q)
        b.add_cloth_mesh(
            vertices=[wp.vec3(*[float(x) for x in v]) for v in rest],
            indices=tris.reshape(-1).tolist(),
            pos=wp.vec3(0.0, 0.0, 0.0),
            rot=wp.quat_identity(),
            vel=wp.vec3(0.0, 0.0, 0.0),
            scale=1.0,
            density=float(cl["density"]),
            tri_ke=float(cl["tri_ke"]),
            tri_ka=float(cl["tri_ka"]),
            tri_kd=float(cl["tri_kd"]),
            edge_ke=float(cl["edge_ke"]),
            edge_kd=float(cl["edge_kd"]),
            particle_radius=float(cl["radius"]),
            color=tuple(cl["color"]),
        )
        P = len(rest)
        self.cloth_slice = slice(start, start + P)
        self.cloth_tris = tris
        self.cloth_rest = rest.astype(np.float32)
        pin = (
            spec.region_mask(rest[:, :2], cl.get("pin_regions", []))
            if "tube" not in cl
            else np.zeros(len(rest), dtype=bool)
        )
        for i in np.nonzero(pin)[0]:
            b.particle_flags[start + int(i)] = int(b.particle_flags[start + int(i)]) & ~int(newton.ParticleFlags.ACTIVE)
            b.particle_mass[start + int(i)] = 0.0
        self.cloth_pinned = np.nonzero(pin)[0]

    def _add_cable(self, b, cable_points):
        cb = self.cfg["cable"]
        if cable_points is None:
            raise ValueError("cable world needs `cable_points` (N+1, 3)")
        pts = np.asarray(cable_points, dtype=np.float32)
        S = len(pts) - 1
        cfg = newton.ModelBuilder.ShapeConfig(
            density=float(cb["density"]), ke=float(cb["ke"]), kd=float(cb["kd"]), mu=float(cb["mu"]), margin=0.0,
            gap=float(self.cfg["soft_contact"]["gap"]),
        )  # fmt: skip
        if not cb.get("self_collision", False):
            cfg.collision_group = -2
        rod = newton.Rod(pts, radius=float(cb["radius"]))
        n0 = b.body_count
        bodies, _ = b.add_rod(
            rod=rod,
            body_frame_origin="com",
            cfg=cfg,
            stretch_stiffness=float(cb["stretch_stiffness"]),
            stretch_damping=float(cb["stretch_damping"]),
            bend_stiffness=float(cb["bend_stiffness"]),
            bend_damping=float(cb["bend_damping"]),
            label="cable",
            color=tuple(cb["color"]),
        )
        self.cable_bodies = list(bodies)
        self.cable_segs = S
        assert self.cable_bodies == list(range(n0, n0 + S))
        for s in cb.get("pinned_segments", []):
            self._make_kinematic(b, self.cable_bodies[int(s)])
        self.cable_seg_len = float(np.linalg.norm(np.diff(pts, axis=0), axis=1).mean())

    @staticmethod
    def _make_kinematic(b, body: int):
        b.body_flags[body] = int(newton.BodyFlags.KINEMATIC)
        b.body_mass[body] = 0.0
        b.body_inv_mass[body] = 0.0
        b.body_inertia[body] = wp.mat33(0.0)
        b.body_inv_inertia[body] = wp.mat33(0.0)

    # -- solver / state --------------------------------------------------------------------------------------------------
    def _make_solver(self):
        c = self.cfg
        kw: Dict[str, Any] = dict(
            iterations=self.iterations, rigid_compliant_alm=True, integrate_with_external_rigid_solver=False
        )
        if self.has_cloth and c["cloth"].get("self_contact", True):
            kw.update(
                particle_enable_self_contact=True,
                particle_self_contact_margin=float(c["cloth"].get("self_margin", 0.003)),
                particle_self_contact_gap=float(c["cloth"].get("self_gap", 0.0)),
                particle_topological_contact_filter_threshold=1,
                particle_rest_shape_contact_exclusion_radius=float(c["cloth"].get("self_exclusion", 0.01)),
                particle_vertex_contact_buffer_size=16,
                particle_edge_contact_buffer_size=20,
            )
        self.solver = SolverVBD(self.model, **kw)
        self.hinge = None
        if self.has_cloth and float(c["cloth"].get("bend_plastic_rate", 0.0)) > 0.0:
            self.hinge = PlasticHinge(
                self.model, c["cloth"]["bend_yield"], c["cloth"]["bend_plastic_rate"], c["cloth"]["bend_crease_angle"]
            )
        self.pipeline = newton.CollisionPipeline(
            self.model,
            broad_phase="nxn",
            soft_contact_gap=float(c["soft_contact"]["gap"]),
            enable_rigid_soft_full_surface_contact=bool(self.has_cloth and c["cloth"].get("full_surface", True)),
        )
        self.contacts = self.pipeline.contacts()
        self.control = self.model.control()
        self.states = [self.model.state(), self.model.state()]
        self.collider_ids = wp.array(np.asarray(self.collider_body, dtype=np.int32), dtype=int, device=self.device)
        self._anchors_p: Dict[int, Dict[str, Any]] = {}
        self._anchors_b: Dict[int, Dict[str, Any]] = {}
        self._rebuild_anchor_arrays()

    def _init_state(self):
        self.snap_particle_q = self.states[0].particle_q.numpy().copy() if self.model.particle_count else None
        self.snap_body_q = self.states[0].body_q.numpy().copy() if self.model.body_count else None
        self.sim_time = 0.0
        self.frames = 0
        self._set_colliders_state(self.collider_q)

    def _set_colliders_state(self, q):
        if not len(self.collider_body):
            return
        for st in self.states:
            bq = st.body_q.numpy()
            for i, bid in enumerate(self.collider_body):
                bq[bid] = q[i]
            st.body_q.assign(bq)

    # -- anchors ---------------------------------------------------------------------------------------------------------
    def _rebuild_anchor_arrays(self):
        dev = self.device
        ap = sorted(self._anchors_p)
        ab = sorted(self._anchors_b)
        self._ap_idx = wp.array(np.asarray(ap, dtype=np.int32), dtype=int, device=dev)
        self._ap_slot = wp.array(
            np.asarray([self._anchors_p[i]["slot"] for i in ap], dtype=np.int32), dtype=int, device=dev
        )
        self._ap_local = wp.array(
            np.asarray([self._anchors_p[i]["local"] for i in ap], dtype=np.float32).reshape(-1, 3),
            dtype=wp.vec3,
            device=dev,
        )
        self._ab_idx = wp.array(np.asarray(ab, dtype=np.int32), dtype=int, device=dev)
        self._ab_slot = wp.array(
            np.asarray([self._anchors_b[i]["slot"] for i in ab], dtype=np.int32), dtype=int, device=dev
        )
        self._ab_local = wp.array(
            np.asarray([self._anchors_b[i]["local"] for i in ab], dtype=np.float32).reshape(-1, 7),
            dtype=wp.transform,
            device=dev,
        )

    def anchor_particles(self, ids: np.ndarray, slot: int) -> None:
        """Make cloth particles ``ids`` (indices into the cloth) follow collider ``slot`` rigidly from now on."""
        q = self.states[0].particle_q.numpy()
        pose = self.collider_q[slot].astype(np.float64)
        inv = spec.pose_inverse(pose)
        flags = self.model.particle_flags.numpy()
        invm = self.model.particle_inv_mass.numpy()
        mass = self.model.particle_mass.numpy()
        for i in np.asarray(ids, dtype=np.int64).tolist():
            gi = self.cloth_slice.start + int(i)
            if gi not in self._anchors_p:
                self._anchors_p[gi] = {
                    "slot": int(slot),
                    "local": spec.pose_apply(inv, q[gi]),
                    "saved": (int(flags[gi]), float(invm[gi]), float(mass[gi])),
                }
            else:
                self._anchors_p[gi].update(slot=int(slot), local=spec.pose_apply(inv, q[gi]))
            flags[gi] = int(flags[gi]) & ~int(newton.ParticleFlags.ACTIVE)
            invm[gi] = 0.0
            mass[gi] = 0.0
        self.model.particle_flags.assign(flags)
        self.model.particle_inv_mass.assign(invm)
        self.model.particle_mass.assign(mass)
        self._rebuild_anchor_arrays()

    def release_particles(self, ids: Optional[np.ndarray] = None) -> None:
        flags = self.model.particle_flags.numpy()
        invm = self.model.particle_inv_mass.numpy()
        mass = self.model.particle_mass.numpy()
        targets = list(self._anchors_p) if ids is None else [self.cloth_slice.start + int(i) for i in ids]
        for gi in targets:
            a = self._anchors_p.pop(gi, None)
            if a is None:
                continue
            flags[gi], invm[gi], mass[gi] = a["saved"]
        self.model.particle_flags.assign(flags)
        self.model.particle_inv_mass.assign(invm)
        self.model.particle_mass.assign(mass)
        self._rebuild_anchor_arrays()

    def anchor_segments(self, segs: np.ndarray, slot: int) -> None:
        """Cable segments ``segs`` follow collider ``slot`` rigidly (kinematic) until released."""
        bq = self.states[0].body_q.numpy()
        inv = spec.pose_inverse(self.collider_q[slot].astype(np.float64))
        m = self.model
        invm = m.body_inv_mass.numpy()
        invi = m.body_inv_inertia.numpy()
        for s in np.asarray(segs, dtype=np.int64).tolist():
            bid = self.cable_bodies[int(s)]
            local = spec.pose_compose(inv, bq[bid].astype(np.float64))
            saved = self._anchors_b.get(bid, {}).get("saved")
            if saved is None:
                saved = (float(invm[bid]), invi[bid].copy())
            self._anchors_b[bid] = {"slot": int(slot), "local": local, "saved": saved}
            invm[bid] = 0.0
            invi[bid] = 0.0
        m.body_inv_mass.assign(invm)
        m.body_inv_inertia.assign(invi)
        self._rebuild_anchor_arrays()

    def release_segments(self, segs: Optional[np.ndarray] = None) -> None:
        m = self.model
        invm = m.body_inv_mass.numpy()
        invi = m.body_inv_inertia.numpy()
        targets = list(self._anchors_b) if segs is None else [self.cable_bodies[int(s)] for s in segs]
        for bid in targets:
            a = self._anchors_b.pop(bid, None)
            if a is None:
                continue
            invm[bid], invi[bid] = a["saved"]
        m.body_inv_mass.assign(invm)
        m.body_inv_inertia.assign(invi)
        self._rebuild_anchor_arrays()

    # -- stepping --------------------------------------------------------------------------------------------------------
    def _interp_poses(self, q_prev: np.ndarray, q_next: np.ndarray) -> np.ndarray:
        """``(substeps, C, 7)`` poses from ``q_prev`` (excluded) to ``q_next`` (the last substep)."""
        S = self.substeps
        a = (np.arange(1, S + 1, dtype=np.float64) / S)[:, None, None]
        p = (1.0 - a) * q_prev[None, :, :3] + a * q_next[None, :, :3]
        qa = q_prev[None, :, 3:7].astype(np.float64)
        qb = q_next[None, :, 3:7].astype(np.float64)
        sgn = np.sign(np.sum(qa * qb, axis=-1, keepdims=True))
        sgn[sgn == 0] = 1.0
        qq = (1.0 - a) * qa + a * sgn * qb
        qq /= np.linalg.norm(qq, axis=-1, keepdims=True)
        return np.concatenate([p, qq], axis=-1).astype(np.float32)

    def step(self, collider_q: Optional[np.ndarray] = None, frames: int = 1) -> None:
        """Advance ``frames`` control ticks with the colliders moving to ``collider_q`` ``(C, 7)`` (linearly, over the first
        frame; the following frames hold it)."""
        C = len(self.collider_body)
        q_next = self.collider_q if collider_q is None else np.asarray(collider_q, dtype=np.float32).reshape(C, 7)
        dev = self.device
        poses_wp = None
        for _ in range(int(frames)):
            if C:
                poses = self._interp_poses(self.collider_q, q_next)
                poses_wp = wp.array(poses.reshape(-1, 7), dtype=wp.transform, device=dev).reshape((self.substeps, C))
            self._frame(poses_wp)
            if C:
                self.collider_q = q_next.copy()
        self.frames += int(frames)

    def _frame(self, poses):
        a, c = self.states
        dev = self.device
        for k in range(self.substeps):
            a.clear_forces()
            if poses is not None:
                wp.launch(
                    _k_set_collider_poses,
                    dim=len(self.collider_body),
                    inputs=[self.collider_ids, poses, k, a.body_q],
                    device=dev,
                )
                if len(self._anchors_p):
                    wp.launch(
                        _k_particle_anchors, dim=len(self._anchors_p),
                        inputs=[self._ap_idx, self._ap_slot, self._ap_local, poses, k, a.particle_q, a.particle_qd], device=dev,
                    )  # fmt: skip
                if len(self._anchors_b):
                    wp.launch(
                        _k_body_anchors, dim=len(self._anchors_b),
                        inputs=[self._ab_idx, self._ab_slot, self._ab_local, poses, k, a.body_q], device=dev,
                    )  # fmt: skip
            if k == 0 and self.has_cloth and self.cfg["cloth"].get("self_contact", True):
                self.solver.rebuild_bvh(a)
            self.pipeline.collide(a, self.contacts)
            self.solver.step(a, c, self.control, self.contacts, self.dt)
            a, c = c, a
        self.states = [a, c]
        if self.hinge is not None:
            self.hinge.apply(a.particle_q)  # crease memory: once per control frame on the new configuration
        self.sim_time += self.frame_dt

    # -- state out -------------------------------------------------------------------------------------------------------
    def cable_nodes(self, body_q: Optional[np.ndarray] = None) -> np.ndarray:
        """``(S+1, 3)`` cable centreline nodes from the segment poses (segment ends; shared nodes averaged)."""
        bq = (self.states[0].body_q.numpy() if body_q is None else body_q)[
            self.cable_bodies[0] : self.cable_bodies[-1] + 1
        ]
        axis = spec.quat_rotate(bq[:, 3:7].astype(np.float64), np.array([0.0, 0.0, 1.0]))
        h = 0.5 * self.cable_seg_len
        starts = bq[:, :3].astype(np.float64) - h * axis
        ends = bq[:, :3].astype(np.float64) + h * axis
        nodes = np.empty((len(bq) + 1, 3))
        nodes[0] = starts[0]
        nodes[-1] = ends[-1]
        nodes[1:-1] = 0.5 * (ends[:-1] + starts[1:])
        return nodes.astype(np.float32)

    def state(self) -> Dict[str, np.ndarray]:
        out: Dict[str, np.ndarray] = {}
        s = self.states[0]
        if self.has_cloth:
            out["particle_q"] = s.particle_q.numpy()[self.cloth_slice].copy()
            out["particle_qd"] = s.particle_qd.numpy()[self.cloth_slice].copy()
        if self.has_cable:
            bq = s.body_q.numpy()
            out["cable_nodes"] = self.cable_nodes(bq)
            out["cable_seg_q"] = bq[self.cable_bodies[0] : self.cable_bodies[-1] + 1].copy()
            qd = s.body_qd.numpy()
            out["cable_seg_qd"] = qd[self.cable_bodies[0] : self.cable_bodies[-1] + 1].copy()
        return out

    # -- reset -----------------------------------------------------------------------------------------------------------
    def reset(
        self,
        particle_q: Optional[np.ndarray] = None,
        cable_points: Optional[np.ndarray] = None,
        collider_q: Optional[np.ndarray] = None,
    ) -> None:
        """Back to the initial state (or the given particle / cable configuration), at rest, colliders teleported."""
        if collider_q is not None and len(self.collider_body):
            self.collider_q = np.asarray(collider_q, dtype=np.float32).reshape(len(self.collider_body), 7)
        self.release_particles()
        self.release_segments()
        for st in self.states:
            if self.has_cloth:
                pq = st.particle_q.numpy()
                if particle_q is not None:
                    pq[self.cloth_slice] = particle_q
                else:
                    pq[self.cloth_slice] = self.cloth_rest
                st.particle_q.assign(pq)
                st.particle_qd.zero_()
            if not self.model.body_count:
                continue
            bq = st.body_q.numpy()
            if self.has_cable and cable_points is not None:
                pts = np.asarray(cable_points, dtype=np.float64)
                mid, tan = spec.cable_rod_frame(pts)
                # +Z of the capsule frame onto the tangent
                z = np.array([0.0, 0.0, 1.0])
                axis = np.cross(np.broadcast_to(z, tan.shape), tan)
                s = np.linalg.norm(axis, axis=1)
                cdot = tan @ z
                ang = np.arctan2(s, cdot)
                axis = axis / np.maximum(s[:, None], 1e-12)
                axis[s < 1e-9] = np.array([1.0, 0.0, 0.0])
                qs = np.concatenate([axis * np.sin(0.5 * ang)[:, None], np.cos(0.5 * ang)[:, None]], axis=1)
                bq[self.cable_bodies[0] : self.cable_bodies[-1] + 1, :3] = mid
                bq[self.cable_bodies[0] : self.cable_bodies[-1] + 1, 3:7] = qs
            elif self.has_cable:
                bq[self.cable_bodies[0] : self.cable_bodies[-1] + 1] = self.snap_body_q[
                    self.cable_bodies[0] : self.cable_bodies[-1] + 1
                ]
            for i, bid in enumerate(self.collider_body):
                bq[bid] = self.collider_q[i]
            st.body_q.assign(bq)
            st.body_qd.zero_()
        self.solver.reset(self.states[0], flags=0)
        if self.hinge is not None:
            self.hinge.reset()
        self.sim_time = 0.0
        self.frames = 0

    def describe(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "fps": self.fps,
            "substeps": self.substeps,
            "colliders": [c["name"] for c in self.colliders],
        }
        if self.has_cloth:
            d["particles"] = int(self.cloth_slice.stop - self.cloth_slice.start)
            d["triangles"] = int(len(self.cloth_tris))
            d["pinned"] = int(len(self.cloth_pinned))
        if self.has_cable:
            d["segments"] = self.cable_segs
        return d
