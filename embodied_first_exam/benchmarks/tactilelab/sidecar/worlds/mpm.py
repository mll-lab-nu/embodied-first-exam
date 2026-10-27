"""A single implicit-MPM dough world with kinematic tools and static colliders (Newton; sidecar side only).

The Isaac scene owns the robot and the tools; each control step it hands the tools' poses over and gets the dough particles
back (service ``mpm.dough`` in ``sidecar/services.py``).  Everything here is env-local, metres, z up, quaternions xyzw.

Scene description (``cfg``, plain JSON)::

    material      preset name or {preset, <override>...}                (softbody_geom.materials)
    voxel         MPM grid size [m]                                     (the points array carries the particles)
    dt, substeps  control step [s] and MPM substeps per control step
    boxes         static collider boxes [{center, half, yaw, mu}]       (plate, tray walls, ...)
    tools         kinematic tools [{name, mu, margin, shapes: [{type: box|cylinder|capsule, half|radius+half_height, offset, yaw}]}]
    bounds        [lo(3), hi(3)] containment box: a particle that leaves it is clamped (a safety net, not physics)
"""

from __future__ import annotations

import numpy as np
import warp as wp

import newton
from newton.solvers import SolverImplicitMPM

from softbody_geom.dough_scene import interp_pose
from softbody_geom.materials import PARTICLE_ATTRS, load_material


@wp.kernel
def _contain(
    q: wp.array[wp.vec3],
    qd: wp.array[wp.vec3],
    lo: wp.vec3,
    hi: wp.vec3,
    clamped: wp.array[int],
):
    i = wp.tid()
    p = q[i]
    v = qd[i]
    if not (wp.isfinite(p[0]) and wp.isfinite(p[1]) and wp.isfinite(p[2])):
        wp.atomic_add(clamped, 1, 1)
        return
    hit = int(0)
    for k in range(3):
        if p[k] < lo[k]:
            p[k] = lo[k]
            v[k] = wp.max(v[k], 0.0)
            hit = 1
        elif p[k] > hi[k]:
            p[k] = hi[k]
            v[k] = wp.min(v[k], 0.0)
            hit = 1
    if hit == 1:
        q[i] = p
        qd[i] = v
        wp.atomic_add(clamped, 0, 1)


def _xform(pos, yaw=0.0, quat=None):
    if quat is None:
        quat = wp.quat_from_axis_angle(wp.vec3(0.0, 0.0, 1.0), float(yaw))
    else:
        quat = wp.quat(*[float(v) for v in quat])
    return wp.transform(wp.vec3(*[float(v) for v in pos]), quat)


