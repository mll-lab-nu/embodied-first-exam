"""Genesis 1.2.1 rigid grasp adapter, including complete equality compaction.

Real constraint verification adapted from historical robot/grasp_constraints.py
at cb60f01b32786cc9c26f754f91b7be4bef3f9ca6. Never resets object poses.
"""
from dataclasses import fields
from importlib.metadata import version
import numpy as np
from topogym.utils.arrays import to_numpy
from topogym.utils.grasp import bilateral_contact_rows, closed_fraction, relative_pose, relative_error, rotation


EQUALITY_FIELDS = {"eq_obj1id", "eq_obj2id", "eq_data", "eq_type", "sol_params"}


def delete_weld_preserving_others(solver, link_a, link_b):
    """Compact the complete last equality row, not just its type (1.2.1 bug).

    Scene-local adapter; no global monkeypatch and no release/reacquire of peers.
    Solver recomputes equality Jacobians on the next normal physics substep.
    """
    if version("genesis-world").split("+")[0] != "1.2.1":
        raise RuntimeError("Weld deletion adapter requires Genesis 1.2.1")
    info, constraint = solver.equalities_info, solver.constraint_solver
    if {f.name for f in fields(info)} != EQUALITY_FIELDS:
        raise RuntimeError("Unsupported Genesis equality layout")
    arrays = {name: getattr(info, name).to_numpy() for name in EQUALITY_FIELDS}
    count_field = constraint.constraint_state.qd_n_equalities
    counts = count_field.to_numpy()
    if counts.shape != (1,):
        raise ValueError("Grasp adapter requires an unbatched world")
    count = int(counts[0])
    static_count = int(solver._rigid_global_info.n_equalities.to_numpy())
    import genesis as gs
    matches = [i for i in range(static_count, count)
               if arrays["eq_type"][i, 0] == int(gs.EQUALITY_TYPE.WELD)
               and arrays["eq_obj1id"][i, 0] == link_a and arrays["eq_obj2id"][i, 0] == link_b]
    if len(matches) != 1:
        raise RuntimeError("Expected exactly one owned dynamic weld to remove")
    slot = matches[0]
    if slot != count-1:
        for name, array in arrays.items():
            array[slot, 0] = array[count-1, 0].copy()
            getattr(info, name).from_numpy(array)
    counts[0] -= 1
    count_field.from_numpy(counts)
    constraint._eq_const_info_cache.clear()


