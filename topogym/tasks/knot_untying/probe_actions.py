"""Explicit soft-grasp fixtures for local FEM loading/unloading experiments."""
import numpy as np


def smoothstep(t):
    t = np.clip(t, 0., 1.)
    return t*t*(3-2*t)


class ProbeActions:
    def __init__(self, mode):
        self.mode = mode
        self.grasps = []
        self.origins = None
        self.events = []
        self.samples = []
        self.targets = None

    def specification(self):
        if self.mode == 'lift_release':
            motion = [dict(start_s=3., end_s=5., lift_m=.03),
                      dict(start_s=5., end_s=7., translate_y_m=.03),
                      dict(start_s=7., end_s=9., lower_m=.03)]
            release = 9.
        else:
            motion = [dict(start_s=3., end_s=15., feed_vector_m=[-.012, .016, 0.],
                           cycle_s=4., cycles=3)]
            release = 15.
        return dict(kind='explicit_soft_target_fixture', motion=motion, release_s=release,
                    post_release_s=5., strength=100., band_radius_m=.008,
                    tail_grasp_arc_distance_m=.015, maximum_band_follow_error_m=.002)

    def declare(self, base, rope, centerline, backend):
        from topogym.primitives.fem_attachment import FEMRopeAttachment
        # Grasp the free tail, 15 mm back from each tip, far from crossings.
        lengths = np.r_[0., np.cumsum(np.linalg.norm(np.diff(centerline, axis=0), axis=1))]
        for distance in (.015, lengths[-1]-.015):
            point = centerline[np.argmin(abs(lengths-distance))]
            self.grasps.append(FEMRopeAttachment(rope, point, radius=.008, strength=100.))

    def update(self, t):
        if t < 3.:
            return
        if self.origins is None:
            self.origins = [grasp.attach().copy() for grasp in self.grasps]
            self.targets = [point.copy() for point in self.origins]
            if self.mode == 'lift_release':
                self.grasps[1].release()
            self.events.append(dict(time_s=t, event='engage_fixture'))
        if self.mode == 'lift_release':
            if t < 5.:
                offset = [0., 0., .03*smoothstep((t-3.)/2)]
            elif t < 7.:
                offset = [0., .03*smoothstep((t-5.)/2), .03]
            elif t < 9.:
                offset = [0., .03, .03*(1-smoothstep((t-7.)/2))]
            else:
                self.release(t)
                return
            self.targets[0] = self.origins[0]+offset
            self.grasps[0].drive_to(self.targets[0])
        elif self.mode == 'feed_release':
            if t >= 15.:
                self.release(t)
                return
            # Three four-second cycles of 20 mm inward feeding and retreat.
            phase = (t-3.) % 4.
            amplitude = smoothstep(phase/2) if phase < 2 else 1-smoothstep((phase-2)/2)
            self.targets[0] = self.origins[0]+np.array([-.012, .016, 0.])*amplitude
            self.grasps[0].drive_to(self.targets[0])
            self.grasps[1].drive_to(self.origins[1])

    def observe(self, t, monitor):
        if self.targets is None:
            return
        positions = [monitor.last_positions[g.indices].mean(axis=0) for g in self.grasps]
        errors = [float(np.linalg.norm(point-target)) for g, point, target in
                  zip(self.grasps, positions, self.targets) if g.active]
        self.samples.append(dict(time_s=t, active_constraints=sum(g.active for g in self.grasps),
                                 band_centers=[p.tolist() for p in positions],
                                 max_follow_error_m=max(errors, default=0.)))

    def release(self, t):
        if any(grasp.active for grasp in self.grasps):
            self.events.append(dict(time_s=t, event='release_all_fixtures'))
        for grasp in self.grasps:
            grasp.release()

    def report(self):
        release = self.specification()['release_s']
        error = max((s['max_follow_error_m'] for s in self.samples), default=0.)
        checks = dict(post_release_observed=bool(self.samples and self.samples[-1]['time_s'] >= release+5.-1e-8),
                      released=not any(g.active for g in self.grasps),
                      band_follow_error=error <= .002)
        return dict(kind='declared_translation_only_soft_grasp_fixture', mode=self.mode,
                    events=self.events, final_active_constraints=sum(g.active for g in self.grasps),
                    checks=checks, passed=all(checks.values()), max_band_follow_error_m=error,
                    robot_grasp_executed=False,
                    material_vertices=[g.indices.tolist() for g in self.grasps])
