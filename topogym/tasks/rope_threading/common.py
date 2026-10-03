"""Threading FEM rope and rigid ring declarations; no second simulation backend."""

from pathlib import Path
from dataclasses import replace
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


def usable_rope_aperture_radius(ring, rope_radius_m, terminal, allowance=0., *,
                              axial_offset_m=0., profile="cylindrical"):
    """Conservative centreline aperture with an explicit compression allowance.

    A small allowance accepts rim contact/flattening in the success check; it
    does not enlarge the physical ring or disable native rope/ring collision.
    """
    if (isinstance(allowance, bool) or not isinstance(allowance, (int, float))
            or not np.isfinite(allowance) or not 0 <= allowance <= .5*rope_radius_m):
        raise ValueError("aperture_contact_allowance_m must be between zero and half the rope radius")
    if profile not in {"cylindrical", "round_ring"}:
        raise ValueError("aperture_check_profile must be cylindrical or round_ring")
    if not np.isfinite(axial_offset_m) or abs(axial_offset_m) > ring["tube_radius_m"]:
        raise ValueError("Aperture slice must lie within the ring tube thickness")
    expanded_tube = ring["tube_radius_m"]+rope_radius_m-allowance
    # A torus aperture widens away from its middle plane. The old constant
    # minimum radius rejects bent ropes that clear the actual rounded rim.
    if profile == "round_ring":
        expanded_tube = np.sqrt(expanded_tube**2-axial_offset_m**2)
    return ring["radius_m"]-expanded_tube-terminal["aperture_margin_m"]


