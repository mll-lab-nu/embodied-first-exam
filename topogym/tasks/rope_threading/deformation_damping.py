"""Task-local, momentum-preserving dissipation through native FEM forces.

F = -alpha M (v - v_rigid), where v_rigid is the mass-weighted best-fit
translation and rotation. This is a declared phenomenological deformation
damping model, not a calibrated rope viscosity or a velocity overwrite.

Native interface: libuipc v0.0.25 FiniteElementExternalForce, UID 671.
https://github.com/spiriMirror/libuipc/blob/v0.0.25/docs/specification/constitutions/finite_element_external_force.md
"""
import numpy as np


def dissipative_forces(positions, velocity, mass, rate, dt):
    x, v, m = (np.asarray(value, dtype=np.float64) for value in (positions, velocity, mass))
    if not (np.isfinite(rate) and rate >= 0 and 0 < dt and rate*dt < 1):
        raise ValueError("Damping requires finite alpha >= 0 and alpha*dt < 1")
    if np.any(m <= 0) or not all(np.isfinite(a).all() for a in (x, v, m)):
        raise ValueError("Damping requires finite states and positive vertex masses")
    total = m.sum()
    r = x-(m[:, None]*x).sum(axis=0)/total
    translation = (m[:, None]*v).sum(axis=0)/total
    inertia = np.eye(3)*np.sum(m*np.sum(r*r, axis=1))-np.einsum("n,ni,nj->ij", m, r, r)
    momentum = np.sum(m[:, None]*np.cross(r, v-translation), axis=0)
    omega = np.linalg.lstsq(inertia, momentum, rcond=1.e-12)[0]
    residual = v-translation-np.cross(omega, r)
    force = -rate*m[:, None]*residual
    power = float(np.sum(force*v))
    force_only_energy_change = dt*power+.5*dt*dt*float(np.sum(force*force/m[:, None]))
    audit = dict(power_w=power, net_force_n=float(np.linalg.norm(force.sum(axis=0))),
        net_torque_nm=float(np.linalg.norm(np.cross(r, force).sum(axis=0))),
        force_only_kinetic_change_j=force_only_energy_change)
    if (power > 1.e-12 or force_only_energy_change > 1.e-12
            or audit["net_force_n"] > 1.e-9 or audit["net_torque_nm"] > 1.e-9):
        raise RuntimeError("Deformation damping violated its dissipation or momentum checks")
    return force, audit


