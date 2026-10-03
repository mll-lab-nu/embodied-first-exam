"""Read-only Genesis/IPC pose, collision-surface and joint-limit measurements.

Intended for trusted development owners. Native contact forces are deliberately
not inferred from surface proximity. No pose, constraint or clock is modified.
"""
import numpy as np
from scipy.spatial.transform import Rotation

from topogym.utils.arrays import to_numpy


def transform_error(native, reference, local_vertices):
    """Compare an affine IPC body to the corresponding Genesis link frame."""
    native, reference = np.asarray(native), np.asarray(reference)
    linear = native[:3, :3]
    u, scale, vt = np.linalg.svd(linear)
    orientation = u @ np.diag([1., 1., np.linalg.det(u @ vt)]) @ vt
    points = np.asarray(local_vertices).reshape(-1, 3)
    delta = points @ (linear-reference[:3, :3]).T + native[:3, 3]-reference[:3, 3]
    return dict(position_error_m=float(np.linalg.norm(native[:3, 3]-reference[:3, 3])),
                orientation_error_rad=float(Rotation.from_matrix(orientation @ reference[:3, :3].T).magnitude()),
                affine_stretch_error=float(np.max(np.abs(scale-1.))),
                collision_vertex_error_m=float(np.linalg.norm(delta, axis=1).max()) if len(points) else None)


def limit_error(value, lower, upper):
    """Physical coordinate limits; this is independent of command limits."""
    if not np.isfinite(value) or np.isnan(lower) or np.isnan(upper) or lower > upper:
        raise ValueError('Joint coordinates must be finite and limits ordered')
    return dict(below_lower=max(0., float(lower-value)),
                above_upper=max(0., float(value-upper)),
                violation=max(0., float(lower-value), float(value-upper)))


class IPCDiagnostics:
    def __init__(self, env):
        self.env = env
        self.world, self.robot = env._world, env._robot
        self.coupler = self.world.scene.sim.coupler
        if not hasattr(self.coupler, '_abd_state_geom'):
            raise ValueError('This diagnostic requires the supported native IPC adapter')
        self.links = list(self.coupler._abd_slots_by_link)
        self.local_vertices = {}
        for link, slots in self.coupler._abd_slots_by_link.items():
            if len(slots) != 1:
                raise ValueError('Only the unbatched IPC layout is supported')
            self.local_vertices[link] = np.asarray(slots[0].geometry().positions().view()).reshape(-1, 3).copy()

    def sample(self):
        import uipc
        from genesis.utils.misc import qd_to_numpy
        solver = self.world.scene.sim.rigid_solver
        positions = qd_to_numpy(solver.links_state.pos, transpose=True)[0]
        quaternions = qd_to_numpy(solver.links_state.quat, transpose=True)[0]
        transforms = np.asarray(self.coupler._abd_state_geom.instances().find(uipc.builtin.transform).view())
        bodies = []
        for index, link in enumerate(self.links):
            reference = np.eye(4)
            reference[:3, 3] = positions[link.idx]
            reference[:3, :3] = Rotation.from_quat(quaternions[link.idx][[1, 2, 3, 0]]).as_matrix()
            bodies.append(dict(entity=link.entity.name, link=link.name,
                **transform_error(transforms[index], reference, self.local_vertices[link])))
        q = to_numpy(self.robot.entity.get_qpos()).reshape(-1)
        targets = self.robot.capture_state().targets
        fingers = []
        for hand, group in self.robot.groups.items():
            for name in group.finger_joints:
                joint = self.robot.entity.get_joint(name)
                limits = np.asarray(joint.dofs_limit).reshape(-1, 2)[0]
                value = float(q[joint.qs_idx_local[0]])
                unit = 'm' if str(group.gripper_field).endswith('_m') else 'rad'
                violation = limit_error(value, *limits)
                fingers.append(dict(hand=hand, joint=name, unit=unit, actual=value,
                    physical_lower=float(limits[0]), physical_upper=float(limits[1]),
                    command=float(targets[hand][group.gripper_field]),
                    command_limits=list(group.gripper_limits),
                    violation=float(violation['violation'])))
        return dict(physics_step=self.world.physics_step,
                    native_frame=int(self.coupler._ipc_world.frame()),
                    native_valid=bool(self.coupler._ipc_world.is_valid()), bodies=bodies, fingers=fingers,
                    contact_force_coverage=False,
                    surface_comparison='same native local collision vertices transformed by both body frames')

    def export_collision_meshes(self, output):
        """Export actual built IPC and Genesis finger surfaces, with provenance."""
        from pathlib import Path
        import trimesh
        import uipc
        output = Path(output)
        output.mkdir(parents=True, exist_ok=False)
        transforms = np.asarray(self.coupler._abd_state_geom.instances().find(uipc.builtin.transform).view())
        result = []
        for group in self.robot.groups.values():
            for name in group.grasp.finger_links:
                link = self.robot.entity.get_link(name)
                if link not in self.local_vertices:
                    continue
                slot = self.coupler._abd_slots_by_link[link][0].geometry()
                local = self.local_vertices[link]
                triangles = np.asarray(slot.triangles().find(uipc.builtin.topo).view()).reshape(-1, 3)
                transform = transforms[self.links.index(link)]
                native = local @ transform[:3, :3].T + transform[:3, 3]
                stem = name.replace('/', '_')
                native_path = output / (stem+'_ipc.ply')
                trimesh.Trimesh(native, triangles, process=False).export(native_path)
                meshes = [trimesh.Trimesh(to_numpy(g.get_verts()).reshape(-1, 3),
                                         np.asarray(g.init_faces), process=False) for g in link.geoms]
                genesis_path = output / (stem+'_genesis.ply')
                trimesh.util.concatenate(meshes).export(genesis_path)
                result.append(dict(link=name, ipc=str(native_path), genesis=str(genesis_path),
                                   native_vertices=len(native), native_triangles=len(triangles)))
        return result