class DoughWorld:
    def __init__(self, cfg: dict, points: np.ndarray, pvol: float):
        self.cfg = cfg
        self.material = load_material(cfg.get("material", "dough"))
        self.voxel = float(cfg.get("voxel", 0.005))
        self.dt = float(cfg.get("dt", 1.0 / 60.0))
        self.substeps = int(cfg.get("substeps", 2))
        self.pvol = float(pvol)
        points = np.asarray(points, np.float32).reshape(-1, 3)
        self.n = len(points)
        self.points0 = points.copy()
        self.margin = float(
            cfg.get("collider_margin", 0.0)
        )  # [m] collider surfaces are pushed out by this (~ particle radius)
        mass = self.material["density"] * self.pvol
        radius = 0.5 * self.pvol ** (1.0 / 3.0)

        b = newton.ModelBuilder()
        SolverImplicitMPM.register_custom_attributes(b)
        b.add_particles(
            pos=points.tolist(),
            vel=np.zeros_like(points).tolist(),
            mass=[mass] * self.n,
            radius=[radius] * self.n,
        )
        # kinematic tools first: body index == tool index
        self.tool_names = []
        for t in cfg.get("tools", []):
            body = b.add_body(xform=wp.transform_identity(), is_kinematic=True, label=str(t["name"]))
            self.tool_names.append(str(t["name"]))
            scfg = newton.ModelBuilder.ShapeConfig(
                mu=float(t.get("mu", self.material["collider_friction"])),
                density=0.0,
                margin=float(t.get("margin", self.margin)),
            )
            for s in t["shapes"]:
                xf = _xform(s.get("offset", [0, 0, 0]), s.get("yaw", 0.0), s.get("quat"))
                kind = s["type"]
                if kind == "box":
                    hx, hy, hz = (float(v) for v in s["half"])
                    b.add_shape_box(body, xform=xf, hx=hx, hy=hy, hz=hz, cfg=scfg)
                elif kind == "cylinder":
                    b.add_shape_cylinder(
                        body, xform=xf, radius=float(s["radius"]), half_height=float(s["half_height"]), cfg=scfg
                    )
                elif kind == "capsule":
                    b.add_shape_capsule(
                        body, xform=xf, radius=float(s["radius"]), half_height=float(s["half_height"]), cfg=scfg
                    )
                else:
                    raise ValueError(f"tool shape {kind!r}")
        for box in cfg.get("boxes", []):
            hx, hy, hz = (float(v) for v in box["half"])
            b.add_shape_box(
                body=-1,
                xform=_xform(box["center"], box.get("yaw", 0.0)),
                hx=hx,
                hy=hy,
                hz=hz,
                cfg=newton.ModelBuilder.ShapeConfig(
                    mu=float(box.get("mu", self.material["collider_friction"])),
                    density=0.0,
                    margin=float(box.get("margin", self.margin)),
                ),
            )
        if cfg.get("ground", True):
            b.add_ground_plane(
                cfg=newton.ModelBuilder.ShapeConfig(mu=float(self.material["collider_friction"]), margin=self.margin)
            )
        self.model = b.finalize()
        self.model.set_gravity(tuple(cfg.get("gravity", [0.0, 0.0, -9.81])))
        self.device = self.model.device
        self.n_tools = len(self.tool_names)

        for name in PARTICLE_ATTRS:
            getattr(self.model.mpm, name).fill_(self.material[name])

        lo, hi = (np.asarray(v, np.float64) for v in cfg["bounds"])
        scfg = SolverImplicitMPM.Config()
        scfg.voxel_size = self.voxel
        scfg.max_iterations = int(cfg.get("iterations", 50))
        scfg.tolerance = float(cfg.get("tolerance", 1.0e-4))
        scfg.strain_basis = "P0"
        scfg.collider_basis = "S2"
        scfg.collider_velocity_mode = "backward"
        scfg.critical_fraction = float(cfg.get("critical_fraction", 0.0))
        scfg.grid_type = "sparse"
        scfg.grid_padding = 0
        cells = int(np.prod(np.ceil((hi - lo) / self.voxel)))
        scfg.max_active_cell_count = int(1.5 * cells)
        self.solver = SolverImplicitMPM(self.model, scfg)
        self.state = self.model.state()
        self.box_lo = wp.vec3(*[float(v) for v in lo])
        self.box_hi = wp.vec3(*[float(v) for v in hi])
        self.clamped = wp.zeros(2, dtype=int, device=self.device)
        self._pose = np.tile(np.array([0, 0, 1.0, 0, 0, 0, 1.0]), (max(self.n_tools, 1), 1))
        self._virgin = None
        self._last_substeps = self.substeps
        self.reset(points)

    # -- state -----------------------------------------------------------------------------------------------------------
    def reset(self, points=None, poses=None):
        """Fresh stress-free dough at ``points`` (default: the initial ones); tools placed at ``poses`` (T, 7)."""
        pts = self.points0 if points is None else np.asarray(points, np.float32).reshape(-1, 3)
        assert len(pts) == self.n, (len(pts), self.n)
        m = self.state.mpm
        if self._virgin is None:
            self._virgin = {
                k: getattr(m, k).numpy().copy()
                for k in (
                    "particle_qd_grad",
                    "particle_elastic_strain",
                    "particle_Jp",
                    "particle_stress",
                    "particle_transform",
                )
            }
        else:
            for k, v in self._virgin.items():
                getattr(m, k).assign(wp.array(v, dtype=getattr(m, k).dtype, device=self.device))
        self.state.particle_q.assign(wp.array(pts, dtype=wp.vec3, device=self.device))
        self.state.particle_qd.zero_()
        if poses is not None and self.n_tools:
            self._pose[: self.n_tools] = np.asarray(poses, np.float64).reshape(-1, 7)
        self._write_tools(self._pose, self._pose, 1.0)
        self.solver.reset(self.state, flags=int(newton.StateFlags.BODY))
        self.clamped.zero_()
        self.time = 0.0

    def _write_tools(self, p0, p1, a):
        """Tools at the pose a of the way p0 -> p1, at rest."""
        if not self.n_tools:
            return
        q = np.zeros((self.n_tools, 7), np.float32)
        for i in range(self.n_tools):
            q[i] = interp_pose(p0[i], p1[i], a)
        self.state.body_q.assign(wp.array(q, dtype=wp.transform, device=self.device))
        self.state.body_qd.assign(wp.zeros(self.n_tools, dtype=wp.spatial_vector, device=self.device))

    def _write_tools_vel(self, pa, pb, h):
        """Tools at pose pb with velocity (pb - pa) / h (kinematic bodies: the collider sees their motion)."""
        q = np.zeros((self.n_tools, 7), np.float32)
        qd = np.zeros((self.n_tools, 6), np.float32)
        for i in range(self.n_tools):
            q[i] = pb[i]
            qd[i, :3] = (pb[i, :3] - pa[i, :3]) / h
            # angular velocity from the quaternion difference (small rotations)
            qa, qb = pa[i, 3:], pb[i, 3:]
            dq = _quat_mul(qb, _quat_conj(qa))
            if dq[3] < 0:
                dq = -dq
            qd[i, 3:] = 2.0 * dq[:3] / h
        self.state.body_q.assign(wp.array(q, dtype=wp.transform, device=self.device))
        self.state.body_qd.assign(wp.array(qd, dtype=wp.spatial_vector, device=self.device))

    def step(self, poses=None, substeps=None):
        """Advance one control step ``dt`` with the tools moving linearly from their last pose to ``poses`` (T, 7)."""
        ns = int(substeps or self.substeps)
        self._last_substeps = ns
        target = self._pose.copy()
        if poses is not None and self.n_tools:
            target[: self.n_tools] = np.asarray(poses, np.float64).reshape(-1, 7)
        h = self.dt / ns
        prev = self._pose.copy()
        for k in range(ns):
            a = (k + 1) / ns
            cur = np.stack([interp_pose(self._pose[i], target[i], a) for i in range(len(target))])
            if self.n_tools:
                self._write_tools_vel(prev, cur, h)
            self.solver.step(self.state, self.state, None, None, h)
            wp.launch(
                _contain,
                dim=self.n,
                inputs=[self.state.particle_q, self.state.particle_qd, self.box_lo, self.box_hi, self.clamped],
                device=self.device,
            )
            prev = cur
        self._pose = target
        self.time += self.dt

    def tool_wrench(self, tool: int = 0) -> np.ndarray:
        """Force [N] and torque [N m] (about the tool body's origin) the dough exerts on tool ``tool`` in the last MPM substep:
        the collider impulses of the grid nodes (``collect_collider_impulses``) of that body, over the substep length."""
        if not self.n_tools:
            return np.zeros(6, np.float32)
        imp, pos, cid = self.solver.collect_collider_impulses(self.state)
        imp, pos, cid = imp.numpy(), pos.numpy(), cid.numpy()
        bidx = self.solver.collider_body_index.numpy()
        ok = (cid >= 0) & (cid < len(bidx))
        sel = np.zeros(len(cid), bool)
        sel[ok] = bidx[cid[ok]] == tool
        if not sel.any():
            return np.zeros(6, np.float32)
        h = self.dt / self._last_substeps
        f = imp[sel].sum(0) / h
        origin = self._pose[tool, :3]
        tq = np.cross(pos[sel] - origin, imp[sel] / h).sum(0)
        w = np.concatenate([f, tq]).astype(np.float32)
        return np.where(np.isfinite(w), w, 0.0).astype(np.float32)

    def particles(self) -> np.ndarray:
        return self.state.particle_q.numpy().astype(np.float32)

    def velocities(self) -> np.ndarray:
        return self.state.particle_qd.numpy().astype(np.float32)

    def stats(self) -> dict:
        q = self.particles()
        return {
            "n": self.n,
            "finite": bool(np.isfinite(q).all()),
            "clamped": [int(v) for v in self.clamped.numpy()],
            "zmin": float(np.nanmin(q[:, 2])),
            "zmax": float(np.nanmax(q[:, 2])),
        }

    def check_grid(self):
        self.solver.check_sparse_grid_rebuild_status()


def _quat_conj(q):
    return np.array([-q[0], -q[1], -q[2], q[3]])


def _quat_mul(a, b):
    x1, y1, z1, w1 = a
    x2, y2, z2, w2 = b
    return np.array(
        [
            w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
            w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
        ]
    )
