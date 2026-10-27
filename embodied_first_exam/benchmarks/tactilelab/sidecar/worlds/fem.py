"""Compliant (tetrahedral VBD) plug worlds of ``fem_plug_insert``; Newton sidecar only.

``PlugPadWorld`` (the shipped, direct-sensor variant): the plug is pinched by the two kinematic GEL-PAD colliders; a plate with
a loose pick socket and a press-fit target hole.  The pads are kinematic boxes whose env-local poses (2, 7: x y z qx qy qz qw)
are handed over every tick (interpolated over the VBD substeps); the plug is held by friction only: the contact friction of
VBD averages the particle side (``soft_contact_mu``) with the shape's ``mu``, so the pads get a large shape ``mu`` (grip) while
the plate keeps a small one (the plug must slide into the press fit).

``PlugWorld`` (carrier variant): the plug hangs below a kinematic carrier; its top ``grip_band`` is anchored to the carrier pose
while held, ``release`` frees it.

Frames: env-local metres, quaternions xyzw.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np
import warp as wp

import newton
from newton.solvers import SolverVBD

from softbody_geom import plug_scene as ps
from softbody_geom.dough_scene import quat_rot_xyzw


@wp.kernel
def _k_set_pad_poses(body_ids: wp.array[int], poses: wp.array2d[wp.transform], k: int, body_q: wp.array[wp.transform]):
    i = wp.tid()
    body_q[body_ids[i]] = poses[k, i]


@wp.kernel
def _k_anchor(
    pidx: wp.array[int],
    local: wp.array[wp.vec3],
    poses: wp.array[wp.transform],
    k: int,
    particle_q: wp.array[wp.vec3],
    particle_qd: wp.array[wp.vec3],
):
    i = wp.tid()
    particle_q[pidx[i]] = wp.transform_point(poses[k], local[i])
    particle_qd[pidx[i]] = wp.vec3(0.0, 0.0, 0.0)


def _tf(p):
    return wp.transform(wp.vec3(*[float(x) for x in p[:3]]), wp.quat(*[float(x) for x in p[3:7]]))


class PlugPadWorld:
    def __init__(self, cfg: Dict[str, Any], pad_poses0: np.ndarray):
        self.cfg = cfg
        pc = {k: v for k, v in cfg["plug"].items() if k in ps.PlugSpec.__dataclass_fields__}
        self.spec = ps.PlugSpec(**pc)
        self.pick_spec = ps.PlugSpec(**{**pc, "hole": tuple(cfg["pick"]["hole"])})
        self.fps = int(cfg.get("fps", 30))
        self.substeps = int(cfg.get("substeps", 10))
        self.iterations = int(cfg.get("iterations", 5))
        self.dt = 1.0 / self.fps / self.substeps
        self.hole_xy = np.asarray(cfg["hole_xy"], float)
        self.pick_xy = np.asarray(cfg["pick_xy"], float)
        self.top_z = float(cfg.get("top_z", 0.0))
        self.gap = float(cfg.get("contact_gap", 0.002))
        sp = self.spec
        b = newton.ModelBuilder(gravity=(0.0, 0.0, -9.81))
        b.rigid_gap = self.gap
        # plate: floor + walls around both holes (static boxes, small friction: the plug must slide into the press fit)
        plate_mu = float(cfg.get("plate_mu", 0.2))
        for xy, spec_ in ((self.pick_xy, self.pick_spec), (self.hole_xy, self.spec)):
            for box in ps.fixture_boxes(xy, self.top_z, spec_):
                fc = newton.ModelBuilder.ShapeConfig(
                    density=0.0, ke=1.0e4, kd=1.0e1, mu=plate_mu, margin=0.0, gap=self.gap
                )
                b.add_shape_box(
                    -1,
                    xform=wp.transform(wp.vec3(*box["pos"]), wp.quat_identity()),
                    hx=box["half"][0],
                    hy=box["half"][1],
                    hz=box["half"][2],
                    cfg=fc,
                    label=f"{box['name']}_{xy[0]:+.3f}",
                )
        # lead-in: four thin 45 deg ramps flaring outward from the target hole's top edge (a funnel: the carried plug is some mm off the hole axis)
        L = float(cfg.get("lead_in", 0.0))
        if L > 0.0:
            t_ = 0.001
            hx_, hy_ = 0.5 * self.spec.hole[0], 0.5 * self.spec.hole[1]
            c45 = 0.5 * np.sqrt(2.0)
            for ax, sgn in ((0, 1.0), (0, -1.0), (1, 1.0), (1, -1.0)):
                half_in = (hx_, hy_)[ax]
                half_len_cross = (hy_, hx_)[ax] + L * c45 + 0.002  # along the wall (covers the corners)
                centre = np.array([self.hole_xy[0], self.hole_xy[1], self.top_z + 0.5 * L * c45])
                centre[ax] += sgn * (half_in + 0.5 * L * c45)
                ang = -sgn * np.pi / 4.0  # rotation about the axis in the plate plane normal to the ramp direction
                if ax == 0:
                    q = [0.0, float(np.sin(0.5 * ang)), 0.0, float(np.cos(0.5 * ang))]  # about y
                    half = [0.5 * L, half_len_cross, 0.5 * t_]
                else:
                    q = [float(np.sin(-0.5 * ang)), 0.0, 0.0, float(np.cos(-0.5 * ang))]  # about x (opposite sense)
                    half = [half_len_cross, 0.5 * L, 0.5 * t_]
                fc = newton.ModelBuilder.ShapeConfig(
                    density=0.0, ke=1.0e4, kd=1.0e1, mu=plate_mu, margin=0.0, gap=self.gap
                )
                b.add_shape_box(
                    -1,
                    xform=wp.transform(wp.vec3(*[float(v) for v in centre]), wp.quat(*q)),
                    hx=half[0],
                    hy=half[1],
                    hz=half[2],
                    cfg=fc,
                    label=f"leadin_{ax}_{sgn:+.0f}",
                )
        # the plug, standing on the pick socket's floor
        n, cell = ps.grid_dims(sp)
        self.n_nodes = (n[0] + 1) * (n[1] + 1) * (n[2] + 1)
        start = len(b.particle_q)
        z_bottom = self.top_z - sp.hole_depth + 0.0003
        b.add_soft_grid(
            pos=wp.vec3(float(self.pick_xy[0]) - 0.5 * sp.size[0], float(self.pick_xy[1]) - 0.5 * sp.size[1], z_bottom),
            rot=wp.quat_identity(), vel=wp.vec3(0.0),
            dim_x=n[0], dim_y=n[1], dim_z=n[2], cell_x=cell[0], cell_y=cell[1], cell_z=cell[2],
            density=sp.density, k_mu=sp.k_mu, k_lambda=sp.k_lambda, k_damp=sp.k_damp,
            particle_radius=float(cfg.get("particle_radius", 0.0005)),
        )  # fmt: skip
        self.pslice = slice(start, start + self.n_nodes)
        self.tris = np.asarray(b.tri_indices, dtype=np.int32).reshape(-1, 3) - start
        self.rest = ps.plug_particle_grid(sp, tuple(self.pick_xy), z_bottom)
        # the two gel pads: kinematic bodies, a thick box behind the gel face (a 4 mm plate would be thinner than the particle spacing)
        pads = cfg["pads"]
        hx, hy, hz0 = (float(v) for v in pads["half"])
        hz = 0.5 * (hz0 + float(pads["back"]))
        self.pad_body = []
        for i, name in enumerate(("pad_left", "pad_right")):
            fb = b.add_body(xform=_tf(pad_poses0[i]), is_kinematic=True, label=name)
            sc = newton.ModelBuilder.ShapeConfig(
                density=0.0, ke=1.0e4, kd=0.1, mu=float(pads.get("mu", 2.0)), margin=0.0, gap=self.gap
            )
            b.add_shape_box(
                fb,
                xform=wp.transform(wp.vec3(0.0, 0.0, hz0 - hz), wp.quat_identity()),
                hx=hx,
                hy=hy,
                hz=hz,
                cfg=sc,
                label=name,
            )
            self.pad_body.append(fb)
        b.color()
        self.model = b.finalize()
        self.model.soft_contact_ke = float(cfg.get("contact_ke", 2.0e6))
        self.model.soft_contact_kd = float(cfg.get("contact_kd", 2.0e-1))
        self.model.soft_contact_mu = float(sp.mu)
        self.device = self.model.device
        self.solver = SolverVBD(
            self.model, iterations=self.iterations, rigid_compliant_alm=True, integrate_with_external_rigid_solver=False
        )
        self.pipeline = newton.CollisionPipeline(self.model, broad_phase="nxn", soft_contact_gap=self.gap)
        self.contacts = self.pipeline.contacts()
        self.control = self.model.control()
        self.states = [self.model.state(), self.model.state()]
        self.pad_ids = wp.array(np.asarray(self.pad_body, dtype=np.int32), dtype=int, device=self.device)
        self.pads_q = np.asarray(pad_poses0, np.float32).reshape(2, 7).copy()
        self.reset(pad_poses0)

    def reset(self, pad_poses=None) -> np.ndarray:
        """The plug standing in the pick socket at rest, the pads at ``pad_poses``."""
        if pad_poses is not None:
            self.pads_q = np.asarray(pad_poses, np.float32).reshape(2, 7).copy()
        for st in self.states:
            pq = st.particle_q.numpy()
            pq[self.pslice] = self.rest
            st.particle_q.assign(pq)
            st.particle_qd.zero_()
            bq = st.body_q.numpy()
            for i, bid in enumerate(self.pad_body):
                bq[bid] = self.pads_q[i]
            st.body_q.assign(bq)
            st.body_qd.zero_()
        self.solver.reset(self.states[0], flags=0)
        self.frames = 0
        return self.particles()

    def _interp(self, prev: np.ndarray, nxt: np.ndarray) -> np.ndarray:
        """``(substeps, 2, 7)`` pad poses from ``prev`` (excluded) to ``nxt`` (the last substep)."""
        S = self.substeps
        a = (np.arange(1, S + 1, dtype=np.float64) / S)[:, None, None]
        p = (1 - a) * prev[None, :, :3] + a * nxt[None, :, :3]
        qa, qb = prev[None, :, 3:7].astype(np.float64), nxt[None, :, 3:7].astype(np.float64)
        sgn = np.sign(np.sum(qa * qb, axis=-1, keepdims=True))
        sgn[sgn == 0] = 1.0
        qq = (1 - a) * qa + a * sgn * qb
        qq /= np.linalg.norm(qq, axis=-1, keepdims=True)
        return np.concatenate([p, qq], axis=-1).astype(np.float32)

    def step(self, pad_poses=None, frames: int = 1) -> None:
        nxt = self.pads_q if pad_poses is None else np.asarray(pad_poses, np.float32).reshape(2, 7)
        dev = self.device
        for _ in range(int(frames)):
            poses = wp.array(self._interp(self.pads_q, nxt).reshape(-1, 7), dtype=wp.transform, device=dev).reshape(
                (self.substeps, 2)
            )
            a, c = self.states
            for k in range(self.substeps):
                a.clear_forces()
                wp.launch(_k_set_pad_poses, dim=2, inputs=[self.pad_ids, poses, k, a.body_q], device=dev)
                self.pipeline.collide(a, self.contacts)
                self.solver.step(a, c, self.control, self.contacts, self.dt)
                a, c = c, a
            self.states = [a, c]
            self.pads_q = nxt.copy()
            self.frames += 1

    def particles(self) -> np.ndarray:
        return self.states[0].particle_q.numpy()[self.pslice].astype(np.float32)

    def stats(self) -> Dict[str, Any]:
        q = self.particles()
        return {"finite": bool(np.isfinite(q).all()), "zmin": float(q[:, 2].min()), "zmax": float(q[:, 2].max())}


class PlugWorld:
    """The carrier variant: the plug hangs below its top frame (origin of the rest pose = centre of the top face)."""

    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.spec = ps.PlugSpec(
            **{k: v for k, v in cfg.get("plug", {}).items() if k in ps.PlugSpec.__dataclass_fields__}
        )
        self.fps = int(cfg.get("fps", 30))
        self.substeps = int(cfg.get("substeps", 10))
        self.iterations = int(cfg.get("iterations", 5))
        self.dt = 1.0 / self.fps / self.substeps
        self.hole_xy = np.asarray(cfg.get("hole_xy", [0.0, 0.0]), float)
        self.top_z = float(cfg.get("top_z", 0.0))
        self.gap = float(cfg.get("contact_gap", 0.002))
        sp = self.spec
        b = newton.ModelBuilder(gravity=(0.0, 0.0, -9.81))
        b.rigid_gap = self.gap
        # table + fixture (static boxes)
        tb = cfg.get("table", {"z": self.top_z - sp.hole_depth - sp.floor, "half": [0.3, 0.3], "mu": 0.6})
        sc = newton.ModelBuilder.ShapeConfig(
            density=0.0, ke=1.0e4, kd=1.0e1, mu=float(tb.get("mu", 0.6)), margin=0.0, gap=self.gap
        )
        b.add_shape_box(
            -1,
            xform=wp.transform(wp.vec3(0, 0, float(tb["z"]) - 0.01), wp.quat_identity()),
            hx=float(tb["half"][0]),
            hy=float(tb["half"][1]),
            hz=0.01,
            cfg=sc,
            label="table",
        )
        for box in ps.fixture_boxes(self.hole_xy, self.top_z, sp):
            fc = newton.ModelBuilder.ShapeConfig(
                density=0.0, ke=1.0e4, kd=1.0e1, mu=float(box["mu"]), margin=0.0, gap=self.gap
            )
            b.add_shape_box(
                -1,
                xform=wp.transform(wp.vec3(*box["pos"]), wp.quat_identity()),
                hx=box["half"][0],
                hy=box["half"][1],
                hz=box["half"][2],
                cfg=fc,
                label=box["name"],
            )
        n, cell = ps.grid_dims(sp)
        self.n_nodes = (n[0] + 1) * (n[1] + 1) * (n[2] + 1)
        self.rest_local = ps.plug_particle_grid(sp, (0.0, 0.0), -float(sp.size[2]))  # (P, 3), top face at z = 0
        start = len(b.particle_q)
        b.add_soft_grid(
            pos=wp.vec3(-0.5 * sp.size[0], -0.5 * sp.size[1], -float(sp.size[2])),
            rot=wp.quat_identity(),
            vel=wp.vec3(0.0),
            dim_x=n[0], dim_y=n[1], dim_z=n[2],
            cell_x=cell[0], cell_y=cell[1], cell_z=cell[2],
            density=sp.density, k_mu=sp.k_mu, k_lambda=sp.k_lambda, k_damp=sp.k_damp,
            particle_radius=float(cfg.get("particle_radius", 0.002)),
        )  # fmt: skip
        self.pslice = slice(start, start + self.n_nodes)
        self.tris = np.asarray(b.tri_indices, dtype=np.int32).reshape(-1, 3) - start
        b.color()
        self.model = b.finalize()
        self.model.soft_contact_ke = float(cfg.get("contact_ke", 2.0e6))
        self.model.soft_contact_kd = float(cfg.get("contact_kd", 2.0e-1))
        self.mu_insert = float(sp.mu)
        self.mu_hold = float(cfg.get("mu_hold", sp.mu))  # friction once the plug is let go (it must stay in the hole)
        self.model.soft_contact_mu = self.mu_insert
        self.device = self.model.device
        self.solver = SolverVBD(
            self.model, iterations=self.iterations, rigid_compliant_alm=True, integrate_with_external_rigid_solver=False
        )
        self.pipeline = newton.CollisionPipeline(self.model, broad_phase="nxn", soft_contact_gap=self.gap)
        self.contacts = self.pipeline.contacts()
        self.control = self.model.control()
        self.states = [self.model.state(), self.model.state()]
        self.carrier = np.array([0, 0, self.top_z + 0.05, 0, 0, 0, 1.0])
        self._anchored: Optional[Dict[str, Any]] = None
        self._saved = None
        self.reset()

    # -- placement -------------------------------------------------------------------------------------------------------
    def _world_rest(self, pose7) -> np.ndarray:
        """Rest particles of the plug carried at ``pose7`` (xyz + xyzw): the top face centre at the carrier pose."""
        R = quat_rot_xyzw(np.asarray(pose7[3:7], float))
        return self.rest_local @ R.T + np.asarray(pose7[:3], float)

    def reset(self, carrier_pose=None) -> np.ndarray:
        """Release any anchor, put the plug hanging from ``carrier_pose`` (default: above the hole), at rest."""
        self.release()
        self.model.soft_contact_mu = self.mu_insert
        if carrier_pose is not None:
            self.carrier = np.asarray(carrier_pose, float).reshape(7)
        q = self._world_rest(self.carrier)
        for st in self.states:
            pq = st.particle_q.numpy()
            pq[self.pslice] = q
            st.particle_q.assign(pq)
            st.particle_qd.zero_()
        self.solver.reset(self.states[0], flags=0)
        self.frames = 0
        return q

    # -- grasp -----------------------------------------------------------------------------------------------------------
    def anchor(self) -> int:
        """Anchor the top band to the carrier (the gripper holds the plug): those particles follow the carrier pose."""
        sp = self.spec
        q = self.states[0].particle_q.numpy()[self.pslice]
        R = quat_rot_xyzw(self.carrier[3:7])
        local = (q - self.carrier[:3]) @ R  # carrier frame
        band = np.where(local[:, 2] > -sp.grip_band - 1e-6)[0]
        flags = self.model.particle_flags.numpy()
        invm = self.model.particle_inv_mass.numpy()
        mass = self.model.particle_mass.numpy()
        gi = band + self.pslice.start
        self._saved = (gi, flags[gi].copy(), invm[gi].copy(), mass[gi].copy())
        flags[gi] = flags[gi] & ~int(newton.ParticleFlags.ACTIVE)
        invm[gi] = 0.0
        mass[gi] = 0.0
        self.model.particle_flags.assign(flags)
        self.model.particle_inv_mass.assign(invm)
        self.model.particle_mass.assign(mass)
        self._anchored = {
            "idx": wp.array(gi.astype(np.int32), dtype=int, device=self.device),
            "local": wp.array(local[band].astype(np.float32), dtype=wp.vec3, device=self.device),
        }
        return int(len(band))

    def release(self) -> None:
        if self._anchored is None:
            return
        gi, flags_s, invm_s, mass_s = self._saved
        flags = self.model.particle_flags.numpy()
        invm = self.model.particle_inv_mass.numpy()
        mass = self.model.particle_mass.numpy()
        flags[gi], invm[gi], mass[gi] = flags_s, invm_s, mass_s
        self.model.soft_contact_mu = self.mu_hold
        self.model.particle_flags.assign(flags)
        self.model.particle_inv_mass.assign(invm)
        self.model.particle_mass.assign(mass)
        self._anchored = None

    @property
    def held(self) -> bool:
        return self._anchored is not None

    # -- stepping --------------------------------------------------------------------------------------------------------
    def _interp(self, prev, nxt) -> np.ndarray:
        S = self.substeps
        a = (np.arange(1, S + 1, dtype=np.float64) / S)[:, None]
        p = (1 - a) * prev[None, :3] + a * nxt[None, :3]
        qa, qb = prev[3:7].astype(np.float64), nxt[3:7].astype(np.float64)
        if np.dot(qa, qb) < 0:
            qb = -qb
        qq = (1 - a) * qa[None] + a * qb[None]
        qq /= np.linalg.norm(qq, axis=1, keepdims=True)
        return np.concatenate([p, qq], axis=1).astype(np.float32)

    def step(self, carrier_pose=None, frames: int = 1) -> None:
        nxt = self.carrier if carrier_pose is None else np.asarray(carrier_pose, float).reshape(7)
        dev = self.device
        for _ in range(int(frames)):
            poses = wp.array(self._interp(self.carrier, nxt), dtype=wp.transform, device=dev)
            a, c = self.states
            for k in range(self.substeps):
                a.clear_forces()
                if self._anchored is not None:
                    wp.launch(
                        _k_anchor,
                        dim=len(self._anchored["idx"]),
                        inputs=[self._anchored["idx"], self._anchored["local"], poses, k, a.particle_q, a.particle_qd],
                        device=dev,
                    )
                self.pipeline.collide(a, self.contacts)
                self.solver.step(a, c, self.control, self.contacts, self.dt)
                a, c = c, a
            self.states = [a, c]
            self.carrier = nxt.copy()
            self.frames += 1

    def particles(self) -> np.ndarray:
        return self.states[0].particle_q.numpy()[self.pslice].astype(np.float32)

    def stats(self) -> Dict[str, Any]:
        q = self.particles()
        return {
            "finite": bool(np.isfinite(q).all()),
            "zmin": float(q[:, 2].min()),
            "zmax": float(q[:, 2].max()),
            "held": self.held,
        }
