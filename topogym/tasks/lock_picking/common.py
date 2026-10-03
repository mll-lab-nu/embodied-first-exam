"""Passive-disc lock in the common World; full overload/clearance audit remains explicit."""

from pathlib import Path
import json
import numpy as np
from scipy.spatial.transform import Rotation
from omegaconf import OmegaConf
from topogym.assets.geometry.lock_picking import (
    LockGeometry,
    write_disc,
    write_key,
    write_endpoint,
    DISC_COLORS,
    ENDPOINT_COLOR,
    paint_aperture_outline,
    key_rest_layout, write_key_cradle,
)
from ..base import TaskDefinition, EntitySpec, TaskSpec
from ..scene_presets import defaults, record_preset, PRESETS
from topogym.assets.scene_visuals import surface, finish_generated_urdf, localize_generated_urdfs


def recommended_grasp_assist(variation_id, seed=0, *, task_parameters=None):
    """Place the existing contact-gated grasp region on this key's handle."""
    from topogym.config.registry import task_definition
    from topogym.utils.grasp import GraspAssistConfig, GraspTarget
    task = task_definition("lock_picking", variation_id, seed)(task_parameters, seed=seed)
    geometry = task.geometry_type(**task.config["geometry"])
    geometry.validate()
    return GraspAssistConfig(
        model="contact_weld_v1", stable_time_s=.05,
        targets=(GraspTarget("lock_key", "key", (-geometry.grip_offset, 0., 0.), .032),),
    )


