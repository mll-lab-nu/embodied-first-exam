"""Negative controls for publishing a complete physical blanket demo."""
from copy import deepcopy
import unittest

from topogym.tasks.blanket_flatten.archive import qualify, qualify_mesh_review


class BlanketArchiveChecks(unittest.TestCase):
    def records(self):
        physical = dict(full_robot_task_verified=True, success=True, initialization_accepted=True,
            active_grasp_particles=[], releases=4, physics_steps=20000, frame_count=2001,
            live_particle_position_writes=False, live_robot_position_writes_after_home=False,
            initial_robot_clearance_checks=50, minimum_initial_robot_clearance_m=.04,
            final_evidence=dict(window_seconds=.5, gates=dict(released=True, flat=True, settled=True)))
        render = dict(source_success=True, preview_only=False, frames=2001, source_frames=2001,
            arm_clearance_review_passed=True,
            cameras=['agentview','front_oblique','wrist'], maximum_particle_reconstruction_error_m=0.,
            maximum_joint_reconstruction_error=0.)
        stability = dict(success=True, mode='stability', worst=dict(nonfinite_steps=0),
            initial_robot_clearance_checks=250, minimum_initial_robot_clearance_m=.04,
            final_evidence=dict(passive_seconds=10., window_seconds=.4, gates=dict(settled=True)))
        return physical, render, stability

    def test_rejects_incomplete_held_or_teleported_attempt(self):
        records = self.records()
        qualify(*records)
        for changes in (dict(success=False), dict(full_robot_task_verified=False),
                        dict(active_grasp_particles=[1]), dict(releases=0),
                        dict(live_particle_position_writes=True),
                        dict(live_robot_position_writes_after_home=True),
                        dict(minimum_initial_robot_clearance_m=0), dict(initial_robot_clearance_checks=0),
                        dict(motion_robot_clearance_checks=1, minimum_motion_robot_clearance_m=.007),
                        dict(final_evidence=dict(window_seconds=.4, gates=dict(flat=True))),
                        dict(final_evidence=dict(window_seconds=.5, gates=dict(flat=False)))):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                qualify({**records[0], **changes}, *records[1:])

    def test_rejects_partial_or_reconstructed_motion_and_short_stability(self):
        for changes in (dict(preview_only=True), dict(frames=1900), dict(source_success=False),
                        dict(arm_clearance_review_passed=False), dict(arm_clearance_review_passed=None),
                        dict(cameras=['agentview','wrist']),
                        dict(maximum_joint_reconstruction_error=.01),
                        dict(maximum_particle_reconstruction_error_m=.002)):
            records = self.records()
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                qualify(records[0], {**records[1], **changes}, records[2])
        for changes in (dict(passive_seconds=2.4), dict(window_seconds=.05), dict(gates=dict(settled=False))):
            records = deepcopy(self.records())
            records[2]['final_evidence'].update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                qualify(*records)

    def test_mesh_review_must_cover_every_frame_without_intersection(self):
        good=dict(frames=3, counts=[0, 0, 0], maximum_intersecting_faces=0, intersecting_frames=[])
        qualify_mesh_review(good, 3)
        for change in (dict(frames=2), dict(counts=[0, 0]), dict(counts=[0, 1, 0]),
                       dict(maximum_intersecting_faces=1), dict(intersecting_frames=[1])):
            with self.subTest(change=change), self.assertRaises(ValueError):
                qualify_mesh_review({**good, **change}, 3)
        physical, render, stability = self.records()
        del render['arm_clearance_review_passed']
        with self.assertRaises(ValueError):
            qualify(physical, render, stability)

    def test_birth_robot_clearance_detects_crossing_surfaces(self):
        import numpy as np
        import trimesh
        from topogym.tasks.blanket_flatten.robot_clearance import surface_clearance
        cube = trimesh.creation.box(extents=[.1, .1, .1])
        cloth = np.array([[-.2,-.2,0],[.2,-.2,0],[.2,.2,0],[-.2,.2,0]])
        faces = np.array([[0,1,2],[0,2,3]])
        robot = [('body', cube.vertices, cube.faces)]
        # All cloth vertices are outside the cube; triangle interiors cross it.
        self.assertLessEqual(surface_clearance(cloth, faces, robot), 0.)
        self.assertAlmostEqual(surface_clearance(cloth+[0,0,.15], faces, robot), .1)

    def test_robot_video_can_omit_preparation_but_cannot_omit_actions_or_end(self):
        physical, render, stability = self.records()
        physical.update(simulated_seconds=100., events=[dict(phase='pull_1_approach', seconds=25.)])
        render.update(source_start_frame=480, frames=1521, recording_start_s=24., recording_end_s=100.)
        qualify(physical, render, stability)
        for change in [dict(recording_start_s=26.), dict(recording_end_s=99.),
                       dict(frames=1500), dict(source_start_frame=-1)]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                qualify(physical, {**render, **change}, stability)

    def test_regular_lower_fps_sampling_keeps_the_complete_action_range(self):
        physical, render, stability = self.records()
        physical.update(fps=20, simulated_seconds=100., events=[dict(phase='pull_1_approach', seconds=25.)])
        indices=list(range(480, 2001, 2))
        render.update(source_start_frame=480, frames=len(indices), recording_start_s=24., recording_end_s=100.,
                      source_fps=20, fps=10, source_frame_indices=indices)
        qualify(physical, render, stability)
        for change in [dict(source_frame_indices=indices[:20]+indices[21:]),
                       dict(source_fps=40), dict(fps=12)]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                qualify(physical, {**render, **change}, stability)

    def test_selected_shape_stability_must_match_source_content_frame_and_velocity(self):
        physical, render, stability = self.records()
        source=dict(source_sha256='a'*64,source_frame=234,initial_velocity='zero')
        physical['initial_state_restoration']=source.copy()
        stability['initial_state_restoration']=source.copy()
        qualify(physical,render,stability)
        for change in [dict(source_sha256='b'*64),dict(source_frame=233),dict(initial_velocity='recorded')]:
            altered=deepcopy(stability)
            altered['initial_state_restoration'].update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):
                qualify(physical,render,altered)


if __name__ == '__main__':
    unittest.main()