class DeformationDamping:
    def __init__(self, coupler, rope, rest_positions, rate, dt):
        self.coupler, self.rope = coupler, rope
        self.rate, self.dt = float(rate), float(dt)
        if not np.isfinite(self.rate) or self.rate <= 0 or self.rate*self.dt >= 1:
            raise ValueError("Invalid deformation damping rate")
        tets = np.asarray(rope.elems, dtype=int)
        points = np.asarray(rest_positions, dtype=float)[tets]
        volumes = abs(np.linalg.det(np.stack([points[:, j]-points[:, 0] for j in (1, 2, 3)], axis=2)))/6
        self.mass = np.zeros(len(rest_positions))
        np.add.at(self.mass, tets.ravel(), np.repeat(volumes*float(rope.material.rho)/4, 4))
        self.force = np.zeros((len(self.mass), 3))
        self.prepared_steps = self.applied_steps = 0
        self.work_j = 0.
        self.maxima = dict(power_w=0., net_force_n=0., net_torque_nm=0., force_only_kinetic_change_j=0.)
        self.original_add = coupler._add_fem_entities_to_ipc
        coupler._add_fem_entities_to_ipc = self._add_force_constitution

    def specification(self):
        return dict(model="rigid-mode-projected mass-proportional deformation damping",
            rate_s_inv=self.rate, force="-alpha * lumped_mass * (native_velocity - best_fit_rigid_velocity)",
            rigid_translation_and_rotation_projected_out=True, velocity_overwrites=False,
            native_force_constitution_uid=671, total_lumped_mass_kg=float(self.mass.sum()),
            integrator="explicit dissipative load inside native BDF1 predictor",
            alpha_dt=self.rate*self.dt, calibrated_against_real_rope=False,
            shared_constraint_flag="enables native forces; nongrasped position-spring strength remains exactly zero")

    def _add_force_constitution(self):
        import uipc
        from uipc.backend import SceneVisitor
        from uipc.constitution import FiniteElementExternalForce
        self.original_add()
        index = next(i for i, entity in enumerate(self.coupler.fem_solver.entities) if entity is self.rope)
        objects = self.coupler._ipc_objects.find(f"fem_{index}_0")
        if len(objects) != 1:
            raise RuntimeError("Damping requires exactly one native rope object")
        obj = objects[0]
        ids = obj.geometries().ids()
        if len(ids) != 1:
            raise RuntimeError("Damping requires one tetrahedral mesh")
        self.constitution = FiniteElementExternalForce()
        self.coupler._ipc_constitution_tabular.insert(self.constitution)
        visitor = SceneVisitor(self.coupler._ipc_scene)
        for slots in (visitor.geometries(), visitor.rest_geometries()):
            mesh = next(slot.geometry() for slot in slots if slot.id() == ids[0])
            self.constitution.apply_to(mesh, np.zeros(3))
            uipc.view(mesh.vertices().find(uipc.builtin.is_constrained)).reshape(-1)[:] = 1
            strength = mesh.vertices().find("strength_ratio")
            if strength:
                uipc.view(strength).reshape(-1)[:] = 0.
        animator = self.coupler._ipc_animator
        if animator.has_animation(obj.id()):
            animator.erase(obj.id())
        animator.insert(obj, self._animate_force_and_grasps)

    def _animate_force_and_grasps(self, info):
        import uipc
        from topogym.world.genesis_ipc_vertex_constraints import _SPECS
        mesh = info.geo_slots()[0].geometry()
        # UID 671 and UID 14 share this flag. All vertices receive forces,
        # but only an engaged grasp receives nonzero position stiffness.
        uipc.view(mesh.vertices().find(uipc.builtin.is_constrained)).reshape(-1)[:] = 1
        uipc.view(mesh.vertices().find("external_force")).reshape(-1, 3)[:] = self.force
        strength_attr = mesh.vertices().find("strength_ratio")
        if strength_attr:
            strength = uipc.view(strength_attr).reshape(-1)
            strength[:] = 0.
            aim = uipc.view(mesh.vertices().find(uipc.builtin.aim_position)).reshape(-1, 3)
            spec = _SPECS[str(self.rope.uid)]
            if spec.follow_verts is not None:
                for band, indices in enumerate(spec.follow_verts):
                    if spec.engaged[band] and spec.targets[band] is not None:
                        strength[indices] = spec.follow_selectors[band][2]
                        aim[indices] = spec.targets[band]
        self.applied_steps = self.prepared_steps

    def start(self):
        import torch
        import uipc
        self.coupler._add_fem_entities_to_ipc = self.original_add
        self.feature = self.coupler._ipc_world.features().find(uipc.core.FiniteElementStateAccessorFeature)
        if self.feature.vertex_count() != len(self.mass):
            raise ValueError("This task-local damping supports a single FEM rope")
        self.buffers = [torch.empty((len(self.mass), 3), dtype=torch.float64, device="cuda") for _ in range(2)]
        self.views = [uipc.backend.BufferView(b.data_ptr(), 0, len(self.mass), 24, 24, "cuda") for b in self.buffers]
        original = self.coupler.couple

        def step(f):
            self.feature.copy_position_to(self.views[0], 0, len(self.mass))
            self.feature.copy_velocity_to(self.views[1], 0, len(self.mass))
            torch.cuda.synchronize()
            x, v = (b.cpu().numpy().copy() for b in self.buffers)
            self.force, audit = dissipative_forces(x, v, self.mass, self.rate, self.dt)
            self.work_j -= audit["power_w"]*self.dt
            for name in self.maxima:
                self.maxima[name] = max(self.maxima[name], audit[name])
            self.prepared_steps += 1
            original(f)
            if self.applied_steps != self.prepared_steps:
                raise RuntimeError("Native damping callback was not applied to this substep")

        self.coupler.couple = step

    def report(self, observed_steps):
        checks = dict(applied_every_native_substep=self.applied_steps == observed_steps > 0,
            nonpositive_power=self.maxima["power_w"] <= 1.e-12,
            nonpositive_force_only_energy_change=self.maxima["force_only_kinetic_change_j"] <= 1.e-12,
            zero_net_force=self.maxima["net_force_n"] <= 1.e-9,
            zero_net_torque=self.maxima["net_torque_nm"] <= 1.e-9)
        return dict(**self.specification(), checks=checks, passed=all(checks.values()),
            applied_native_steps=self.applied_steps, dissipated_work_j=self.work_j, maxima=self.maxima,
            scope="damping-load audit only; not a complete elastic/contact energy balance")
