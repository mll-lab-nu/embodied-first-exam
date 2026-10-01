"""Threading FEM rope and rigid ring declarations; no second simulation backend."""

from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
from topogym.utils.geometry.rope import load_centerline_map, sample_material_centerline
from topogym.utils.geometry.passage import aperture_crossings
from topogym.evaluation.task_metrics import body_points, soft_speed, ipc_integrity
from topogym.assets.geometry.rope_threading import ThreadingLayout, generate_assets
from topogym.assets.materials import rope_fem_parameters, rope_ipc_parameters
from topogym.assets.geometry.rope_volume import write_rope_volume
from ..base import TaskDefinition, EntitySpec, TaskSpec
from ..scene_presets import defaults, record_preset, PRESETS
from topogym.assets.scene_visuals import surface


class RopeThreadingTask(TaskDefinition):
    task_id = "rope_threading"
    instruction = 'Thread the rope through all rings in the prescribed order and direction, then keep the whole rope still.'
    terminal_revision = "terminal_v3_default_success"
    physics_model = "fem_ipc"
    defaults = defaults(task_id, geometry={}, stable_duration_s=0.5, rope_finish="hemp",
                        terminal=dict(maximum_speed_m_s=.001, aperture_margin_m=.0001))
    hash_when_changed = ("rope_finish",)

    def declare(self, asset_dir, table_height_m):
        self.table_height_m = float(table_height_m)
        # Keep the whole source assembly clear of the ALOHA mounting feet.
        self.layout = ThreadingLayout(**(PRESETS[self.task_id]["geometry"] | self.config["geometry"]))
        folder = Path(asset_dir)
        preset = record_preset(self, folder)
        report = generate_assets(folder, self.layout)
        volume = write_rope_volume(folder / "rope_volume.npz", self.layout.centerline(), self.layout.rope_radius_m)
        self.centerline_map = load_centerline_map(volume)
        entities = [
            EntitySpec(
                "rope",
                "mesh",
                folder / "rope.obj",
                (0, 0, table_height_m),
                physics_model="fem_elastic",
                volume_path=volume,
                material=rope_fem_parameters(),
                surface=surface(self.config["rope_finish"]),
                morph_options={"convexify": False, "decimate": False},
            )
        ]
        for ring in self.layout.rings():
            for name in (ring["name"], ring["name"] + "_stand", ring["name"] + "_base"):
                color = (ring["rgba"] if name == ring["name"] else
                         ring["stand" if name.endswith("_stand") else "base"]["rgba"])
                entities.append(
                    EntitySpec(
                        name,
                        "mesh",
                        folder / f"{name}.glb",
                        (0, 0, table_height_m),
                        fixed=True,
                        material={"coup_type": "ipc_only"},
                        surface={"color": tuple(color), "metallic": .15, "roughness": .5},
                        morph_options={"convexify": False, "decimate": False,
                                       "file_meshes_are_zup": True},
                    )
                )
        return TaskSpec(
            tuple(entities),
            {"fem": {}, "ipc": rope_ipc_parameters()},
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
        quiet, speed = soft_speed(soft, self.config["terminal"]["maximum_speed_m_s"])
        expected = list(self.layout.required_crossings())
        hits, ambiguous = [], False
        thickness_ok = True
        for ring in self.layout.rings():
            body = state["bodies"][ring["name"]]
            center = body_points(body, [ring["center_m"]])[0]
            q = np.asarray(body["quaternion_wxyz"])
            normal = Rotation.from_quat(q[[1, 2, 3, 0]]).apply(ring["normal"])
            radius = ring["radius_m"]-ring["tube_radius_m"]-self.layout.rope_radius_m-self.config["terminal"]["aperture_margin_m"]
            crossings, uncertain = aperture_crossings(points, center, normal, radius)
            nominal, _ = aperture_crossings(points, center, normal, ring["radius_m"]-ring["tube_radius_m"])
            thickness_ok &= len(nominal) == len(crossings)
            ambiguous |= uncertain
            for offset in (-ring["tube_radius_m"], ring["tube_radius_m"]):
                boundary, unsure = aperture_crossings(points, center+offset*normal, normal, radius)
                ambiguous |= unsure
                thickness_ok &= [h["sign"] for h in boundary] == [h["sign"] for h in crossings]
            hits.extend(dict(hit, ring=ring["name"]) for hit in crossings)
        hits.sort(key=lambda h: h["material_coordinate"])
        sequence = [(h["ring"], h["sign"]) for h in hits]
        intact = ipc_integrity(state, ("rope",))
        return (bool(sequence == expected and thickness_ok and not ambiguous and quiet and intact is True),
                "rope_volume_invalid" if intact is False else None,
                dict(crossing_sequence=sequence, ambiguous=bool(ambiguous), thickness_clear=bool(thickness_ok),
                     quiet=quiet, **speed, evaluation_status="available" if intact is not None else "unavailable",
                     thresholds_calibrated=False, goal_evaluation_complete=bool(self.goal_complete)))
