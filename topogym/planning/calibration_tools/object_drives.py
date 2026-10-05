"""Opt-in native IPC external forces, declared before build in a private worker.

No pose setter, new integrator, robot action change or shared physics patch.
"""
from copy import deepcopy
from uuid import uuid4

import numpy as np

from .contracts import UnsupportedCapability, positive_int, json_value


def vector(value, label):
    x = np.asarray(value)
    if x.shape != (3,) or x.dtype.kind not in "fiu" or not np.isfinite(x).all():
        raise ValueError(label+" requires three finite numbers")
    return x.astype(float)


def force_command(position, velocity, target, *, kp, kd, maximum):
    value = kp*(np.asarray(target)-position)-kd*velocity
    norm = float(np.linalg.norm(value))
    return value*min(1., maximum/norm) if norm else value


def declare_force(geometry, kind):
    """Pure native geometry declaration, independently testable without a World."""
    from uipc.constitution import AffineBodyExternalBodyForce, FiniteElementExternalForce
    if kind not in {"rigid", "fem"}:
        raise ValueError("Expected rigid or fem force declaration")
    cls = AffineBodyExternalBodyForce if kind == "rigid" else FiniteElementExternalForce
    constitution = cls()
    constitution.apply_to(geometry, np.zeros(3))
    collection = geometry.instances() if kind == "rigid" else geometry.vertices()
    return constitution, collection.find("external_force")