class RigidGraspBackend:
    def __init__(self, world, robot, config):
        self.world, self.robot, self.config = world, robot, config
        self.solver = world.scene.sim.rigid_solver
        self._pairs = None
        if hasattr(world.scene.sim.coupler, "checkpoint_store"):
            raise ValueError("contact_weld_v1 does not support IPC scenes")
        self.hands = {}
        for name, group in robot.groups.items():
            if group.grasp is None:
                raise ValueError(f"No grasp geometry declared for {name}")
            self.hands[name] = (robot.entity.get_link(group.hand_link),
                               tuple(robot.entity.get_link(n).idx for n in group.grasp.finger_links))
        self.targets, self._evidence = {}, {}
        robot_links = {l.idx for l in robot.entity.links}
        for spec in config.targets:
            entity = world.entities[spec.entity]
            if not hasattr(entity, "links") or spec.entity == "robot":
                raise ValueError("Grasp target must be a task rigid link")
            link = entity.get_link(spec.link)
            if link.idx in robot_links or link.is_fixed or entity.n_dofs == 0 or getattr(entity.material, "coup_type", None) == "ipc_only":
                raise ValueError("Fixed, robot or IPC-only targets cannot use rigid grasp")
            self.targets[spec.key] = (spec, link)
        capacity = int(self.solver._rigid_global_info.n_candidate_equalities.to_numpy())
        current = int(self.solver.constraint_solver.constraint_state.qd_n_equalities.to_numpy()[0])
        if capacity-current < len(self.hands):
            raise ValueError("Insufficient reserved dynamic grasp constraint capacity")

    def fraction(self, hand):
        group = self.robot.groups[hand]
        value = self.robot.capture_state().targets[hand][group.gripper_field]
        return closed_fraction(value, group.grasp.open_position, group.grasp.closed_position)

    def relative_pose(self, hand, target):
        parent = self.hands[hand][0]
        child = self.targets[tuple(target)][1]
        return relative_pose(to_numpy(parent.get_pos()).reshape(3), to_numpy(parent.get_quat()).reshape(4),
                             to_numpy(child.get_pos()).reshape(3), to_numpy(child.get_quat()).reshape(4))

    def finger_fractions(self, hand):
        group = self.robot.groups[hand]
        q = to_numpy(self.robot.entity.get_qpos()).reshape(-1)
        values = [q[self.robot.entity.get_joint(n).qs_idx_local[0]] for n in group.finger_joints]
        return [closed_fraction(v, group.grasp.open_position, group.grasp.closed_position) for v in values]

    def health_reason(self, binding):
        actual = np.asarray(self.finger_fractions(binding["hand"]))
        captured = np.asarray(binding["finger_fractions"])
        if np.max(captured-actual) > self.config.max_finger_opening_fraction:
            return "physical_fingers_opened"
        return None

    def check_health(self, binding):
        reason = self.health_reason(binding)
        translation, angle = relative_error(binding["relative_pose"], self.relative_pose(binding["hand"], binding["target"]))
        if translation > self.config.max_translation_error_m or angle > self.config.max_rotation_error_rad:
            reason = "relative_pose_error"
        return reason

    def candidates(self, hand):
        # Force a current final-substep snapshot, never a cached earlier query.
        collider = self.solver.collider
        collider._contact_data_cache.clear()
        contacts = {k: to_numpy(v) for k, v in collider.get_contacts().items()}
        parent, fingers = self.hands[hand]
        group = self.robot.groups[hand]
        tcp = to_numpy(parent.get_pos()).reshape(3) + rotation(to_numpy(parent.get_quat()).reshape(4)).apply(group.tcp_position_in_hand_m)
        result = []
        for key, (spec, link) in self.targets.items():
            center = to_numpy(link.get_pos()).reshape(3) + rotation(to_numpy(link.get_quat()).reshape(4)).apply(spec.center_m)
            if np.linalg.norm(center-tcp) > self.config.max_tcp_distance_m:
                continue
            rows = bilateral_contact_rows(contacts, fingers, link.idx, center_m=center,
                radius_m=spec.radius_m, max_penetration_m=self.config.max_penetration_m)
            if rows:
                result.append(key)
                self._evidence[hand, key] = dict(
                    physics_step=self.world.physics_step,
                    source="genesis_rigid_final_substep", rows=[dict(
                        link_a=int(contacts["link_a"][i]), link_b=int(contacts["link_b"][i]),
                        position_m=contacts["position"][i].tolist(),
                        penetration_m=float(contacts["penetration"][i]),
                        force_n=contacts["force"][i].tolist()) for i in rows])
        return sorted(result)

    def pairs(self):
        # The solver's welds change only in acquire / release and in a world restore, which ends in verify_bindings; those
        # three drop this cache, so exists() (every tick per held hand) reuses one solver read between them.
        if self._pairs is None:
            values = self.solver.get_weld_constraints(as_tensor=True, to_torch=True)
            self._pairs = [(int(a), int(b)) for a, b in zip(to_numpy(values["link_a"]).ravel(),
                           to_numpy(values["link_b"]).ravel()) if a >= 0 and b >= 0]
        return list(self._pairs)

    def acquire(self, hand, target):
        a, b = self.hands[hand][0].idx, self.targets[tuple(target)][1].idx
        reference = self.relative_pose(hand, target)
        self._pairs = None
        before = self.pairs()
        if (a, b) in before or (b, a) in before:
            raise RuntimeError("Grasp pair already constrained")
        self._pairs = None
        self.solver.add_weld_constraint(a, b)
        if sorted(self.pairs()) != sorted([*before, (a, b)]):
            raise RuntimeError("Weld acquisition did not create the expected real constraint")
        return dict(hand=hand, target=tuple(target), links=(a, b), relative_pose=reference,
                    finger_fractions=self.finger_fractions(hand),
                    acquisition_evidence=self._evidence[hand, tuple(target)])

    def exists(self, binding):
        return tuple(binding["links"]) in self.pairs()

    def release(self, binding):
        pair = tuple(binding["links"])
        self._pairs = None
        expected = self.pairs()
        expected.remove(pair)
        self._pairs = None
        delete_weld_preserving_others(self.solver, *pair)
        if sorted(self.pairs()) != sorted(expected):
            raise RuntimeError("Grasp release changed unrelated constraints")

    def verify_bindings(self, bindings):
        self._pairs = None
        expected = sorted(tuple(b["links"]) for b in bindings)
        hands = {h.idx for h, _ in self.hands.values()}
        actual = sorted(pair for pair in self.pairs() if pair[0] in hands or pair[1] in hands)
        if actual != expected:
            raise ValueError("Restored grasp ownership differs from real constraints")