class RopeThreadingTask(TaskDefinition):
    task_id = "rope_threading"
    instruction = 'Thread the rope through all rings in the prescribed order and direction, then keep the whole rope still.'
    terminal_revision = "terminal_v3_default_success"
    physics_model = "fem_ipc"
    defaults = defaults(task_id, geometry={}, stable_duration_s=0.5, rope_finish="hemp",
                        rope_mesh={}, rope_material={}, rope_reference_shape="straight", robot_riser_height_m=.0209,
                        rope_robot_contact="full", aperture_contact_allowance_m=0., aperture_check_profile="cylindrical",
                        terminal=dict(maximum_speed_m_s=.001, aperture_margin_m=.0001))
    hash_when_changed = ("rope_finish", "rope_mesh", "rope_material", "rope_reference_shape", "robot_riser_height_m", "rope_robot_contact", "aperture_contact_allowance_m", "aperture_check_profile")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        mesh, material = self.config["rope_mesh"], self.config["rope_material"]
        if not isinstance(mesh, dict) or set(mesh)-{"profile", "spacing", "sides"}:
            raise ValueError("rope_mesh supports profile, spacing and sides")
        if not isinstance(material, dict) or set(material)-{"E", "nu", "rho", "friction_mu"}:
            raise ValueError("rope_material supports E, nu, rho and friction_mu")
        from topogym.assets.materials import MaterialSpec
        MaterialSpec("fem_elastic", rope_fem_parameters() | material)
        if self.config["rope_reference_shape"] not in {"straight", "initial"}:
            raise ValueError("rope_reference_shape must be straight or initial")
        if self.config["rope_robot_contact"] not in {"full", "fingers"}:
            raise ValueError("rope_robot_contact must be full or fingers")
        if self.config["aperture_check_profile"] not in {"cylindrical", "round_ring"}:
            raise ValueError("aperture_check_profile must be cylindrical or round_ring")
        height = self.config["robot_riser_height_m"]
        if isinstance(height, bool) or not np.isfinite(height) or not 0 <= height <= .15:
            raise ValueError("robot_riser_height_m must be in [0, .15]")

    def declare(self, asset_dir, table_height_m):
        self.table_height_m = float(table_height_m)
        # The task-specific ALOHA risers restore the Wang reference clearance.
        self.layout = ThreadingLayout(**(PRESETS[self.task_id]["geometry"] | self.config["geometry"]))
        for ring in self.layout.rings():
            usable_rope_aperture_radius(ring, self.layout.rope_radius_m, self.config["terminal"], self.config["aperture_contact_allowance_m"])
        folder = Path(asset_dir)
        preset = record_preset(self, folder)
        report = generate_assets(folder, self.layout)
        volume = write_rope_volume(folder / "rope_volume.npz", self.layout.centerline(), self.layout.rope_radius_m,
                                   **self.config["rope_mesh"])
        if self.config["rope_reference_shape"] == "initial":
            # Keep immutable straight material coordinates for tracking/grasp
            # identity; only the elastic stress-free reference is curved.
            with np.load(volume, allow_pickle=False) as data:
                arrays = {k: data[k].copy() for k in data.files}
            np.savez_compressed(volume, **arrays, elastic_rest=arrays["spawn"])
        self.centerline_map = load_centerline_map(volume)
        entities = [
            EntitySpec(
                "rope",
                "mesh",
                folder / "rope.obj",
                (0, 0, table_height_m),
                physics_model="fem_elastic",
                volume_path=volume,
                material=rope_fem_parameters() | self.config["rope_material"],
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
                fem_rope_profile=self.config["rope_mesh"].get("profile", "v13_material_mesh"),
                geometry_report=report,
                required_reference_shape=self.config["rope_reference_shape"],
                goal_evaluation_complete=bool(self.goal_complete),
            ),
        )

    def finalize_spec(self, spec, *, asset_dir, scene_config):
        if scene_config.robot_control.robot.name != "aloha":
            return spec
        if self.config["rope_robot_contact"] == "fingers":
            from topogym.robot.description import describe_robot
            links = [name for group in describe_robot(scene_config.robot_control).groups
                     for name in group.grasp.finger_links]
            spec = replace(spec, physics_options={**spec.physics_options,
                "ipc": {**spec.physics_options["ipc"], "robot_collision_links": links}},
                metadata={**spec.metadata, "rope_robot_contact": "fingers",
                          "robot_ipc_collision_links": links,
                          "robot_ipc_filter_scope": "all_ipc_contacts"})
        height = float(scene_config.robot_control.robot.get("base_riser_height_m", 0.))
        if height <= 0:
            return spec
        mount = scene_config.env.robot_mount
        rotation = Rotation.from_euler("xyz", mount.euler, degrees=True)
        quaternion = tuple(rotation.as_quat()[[3, 0, 1, 2]])
        # Narrow supports under the original base axes leave the tabletop rope
        # free below the overhanging flanges. The robot itself is not rescaled.
        risers = tuple(EntitySpec(
            f"{side}_base_riser", "box", None,
            tuple(np.asarray(mount.pos) + rotation.apply((x, -.019, height / 2))),
            quaternion, fixed=True, material={"coup_type": "ipc_only"},
            morph_options={"size": (.07, .07, height)},
            surface={"color": (.24, .26, .28, 1.), "metallic": .5, "roughness": .5},
        ) for side, x in (("left", -.469), ("right", .469)))
        return replace(spec, entities=(*spec.entities, *risers),
                       metadata={**spec.metadata, "aloha_base_riser_height_m": height})

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
            radius = usable_rope_aperture_radius(ring, self.layout.rope_radius_m, self.config["terminal"], self.config["aperture_contact_allowance_m"])
            crossings, uncertain = aperture_crossings(points, center, normal, radius)
            nominal, _ = aperture_crossings(points, center, normal, ring["radius_m"]-ring["tube_radius_m"])
            thickness_ok &= len(nominal) == len(crossings)
            ambiguous |= uncertain
            for offset in (-ring["tube_radius_m"], ring["tube_radius_m"]):
                slice_radius = usable_rope_aperture_radius(ring, self.layout.rope_radius_m,
                    self.config["terminal"], self.config["aperture_contact_allowance_m"],
                    axial_offset_m=offset, profile=self.config["aperture_check_profile"])
                boundary, unsure = aperture_crossings(points, center+offset*normal, normal, slice_radius)
                ambiguous |= unsure
                thickness_ok &= [h["sign"] for h in boundary] == [h["sign"] for h in crossings]
            hits.extend(dict(hit, ring=ring["name"]) for hit in crossings)
        hits.sort(key=lambda h: h["material_coordinate"])
        sequence = [(h["ring"], h["sign"]) for h in hits]
        intact = ipc_integrity(state, ("rope",))
        return (bool(sequence == expected and thickness_ok and not ambiguous and quiet and intact is True),
                "rope_volume_invalid" if intact is False else None,
                dict(crossing_sequence=sequence, ambiguous=bool(ambiguous), thickness_clear=bool(thickness_ok),
                     aperture_contact_allowance_m=self.config["aperture_contact_allowance_m"],
                     aperture_check_profile=self.config["aperture_check_profile"],
                     quiet=quiet, **speed, evaluation_status="available" if intact is not None else "unavailable",
                     thresholds_calibrated=False, goal_evaluation_complete=bool(self.goal_complete)))
