"""slotted_post_ring hard with the cord as a rigid capsule chain (the FEM settings are unchanged).

The fixture, ring, beads, chain and discs are one MJCF entity (topogym.assets.geometry.slotted_chain) for Genesis'
rigid solver. The geometry is slotted_post_ring_hard's with three changes for the chain:
- the slot is 34 mm (SLOT_WIDTH_M; hard's is 28 mm): the cord beside the ring's tube in the slot has 14 mm, not 8 mm;
  beads (39 mm) still stop at it, the discs and the ring pass it only edge-on;
- the cord is 0.66 m longer, the extra laid on the table front left (slotted_chain.ChainLayout);
- the puzzle stands at CENTER_XY_M, 9 cm nearer the robot's centre line, where the left arm reaches the post's front
  and back as the right arm does (the goal region's x follows the table, not the puzzle).

The goal is the FEM settings' goal: every ring point inside the goal region, every other part (chain, discs, beads,
base, post) on the system side of the separator, the ring quiet. The goal region is chosen from the reset geometry.
"""
from pathlib import Path

import numpy as np

from topogym.assets.geometry.slotted_chain import EYE_LOCAL_M, LINKS, ChainLayout, fixture_boxes, part_vertices, scene_xml
from topogym.evaluation.task_metrics import body_points, body_points_batch, quiet_body
from topogym.utils.geometry.regions import placement_measurements
from ..base import EntitySpec, TaskSpec, merge_parameters
from ..scene_presets import record_preset
from .slotted_post_ring_hard import SlottedPostRingHardTask

ENTITY = "slotted_chain"
REMAINDER = ("base", "post", "cord", "bead_left", "bead_right", "disc_left", "disc_right")
CENTER_XY_M = (-.11, .04)
SLOT_WIDTH_M = .034
GRASP_TCP_DISTANCE_M = .09   # the ring's grasp region is centred on its centre, 61 mm from a pinch on its tube


class SlottedPostRingHardChainTask(SlottedPostRingHardTask):
    variation_id = "slotted_post_ring_hard_chain"
    family_id = "rigid_chain"
    model_revision = "chain88_v6"
    difficulty = None
    physics_model = "rigid_articulated"
    # The rigid families' CPU float64 solve with one substep instead of the FEM settings' IPC (rcb_topogym
    # simulator_config); the task's 800-tick reset settle and the default rigid options stay.
    simulator_settings = dict(compute_backend="cpu", precision="64", solver_substeps=1)
    defaults = merge_parameters(SlottedPostRingHardTask.defaults, {"center_xy_m": list(CENTER_XY_M),
                                                                    "geometry": {"slot_width_m": SLOT_WIDTH_M}})

    def make_layout(self):
        """The setting's geometry with the chain's longer cord (slotted_chain.ChainLayout)."""
        return ChainLayout(**self.config["geometry"])

    def grasp_assist(self):
        """contact_weld_v1 on the ring only, its region round its whole body. Not the beads: a hand slides a bead along
        the cord, and a welded bead drags the cord off the weld's pose. Not the discs: welded in A's rim grip, disc1
        pushed into the slot stops B's take behind the post. Not the chain's links: a pinch holds them by friction,
        and 88 more targets cost about 18% per control step."""
        from topogym.utils.grasp import GraspAssistConfig, rigid_grasp_region
        ring = rigid_grasp_region(ENTITY, "ring", part_vertices(self.make_layout())["ring"])
        return GraspAssistConfig("contact_weld_v1", (ring,), max_tcp_distance_m=GRASP_TCP_DISTANCE_M)

    def declare(self, asset_dir, table_height_m):
        import genesis as gs
        self.table_height_m = float(table_height_m)
        preset = record_preset(self, asset_dir)
        self.origin = np.r_[np.asarray(self.config["center_xy_m"], float), table_height_m]
        self.layout = self.make_layout().validate()
        xml, points = scene_xml(self.layout, LINKS)
        path = Path(asset_dir)/f"{ENTITY}.xml"
        path.write_text(xml)
        self.chord_m = float(np.linalg.norm(points[1]-points[0]))
        self.part_points = part_vertices(self.layout)
        corners = np.array([[x, y, z] for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)], float)
        boxes = {name: np.asarray(c)+corners*h for name, c, h in fixture_boxes(self.layout)}
        self.fixture_points = dict(base=boxes.pop("base")+self.origin, post=np.vstack(list(boxes.values()))+self.origin)
        self.placement_targets, self.placement_remainder = ("target_ring",), REMAINDER
        return TaskSpec((EntitySpec(ENTITY, "mjcf", path, tuple(self.origin)),),
                        {"rigid": dict(enable_self_collision=True, constraint_solver=gs.constraint_solver.CG)},
                        dict(**preset, assembly_origin_m=list(self.origin), task_id=self.task_id, chain_links=LINKS,
                             goal_evaluation_complete=bool(self.goal_complete)))

    def placement_clouds(self, spec):
        """The reset geometry's parts (the goal region does not depend on the start state)."""
        from scipy.spatial.transform import Rotation as R
        _, points = scene_xml(self.layout, LINKS)
        controls = self.layout.cord_controls()
        poses = dict(ring=(np.r_[0., 0., self.layout.ring_z], R.identity()))
        for side, k in zip(("left", "right"), self.layout.bead_controls()):
            poses[f"bead_{side}"] = (controls[k], R.identity())
        eye = np.asarray(EYE_LOCAL_M)
        poses["disc_left"], poses["disc_right"] = (points[0]-eye, R.identity()), (points[-1]-eye, R.identity())
        return self._clouds({name: dict(position_m=p+self.origin, quaternion_wxyz=r.as_quat()[[3, 0, 1, 2]])
                             for name, (p, r) in poses.items()}, points+self.origin)

    def _clouds(self, parts, cord):
        """{placement name: world points}; parts: {ring, beads, discs: world pose}, cord: the chain's joint points."""
        r = self.layout.rope_radius_m
        out = dict(target_ring=body_points(parts["ring"], self.part_points["ring"]), **self.fixture_points)
        for name in ("bead_left", "bead_right", "disc_left", "disc_right"):
            out[name] = body_points(parts[name], self.part_points[name])
        out["cord"] = (np.asarray(cord)[:, None, :]+r*np.vstack([np.eye(3), -np.eye(3)])[None]).reshape(-1, 3)
        return out

    def chain_points(self, state):
        """World points of the chain's joints (LINKS+1, left eye first) in a World state."""
        links = state["articulations"][ENTITY]["links"]
        ends = body_points_batch([links[f"link_{i:03d}"] for i in range(LINKS)], [[0., 0., 0.], [self.chord_m, 0., 0.]])
        # The chain grows outwards from the middle link: left of it a link's frame sits at its right end, pointing left.
        k = LINKS//2
        return np.vstack([ends[:k, 1], ends[k:, 0], ends[-1:, 1]])

    def evaluate_goal_region(self, state, region):
        links = state["articulations"][ENTITY]["links"]
        clouds = self._clouds({name: links[name if name != "target_ring" else "ring"]
                               for name in ("ring", "bead_left", "bead_right", "disc_left", "disc_right")},
                              self.chain_points(state))
        metrics = placement_measurements(region, {"target_ring": clouds.pop("target_ring")}, clouds)
        quiet = quiet_body(links["ring"], .001, .02)
        metrics.update(quiet=quiet, connections_intact=True, evaluation_status="available", holding_allowed=True)
        reached = metrics["all_target_inside"] and metrics["remainder_on_system_side"] and quiet
        return bool(reached), None, metrics