class ObjectDrives:
    def __init__(self, owner, declarations):
        self.owner, self.declarations = owner, dict(declarations)
        self.slots = {}
        self.active = False

    def install(self, world):
        if not self.declarations:
            return
        coupler = world.scene.sim.coupler
        if not hasattr(coupler, "_finalize_ipc") or not hasattr(coupler, "fem_slots"):
            raise UnsupportedCapability("object_drives currently requires the pinned FEM/IPC backend")
        self.owner.profiler.wrap(coupler, "_finalize_ipc", "object_drive_declaration",
                                 before=lambda: self._declare(world))

    def _declare(self, world):
        from uipc.backend import SceneVisitor
        coupler = world.scene.sim.coupler
        rest = {slot.id(): slot for slot in SceneVisitor(coupler._ipc_scene).rest_geometries()}
        inserted = set()
        for name, kind in self.declarations.items():
            if name not in world.entities or name in {"robot", "table"}:
                raise ValueError("Declare a task object for external driving: "+name)
            entity = world.entities[name]
            if kind == "fem":
                slot = coupler.fem_slots.get(entity)
                if slot is None:
                    raise UnsupportedCapability("No IPC FEM geometry for "+name)
            else:
                if (getattr(entity.material, "coup_type", None) != "ipc_only" or
                        len(entity.links) != 1 or entity.base_link.is_fixed):
                    raise UnsupportedCapability("Rigid drive requires one dynamic ipc_only body: "+name)
                slots = coupler._abd_slots_by_link.get(entity.base_link, ())
                if len(slots) != 1:
                    raise UnsupportedCapability("Rigid drive requires a single environment")
                slot = slots[0]
            constitution, attribute = declare_force(slot.geometry(), kind)
            if kind not in inserted:
                coupler._ipc_constitution_tabular.insert(constitution)
                inserted.add(kind)
            if slot.id() in rest:
                declare_force(rest[slot.id()].geometry(), kind)
            flags = slot.geometry().instances().find("is_constrained") if kind == "rigid" else None
            if flags is not None and np.any(np.asarray(flags.view())):
                raise UnsupportedCapability("External driving cannot take ownership of an existing rigid constraint")
            self.slots[name] = dict(kind=kind, attribute=attribute, flags=flags)

    def capabilities(self):
        return dict(declared=deepcopy(self.declarations), ready=list(self.slots),
            modes=["constant_world_force", "bounded_position_pd", "bounded_vertex_group_pd"],
            native_backend="libuipc external force constitutions",
            orientation_drive=False, direct_pose_setter=False, physical_acceptance=False)

    def clear(self):
        if not self.slots:
            return
        import uipc
        for row in self.slots.values():
            uipc.view(row["attribute"])[:] = 0
            if row.get("flags") is not None:
                uipc.view(row["flags"])[:] = 0

    def set_force(self, name, force, indices):
        import uipc
        row = self.slots[name]
        values = uipc.view(row["attribute"])
        values[:] = 0
        if row["kind"] == "rigid":
            values.reshape(-1, 12)[:, :3] = force
            if row.get("flags") is not None:
                uipc.view(row["flags"])[:] = 1
        else:
            # force_world_n means total force, not an unintended per-vertex multiplier.
            values.reshape(-1, 3)[indices] = force/len(indices)

    def set_vertex_forces(self, name, forces):
        """Per-vertex world forces (N, 3) on a FEM entity; replaces the previous command."""
        import uipc
        row = self.slots[name]
        if row["kind"] != "fem":
            raise ValueError("Per-vertex forces apply to FEM entities")
        values = uipc.view(row["attribute"]).reshape(-1, 3)
        forces = np.asarray(forces)
        if forces.shape != values.shape or forces.dtype.kind not in "fiu" or not np.isfinite(forces).all():
            raise ValueError("Per-vertex forces must match the FEM vertex array and be finite")
        values[:] = forces

    def measured(self, name, indices):
        world = self.owner.runner._last_tick["world"]
        if self.slots[name]["kind"] == "rigid":
            body = world["bodies"][name]
            return vector(body["position_m"], "measured position"), vector(body["linear_velocity_m_s"], "measured velocity")
        fem = world["fem"][name]
        return (vector(np.asarray(fem["position_m"])[indices].mean(0), "measured centroid"),
                vector(np.asarray(fem["velocity_m_s"])[indices].mean(0), "measured velocity"))

    def run(self, entity, *, control_steps, max_force_n, force_world_n=None,
            positions_world_m=None, vertex_indices=None, kp_n_per_m=100., kd_ns_per_m=5.):
        owner = self.owner
        owner.need_physics()
        if entity not in self.slots:
            raise UnsupportedCapability("Declare candidate.object_drives for this entity before building a fresh session")
        if self.active:
            raise ValueError("Object drive is already active")
        positive_int(control_steps, "control_steps", 10000)
        for label, value in (("max_force_n", max_force_n), ("kp_n_per_m", kp_n_per_m), ("kd_ns_per_m", kd_ns_per_m)):
            if isinstance(value, bool) or not np.isfinite(value) or value < 0 or label == "max_force_n" and value == 0:
                raise ValueError(label+" must be finite, with positive max_force_n and nonnegative gains")
        if (force_world_n is None) == (positions_world_m is None):
            raise ValueError("Choose force_world_n or positions_world_m")
        force = vector(force_world_n, "force_world_n") if force_world_n is not None else None
        if force is not None and np.linalg.norm(force) > max_force_n:
            raise ValueError("Requested force exceeds max_force_n")
        goals = None
        if positions_world_m is not None:
            positive_int(len(positions_world_m), "positions_world_m", control_steps)
            goals = [vector(v, "target position") for v in positions_world_m]
        kind = self.slots[entity]["kind"]
        if kind == "rigid":
            if vertex_indices is not None:
                raise ValueError("vertex_indices only applies to FEM")
            indices = None
        else:
            count = len(owner.runner._last_tick["world"]["fem"][entity]["position_m"])
            if (not isinstance(vertex_indices, list) or not vertex_indices or
                any(type(i) is not int or not 0 <= i < count for i in vertex_indices) or
                len(set(vertex_indices)) != len(vertex_indices)):
                raise ValueError("Select distinct in-range FEM vertex_indices explicitly")
            indices = vertex_indices
        start, _ = self.measured(entity, indices)
        knots = [start, *goals] if goals is not None else None
        identifier = uuid4().hex
        owner.evidence.event("object_drive_started", intervention=True, drive_id=identifier, entity=entity,
            control_steps=control_steps, force_world_n=force_world_n, positions_world_m=positions_world_m,
            vertex_indices=indices, max_force_n=max_force_n, kp_n_per_m=kp_n_per_m, kd_ns_per_m=kd_ns_per_m)
        self.active, rows, reason = True, [], "control_step_limit"
        try:
            for index in range(control_steps):
                if owner.cancelled():
                    reason = "cancelled"
                    break
                p, v = self.measured(entity, indices)
                target = None
                command = force
                if knots is not None:
                    progress = (index+1)/control_steps*(len(knots)-1)
                    segment = min(int(progress), len(knots)-2)
                    fraction = progress-segment
                    target = (1-fraction)*knots[segment]+fraction*knots[segment+1]
                    command = force_command(p, v, target, kp=kp_n_per_m, kd=kd_ns_per_m, maximum=max_force_n)
                self.set_force(entity, command, indices)
                owner.evidence.event("object_drive_command", intervention=True, drive_id=identifier,
                    index=index, source_state_ref=owner.state_ref(), force_world_n=command,
                    target_position_world_m=target)
                result = owner.step({})
                current, _ = self.measured(entity, indices)
                row = dict(index=index, state_ref=owner.state_ref(), force_world_n=command,
                    target_position_world_m=target, measured_position_world_m=current,
                    completed_control_steps=result["control_steps"], physics_ticks=result["physics_steps"],
                    reason=result["reason"])
                rows.append(json_value(row))
                owner.evidence.event("object_drive_sample", intervention=True, drive_id=identifier, **row)
                if result["control_steps"] != 1 or owner.env._terminated or owner.env._truncated:
                    reason = result["reason"]
                    break
        except BaseException:
            reason = "execution_error"
            raise
        finally:
            try:
                self.clear()
                # A completed development operation never leaves a persistent force in its checkpoint.
                if not getattr(owner.env, "_faulted", False):
                    owner.env._checkpoint_current()
            except BaseException:
                owner.poisoned = True
                raise
            finally:
                self.active = False
                owner.evidence.event("object_drive_finished", intervention=True, drive_id=identifier,
                                     recorded_samples=len(rows), reason=reason)
        return dict(drive_id=identifier, entity=entity, reason=reason, samples=rows,
            external_force_cleared=True, robot_actions="hold existing targets", formal_qualification=False,
            scope="same IPC model with explicit external force; not robot completion or a kinematic teleport")

    def run_groups(self, entity, *, groups, control_steps, max_force_n, kp_n_per_m=100., kd_ns_per_m=5.,
                   record_every=10):
        """Several FEM vertex groups driven at once, e.g. two virtual point grippers on a cord.

        groups: [{"vertex_indices": [...], "targets_world_m": [xyz or None] * control_steps}]. At control
        step i each group whose target is not None gets its own bounded PD force (on its centroid, shared
        equally by its vertices); None leaves that group free (released). Robot targets are held.
        """
        owner = self.owner
        owner.need_physics()
        if entity not in self.slots or self.slots[entity]["kind"] != "fem":
            raise UnsupportedCapability("Declare candidate.object_drives {entity: 'fem'} before building a fresh session")
        if self.active:
            raise ValueError("Object drive is already active")
        positive_int(control_steps, "control_steps", 10000)
        positive_int(record_every, "record_every", 10000)
        for label, value in (("max_force_n", max_force_n), ("kp_n_per_m", kp_n_per_m), ("kd_ns_per_m", kd_ns_per_m)):
            if isinstance(value, bool) or not np.isfinite(value) or value < 0 or label == "max_force_n" and value == 0:
                raise ValueError(label+" must be finite, with positive max_force_n and nonnegative gains")
        count = len(owner.runner._last_tick["world"]["fem"][entity]["position_m"])
        if not isinstance(groups, list) or not groups:
            raise ValueError("groups must be a nonempty list")
        plan, selected = [], set()
        for g in groups:
            idx = g.get("vertex_indices") if isinstance(g, dict) else None
            if (not isinstance(idx, list) or not idx or any(type(i) is not int or not 0 <= i < count for i in idx)
                    or len(set(idx)) != len(idx)):
                raise ValueError("Each group needs distinct in-range FEM vertex_indices")
            if selected.intersection(idx):
                raise ValueError("FEM vertex groups must not overlap")
            selected.update(idx)
            targets = g.get("targets_world_m")
            if not isinstance(targets, list) or len(targets) != control_steps:
                raise ValueError("Each group needs one target (or None) per control step")
            plan.append((idx, [None if t is None else vector(t, "target position") for t in targets]))
        identifier = uuid4().hex
        owner.evidence.event("object_drive_started", intervention=True, drive_id=identifier, entity=entity,
            control_steps=control_steps, groups=[dict(vertex_indices=i) for i, _ in plan],
            max_force_n=max_force_n, kp_n_per_m=kp_n_per_m, kd_ns_per_m=kd_ns_per_m, mode="groups")
        self.active, rows, reason = True, [], "control_step_limit"
        try:
            for index in range(control_steps):
                if owner.cancelled():
                    reason = "cancelled"
                    break
                forces = np.zeros((count, 3))
                commands = []
                for idx, targets in plan:
                    if targets[index] is None:
                        commands.append(None)
                        continue
                    p, v = self.measured(entity, idx)
                    f = force_command(p, v, targets[index], kp=kp_n_per_m, kd=kd_ns_per_m, maximum=max_force_n)
                    forces[idx] += f/len(idx)
                    commands.append(f.tolist())
                self.set_vertex_forces(entity, forces)
                owner.evidence.event("object_drive_command", intervention=True, drive_id=identifier,
                    index=index, source_state_ref=owner.state_ref(), group_forces_world_n=commands,
                    target_world_m=[None if t[index] is None else t[index].tolist() for _, t in plan])
                result = owner.step({})
                if index % record_every == 0 or index == control_steps-1:
                    measured = [None if t[index] is None else self.measured(entity, i)[0].tolist() for i, t in plan]
                    row = json_value(dict(index=index, state_ref=owner.state_ref(), measured_world_m=measured,
                        target_world_m=[None if t[index] is None else t[index].tolist() for _, t in plan],
                        group_forces_world_n=commands, completed_control_steps=result["control_steps"],
                        physics_ticks=result["physics_steps"], reason=result["reason"]))
                    rows.append(row)
                    owner.evidence.event("object_drive_sample", intervention=True, drive_id=identifier, **row)
                if result["control_steps"] != 1 or owner.env._terminated or owner.env._truncated:
                    reason = result["reason"]
                    break
        except BaseException:
            reason = "execution_error"
            raise
        finally:
            try:
                self.clear()
                if not getattr(owner.env, "_faulted", False):
                    owner.env._checkpoint_current()
            except BaseException:
                owner.poisoned = True
                raise
            finally:
                self.active = False
                owner.evidence.event("object_drive_finished", intervention=True, drive_id=identifier,
                                     recorded_samples=len(rows), reason=reason)
        return dict(drive_id=identifier, entity=entity, reason=reason, samples=rows,
            external_force_cleared=True, robot_actions="hold existing targets", formal_qualification=False,
            scope="same IPC model with explicit external forces on vertex groups; not robot completion")
