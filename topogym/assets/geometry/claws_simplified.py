"""Dimensioned low-tier claw candidates, using the existing compound-box assets.

These are independent rigid solids. Initial clearance and a blocked axial pull
are checked here; neither a separation path nor difficulty is qualified.
"""
from pathlib import Path
from types import SimpleNamespace
import json

import numpy as np
import trimesh

from .interlocked_claws import (
    COLORS, DENSITY, FamilyModel, Part, box, box_mesh, load_reference,
    pose, retarget_qpos, tcp_frames,
)


class SimplifiedClawModel(FamilyModel):
    """Reuse the established solid-union inertia and native-box URDF writer."""

    def __init__(self, family, reference_q):
        self.family = family
        reference = load_reference()
        frames = tcp_frames(reference, reference_q)
        center = np.mean([f[:3, 3] for f in frames], axis=0)
        # Match easy's 260 mm grasp spacing and medium/hard's flat grasp pads.
        grasps = [np.array([-.13, 0., 0.]), np.array([.13, 0., 0.])]
        if family == "shallow_l_hooks":
            grasps[0][2], grasps[1][1] = -.022, .022
            # Brown lies in xz, blue in xy: their short legs cross at 90 deg
            # in the yz projection, with a 4 mm axial surface gap. Brown's
            # short leg is to the RIGHT of blue's, blocking an outward pull.
            # Both tips extend 6 mm beyond the other leg's projected edge.
            items = [
                [box([-.0705, 0., -.022], [.169, .012, .012]),
                 box([.008, 0., -.008], [.012, .012, .040])],
                [box([.0705, .022, 0.], [.169, .012, .012]),
                 box([-.008, .008, 0.], [.012, .040, .012])],
            ]
            dimensions = dict(shaft_section_m=.012, short_leg_length_m=.040,
                              short_leg_axes=[[0, 0, 1], [0, -1, 0]],
                              short_leg_angle_deg=90., short_leg_gap_m=.004,
                              crossing_tip_margin_m=.006,
                              handle_height_difference_m=.022,
                              handle_lateral_difference_m=.022)
        elif family == "cross_square_offset":
            # Cross axes are y and z; its grasp shaft is x (all perpendicular).
            # Square lies in yz at x=0; cross head starts beyond it at x=22 mm.
            a, outer, opening, thickness = .120, .132, .088, .012
            rail = (outer-opening)/2
            side = (outer+opening)/4
            grasps[1][1] = .094
            items = [
                [box([-.0665, 0., 0.], [.177, .014, .014]),
                 box([.022, 0., 0.], [.014, a, .014]),
                 box([.022, 0., 0.], [.014, .014, a])],
                [box([0., -side, 0.], [thickness, rail, outer]),
                 box([0., side, 0.], [thickness, rail, outer]),
                 box([0., 0., -side], [thickness, opening+.002, rail]),
                 box([0., 0., side], [thickness, opening+.002, rail]),
                 # 28 mm of visible lateral extension beyond the frame rim,
                 # then a perpendicular turn into the x-directed grasp shaft.
                 box([0., .078, 0.], [.014, .046, .014]),
                 box([.074, .094, 0.], [.162, .014, .014])],
            ]
            dimensions = dict(cross_span_m=a, cross_bar_section_m=.014,
                              frame_outer_side_m=outer, frame_clear_side_m=opening,
                              frame_depth_m=thickness, frame_rail_width_m=rail,
                              lateral_extension_beyond_frame_m=.028,
                              shaft_lateral_offset_m=.094, head_frame_gap_m=.009,
                              shaft_axis=[1, 0, 0], cross_axes=[[0, 1, 0], [0, 0, 1]])
        else:
            raise ValueError(f"Unknown simplified claw family: {family}")

        self.parts, targets = [], []
        for i, (boxes, grasp, frame) in enumerate(zip(items, grasps, frames)):
            boxes.append(box(grasp, [.030, .028, .024]))
            mesh = trimesh.boolean.union([box_mesh(b) for b in boxes], engine="manifold")
            mesh.density = DENSITY
            if (not mesh.is_watertight or not mesh.is_winding_consistent
                    or len(mesh.split()) != 1 or mesh.volume <= 0
                    or np.linalg.eigvalsh(mesh.moment_inertia).min() <= 0):
                raise ValueError(f"{family} piece {i} must be one valid solid")
            local_grasp = frame.copy()
            local_grasp[:3, 3] = grasp
            self.parts.append(Part(f"piece_{i}", boxes, mesh, local_grasp,
                                   ("left", "right")[i], .0222))
            target = frame.copy()
            target[:3, 3] = center+grasp
            targets.append(target)
        self.initial_q = retarget_qpos(reference, reference_q, targets)
        self.initial = [pose(center), pose(center)]
        self.segments = []
        self.duration = 0.

        collision = trimesh.collision.CollisionManager()
        collision.add_object("other", self.parts[1].mesh)
        target_mesh = self.parts[0].mesh
        gap = float(collision.min_distance_single(target_mesh))
        if collision.in_collision_single(target_mesh) or gap <= 0:
            raise ValueError(f"{family}: initial pieces intersect")
        # Finite negative-control witness, not a full manipulation certificate.
        witness = next((float(d) for d in np.linspace(.001, .035, 35)
                        if collision.in_collision_single(target_mesh,
                                                         transform=pose([-d, 0., 0.]))), None)
        if witness is None:
            raise ValueError(f"{family}: expected short-leg/head axial obstruction is absent")
        actual = tcp_frames(reference, self.initial_q)
        self.audit = dict(
            dimensions=dimensions, grip_block_m=[.030, .028, .024],
            initial_surface_collision=False, initial_surface_gap_m=gap,
            axial_pull_collision_witness_m=witness,
            initial_robot_qpos=self.initial_q.tolist(),
            tcp_position_error_m=max(float(np.linalg.norm(a[:3, 3]-b[:3, 3]))
                                     for a, b in zip(actual, targets)),
            robot_geometry_modified=False, initialization="opposed_original_aloha_pregrasp",
            geometry_status="candidate", full_path_verified=False,
            physics_verified=False, difficulty_qualified=False,
        )


def build_simplified_claws(folder, family, reference_q):
    folder = Path(folder)
    model = SimplifiedClawModel(family, reference_q)
    root = folder / "family"
    report = model.save(root)
    report.update(model.audit)
    bodies = [SimpleNamespace(name=p.name, mesh=p.mesh, pose=t, color=c,
                              asset_path=root/f"{p.name}.urdf")
              for p, t, c in zip(model.parts, model.initial, COLORS)]
    (folder / "geometry_report.json").write_text(json.dumps(report, indent=2)+"\n")
    scene = trimesh.Scene()
    for body in bodies:
        scene.add_geometry(body.mesh, node_name=body.name, transform=body.pose)
    scene.export(folder / "assembly.glb")
    return SimpleNamespace(bodies=bodies, reference={"density_kg_m3": DENSITY}), report, model.initial_q