class LockPickingTask(TaskDefinition):
    task_id = "lock_picking"
    geometry_type = LockGeometry
    instruction = 'Insert the key through the lock until its leading tab clears the final plate. The rotor pins must remain constrained by their physical slots.'
    terminal_revision = "terminal_v4_bore_contact_default_success"
    physics_model = "rigid_articulated"
    defaults = defaults(task_id, geometry={}, stable_duration_s=0.5,
        physics=dict(disc_mass=.12, key_mass=.12, disc_damping=.03,
                     friction=.01, passive_armature=0., contact_timeconst=.0025),
        terminal=dict(rotor_tolerance_deg=.5, insertion_margin_m=.001,
                      shaft_contact_tolerance_m=.00001),
        disc_colors=[list(color) for color in DISC_COLORS], base_finish="coated_metal")
    hash_when_changed = ("disc_colors", "base_finish")

    def __init__(self, config=None, seed=0):
        super().__init__(config, seed)
        physics = self.config["physics"]
        if not isinstance(physics, dict) or set(physics) != set(self.defaults["physics"]):
            raise ValueError("Unknown or missing lock physics parameter")
        for name, value in physics.items():
            if (isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float))
                    or not np.isfinite(value) or value < 0
                    or (name in {"disc_mass", "key_mass", "contact_timeconst"} and value == 0)):
                raise ValueError(f"Invalid lock physics.{name}")

    def declare(self, asset_dir, table_height_m):
        self.table_height_m = float(table_height_m)
        physics = self.config["physics"]
        # Historical passive mechanism: no motor rotor inertia on disc hinges.
        passive_urdf = {"merge_fixed_links": False, "default_armature": physics["passive_armature"]}
        mechanism_material = {"friction": physics["friction"]}
        preset = record_preset(self, asset_dir)
        self.layout = g = self.geometry_type(
            **{"axis_z": table_height_m + 0.185,
               **PRESETS[self.task_id]["geometry"], **self.config["geometry"]}
        )
        g.validate()
        folder = Path(asset_dir)
        folder.mkdir(parents=True, exist_ok=True)
        base_height = .028
        rest = key_rest_layout(g)
        x_min = rest["tray_start"]-.065
        x_max = g.disc_x(g.disc_count)+.07
        entities = [EntitySpec("lock_base", "box", None,
            ((x_min+x_max)/2, g.center_y, table_height_m+base_height/2), fixed=True,
            morph_options={"size": (x_max-x_min, .21, base_height)},
            surface=surface(self.config["base_finish"]))]
        stops = self.config["rotor_stops"]
        outlines = {}
        if len(stops) != g.disc_count:
            raise ValueError(f"{g.disc_count} rotor-stop definitions are required")
        for i, slots in enumerate(g.slots):
            stop = OmegaConf.create(stops[i])
            if not stop.bounds_deg[0] <= g.initial_disc_deg[i] <= stop.bounds_deg[1]:
                raise ValueError("Initial rotor angle outside its physical stop range")
            path = write_disc(
                g, slots, folder / f"disc_{i}", physics["disc_mass"], physics["disc_damping"], self.config["disc_colors"][i],
                stop=stop, mount_z=table_height_m+base_height-g.axis_z,
            )
            outlines[f"lock_disc_{i}"] = self._paint_aperture(path, slots, self.config["disc_colors"][i])
            entities.append(
                EntitySpec(
                    f"lock_disc_{i}",
                    "urdf",
                    path,
                    (g.disc_x(i), g.center_y, g.axis_z),
                    fixed=True,
                    morph_options=passive_urdf,
                    material=mechanism_material,
                    initial_joint_positions={
                        "disc_hinge": float(np.radians(g.initial_disc_deg[i]))
                    },
                )
            )
            frame = folder/f"disc_{i}"/"limits"/"stop_frame.urdf"
            finish_generated_urdf(frame, "engineering_plastic")
            entities.append(EntitySpec(f"lock_frame_{i}", "urdf", frame,
                (g.disc_x(i), g.center_y, g.axis_z), fixed=True,
                material={"friction": .3},
                morph_options={"merge_fixed_links": False}))
        goal = write_endpoint(g, folder / "goal")
        outlines["lock_goal"] = self._paint_aperture(
            goal, (g.endpoint_deg,), ENDPOINT_COLOR, goal_plate=True
        )
        silver = surface("silver")
        silver["color"] = silver["color"][:3]
        key = write_key(g, folder / "key", physics["key_mass"], visual_finish=silver)
        tray_length = rest["tray_end"]-rest["tray_start"]
        tray_x = (rest["tray_end"]+rest["tray_start"])/2
        entities.append(EntitySpec("key_tray", "box", None,
            (tray_x, g.center_y, rest["tray_top"]-rest["tray_thickness"]/2),
            fixed=True, morph_options={"size": (tray_length, rest["tray_width"], rest["tray_thickness"])},
            surface=surface("engineering_plastic")))
        for i, x in enumerate(rest["cradle_x"]):
            bottom = table_height_m+base_height
            top = rest["tray_top"]-rest["tray_thickness"]
            if top <= bottom:
                raise ValueError("Key tray must leave room for its support posts")
            entities.append(EntitySpec(f"key_tray_post_{i}", "box", None,
                (x, g.center_y, (top+bottom)/2), fixed=True,
                morph_options={"size": (.022, .05, top-bottom)},
                surface=surface("engineering_plastic")))
            for j, mesh in enumerate(write_key_cradle(rest, folder/f"cradle_{i}")):
                entities.append(EntitySpec(f"key_cradle_{i}_{j}", "mesh", mesh,
                    (x, g.center_y, rest["tray_top"]), fixed=True,
                    material={"friction": .6},
                    morph_options={"convexify": True, "decimate": False},
                    surface=surface("engineering_plastic")))
        # The endpoint is also supported by a real post, not floating in space.
        lower = table_height_m+base_height
        upper = g.axis_z-g.disc_radius
        entities.append(EntitySpec("lock_goal_post", "box", None,
            (g.disc_x(g.disc_count), g.center_y, (lower+upper)/2), fixed=True,
            morph_options={"size": (.035, .08, upper-lower)},
            surface=surface("engineering_plastic")))
        entities.extend(
            (
                EntitySpec(
                    "lock_goal",
                    "urdf",
                    goal,
                    (g.disc_x(g.disc_count), g.center_y, g.axis_z),
                    fixed=True,
                    material=mechanism_material,
                ),
                EntitySpec(
                    "lock_key",
                    "urdf",
                    key,
                    (
                        g.tip_x(0), g.center_y,
                        rest["resting_axis_z"]+0.0001,
                    ),
                    material=mechanism_material,
                    morph_options=passive_urdf,
                ),
            )
        )
        localize_generated_urdfs(folder)
        return TaskSpec(
            tuple(entities),
            {"rigid": {"enable_self_collision": True,
                       "enable_joint_limit": True, "iterations": 100,
                       "constraint_timeconst": physics["contact_timeconst"]}},
            dict(
                **preset, key_rest=rest, physical_rotor_frames=True,
                aperture_outlines=outlines,
                task_id=self.task_id,
                goal_evaluation_complete=bool(self.goal_complete),
                rotor_stops_complete=False,  # Full overload/withdrawal audit still missing.
            ),
        )

    def _paint_aperture(self, path, slots, color, *, goal_plate=False):
        """Reuse the visual-only painter and keep its report episode-independent."""
        paint_aperture_outline(
            path, self.layout, slots, color, self.config["aperture_outline"],
            goal_plate=goal_plate,
        )
        report_path = path.parent / "aperture_outline.json"
        if not report_path.is_file():
            return {"enabled": False}
        report = json.loads(report_path.read_text())
        for key in ("source_visual", "outlined_visual"):
            source = Path(report[key])
            if not source.is_absolute():
                source = path.parent / source
            report[key] = source.resolve().relative_to(path.parent.resolve()).as_posix()
        report_path.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
        return report

    def evaluate_state(self, state):
        p = np.asarray(state["bodies"]["lock_key"]["position_m"])
        if not np.isfinite(p).all():
            return False, "Non-finite key state", {}
        if p[2] < self.table_height_m - 0.1:
            return False, "Key fell below table", {}
        cfg, g = self.config["terminal"], self.layout
        angles = []
        for i, stop in enumerate(self.config["rotor_stops"]):
            value = np.asarray(state["articulations"][f"lock_disc_{i}"]["joints"]["disc_hinge"]["position"], float)
            if value.size != 1 or not np.isfinite(value).all():
                raise ValueError("Expected one finite rotor angle")
            angle = float(np.degrees(value.item()))
            angles.append(angle)
            lo, hi = stop["bounds_deg"]
            if hi-lo < 360-1e-8 and not lo-cfg["rotor_tolerance_deg"] <= angle <= hi+cfg["rotor_tolerance_deg"]:
                return False, "rotor_limit_exceeded", dict(rotor=i, angle_deg=angle)
        q = np.asarray(state["bodies"]["lock_key"]["quaternion_wxyz"], float)
        if q.shape != (4,) or not np.isfinite(q).all() or np.linalg.norm(q) < 1e-12:
            raise ValueError("Invalid key orientation")
        rotation = Rotation.from_quat(q[[1, 2, 3, 0]])
        axis = rotation.apply([1., 0, 0])
        tilt = float(np.degrees(np.arccos(np.clip(axis[0], -1, 1))))
        radial = rotation.apply([0., 0, 1.])
        angle = float(np.degrees(np.arctan2(radial[1], radial[2])))
        depth = (p[0]-g.first_x)/g.pitch+1
        # Tilt is constrained by passage through every finite bore, not by
        # an independent coaxiality angle. Backwards/transverse keys cannot pass.
        aligned = axis[0] > 1e-8
        offsets = []
        shaft_coordinates = []
        shaft_in_goal = False
        shaft_through_all = False
        bore_excess = None
        if aligned:
            for i in range(g.disc_count+1):
                x = g.disc_x(i)
                for face in (x-g.disc_thickness/2, x+g.disc_thickness/2):
                    coordinate = (face-p[0])/axis[0]
                    shaft_coordinates.append(float(coordinate))
                    at = p+axis*coordinate
                    offsets.append(float(np.linalg.norm(at[1:]-[g.center_y, g.axis_z])))
            # A normal resting contact need not leave a positive air gap. The
            # 10 um budget covers the 3--6 um residual in the three recorded
            # released poses; it is not a general solver penetration allowance.
            bore_excess = max(offsets) + g.shaft_radius/axis[0] - g.bore_radius
            aligned &= bore_excess <= cfg["shaft_contact_tolerance_m"]
            # write_key() authors the shaft over [-grip_offset-.02, .015].
            # Account for the oblique section's axial extent at both end caps.
            end_padding = g.shaft_radius*np.linalg.norm(axis[1:])/axis[0]
            def spans(coordinates):
                return (min(coordinates)-end_padding >= -g.grip_offset-.02
                        and max(coordinates)+end_padding <= .015)
            shaft_in_goal = spans(shaft_coordinates[-2:])
            shaft_through_all = spans(shaft_coordinates)
        # Conservative x extent of the leading tab under small residual tilt.
        tab_back = p[0]-g.tab_thickness/2*abs(axis[0])-g.tab_radius*np.linalg.norm(rotation.as_matrix()[0, 1:])
        inserted = tab_back >= g.disc_x(g.disc_count)+g.disc_thickness/2+cfg["insertion_margin_m"]
        issues = g.clearance(depth, angle, angles)
        # Expand slab tests for tilt and angular tests for the allowed offset.
        radial_error = max(offsets, default=g.bore_radius)
        angular_allowance = np.degrees(np.arcsin(min(1., radial_error/g.tab_radius)))+tilt
        for tab in range(g.tab_count):
            tab_center = p+rotation.apply([-tab*g.pitch, 0, 0])
            extent = g.tab_thickness/2*abs(axis[0])+g.tab_radius*np.linalg.norm(rotation.as_matrix()[0, 1:])
            for i in range(g.disc_count+1):
                if abs(tab_center[0]-g.disc_x(i)) <= extent+g.disc_thickness/2:
                    margin = (g.slot_margin(angle, angles[i], i) if i < g.disc_count else
                              g.slot_half_deg-g.tab_half_deg-abs((angle-g.endpoint_deg+180)%360-180))
                    if margin < angular_allowance:
                        issues.append(f"tab{tab}/plate{i}/pose_clearance")
        return bool(inserted and shaft_through_all and aligned and not issues), None, dict(
            disc_angles_deg=angles, key_depth=depth, key_tilt_deg=tilt,
            coaxial=bool(aligned), shaft_bore_clear=bool(aligned),
            shaft_bore_excess_m=bore_excess,
            shaft_contact_tolerance_m=cfg["shaft_contact_tolerance_m"],
            shaft_in_goal=bool(shaft_in_goal), shaft_through_all_plates=bool(shaft_through_all),
            leading_tab_inserted=bool(inserted), clearance_issues=issues,
            physical_rotor_frames=True, rotor_mechanism_runtime_verified=False,
            evaluation_status="available", thresholds_calibrated=False,
            goal_evaluation_complete=bool(self.goal_complete))
