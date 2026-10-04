"""Knot FEM declaration with straight material coordinates and native IPC history."""

from pathlib import Path
import numpy as np
from topogym.utils.geometry.rope import load_centerline_map, sample_material_centerline
from topogym.utils.geometry.passage import planar_clearance
from topogym.evaluation.task_metrics import soft_speed, ipc_integrity
from topogym.assets.geometry.knot_untying import KnotLayout, generate_assets
from topogym.assets.materials import rope_fem_parameters, rope_ipc_parameters
from topogym.assets.geometry.rope_volume import write_rope_volume
from ..base import TaskDefinition, EntitySpec, TaskSpec
from ..scene_presets import defaults, record_preset
from topogym.assets.scene_visuals import surface


class KnotUntyingTask(TaskDefinition):
    task_id = "knot_untying"
    instruction = 'Untangle the rope and leave it still on the table with no projected crossings or overlapping segments.'
    terminal_revision = "terminal_v5_fixed_contact_active_clearance_1mm"
    physics_model = "fem_ipc"
    defaults = defaults(task_id, geometry={}, stable_duration_s=0.5,
        origin_xy_m=[0., 0.], yaw_deg=0., rope_finish="orange_rope",
        terminal=dict(maximum_speed_m_s=.001, table_clearance_m=.003, penetration_tolerance_m=.001))
    hash_when_changed = ("origin_xy_m", "yaw_deg", "rope_finish")

    def final_settling_spec(self):
        from topogym.evaluation.terminal import SettlingSpec
        return SettlingSpec(fem_targets=("rope",), clearance_m=.001,
            robot_contact_policy="fixed_contact_active_clearance_v1",
            maximum_speed_m_s=self.config["terminal"]["maximum_speed_m_s"])

    def declare(self, asset_dir, table_height_m):
        self.table_height_m = float(table_height_m)
        preset = record_preset(self, asset_dir)
        self.layout, report = generate_assets(
            asset_dir, KnotLayout(**self.config["geometry"])
        )
        volume = write_rope_volume(Path(asset_dir) / "rope_volume.npz", self.layout.centerline(), self.layout.rope_radius_m)
        origin = np.asarray(self.config["origin_xy_m"], dtype=float)
        yaw = float(self.config["yaw_deg"])
        if origin.shape != (2,) or not np.isfinite(origin).all() or not np.isfinite(yaw):
            raise ValueError("Invalid Knot origin_xy_m or yaw_deg")
        mesh_path = Path(asset_dir) / "rope.obj"
        if yaw:
            # FEM volumes keep identity orientation: bake the turn into the skin and
            # the spawn (as Orbits does). The generator's own files stay untouched.
            import trimesh
            from scipy.spatial.transform import Rotation
            rotation = Rotation.from_euler("z", yaw, degrees=True)
            matrix = np.eye(4); matrix[:3, :3] = rotation.as_matrix()
            mesh = trimesh.load(mesh_path, force="mesh", process=False)
            mesh.apply_transform(matrix)
            mesh_path = Path(asset_dir) / "rope_posed.obj"
            mesh.export(mesh_path)
            with np.load(volume) as source:
                data = {key: source[key] for key in source.files}
            for key in ("spawn", "centerline"):
                data[key] = rotation.apply(data[key])
            np.savez_compressed(volume, **data)
        self.centerline_map = load_centerline_map(volume)
        entity = EntitySpec(
            "rope",
            "mesh",
            mesh_path,
            (origin[0], origin[1], table_height_m),
            physics_model="fem_elastic",
            volume_path=volume,
            material=rope_fem_parameters(),
            surface=surface(self.config["rope_finish"]),
            morph_options={"convexify": False, "decimate": False},
        )
        return TaskSpec(
            (entity,),
            # 1 mm/s friction smoothing (as the v9 demo): with the libuipc default
            # 10 mm/s a released curved rope creeps ~3 mm/s and never meets the
            # 1 mm/s quiet terminal check.
            {"fem": {}, "ipc": dict(rope_ipc_parameters(), contact_eps_velocity=.001)},
            dict(
                **preset,
                task_id=self.task_id,
                fem_rope_profile="v13_material_mesh",
                geometry_report=report,
                required_reference_shape="straight",
                goal_evaluation_complete=bool(self.goal_complete),
            ),
        )

    def evaluate_state(self, state):
        soft = state["fem"]["rope"]
        points = sample_material_centerline(soft, *self.centerline_map)
        indices, material_s = self.centerline_map
        radius, cfg = self.layout.rope_radius_m, self.config["terminal"]
        stations = material_s[indices]
        if stations.ndim == 2:
            stations = stations.mean(axis=1)
        clear, geometry = planar_clearance(points, stations, 2*radius)
        z = np.asarray(soft["position_m"])[:, 2]
        on_table = bool(z.min() >= self.table_height_m-cfg["penetration_tolerance_m"]
                        and z.max() <= self.table_height_m+2*radius+cfg["table_clearance_m"])
        quiet, speed = soft_speed(soft, cfg["maximum_speed_m_s"])
        intact = ipc_integrity(state, ("rope",))
        return (bool(clear and on_table and quiet and intact is True),
                "rope_volume_invalid" if intact is False else None,
                dict(planar_clear=bool(clear), on_table=on_table, quiet=quiet, **geometry, **speed,
                     evaluation_status="available" if intact is not None else "unavailable",
                     thresholds_calibrated=False, goal_evaluation_complete=bool(self.goal_complete)))
