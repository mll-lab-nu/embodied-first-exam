"""Explicit soft-grasp fixture: feed a free end through R1, slide, release.

This qualifies a local rope/ring interaction, never a robot execution.
"""
import numpy as np

from topogym.tasks.knot_untying.probe_actions import smoothstep
from .geometry import route_crossings


class RingContactActions:
    def __init__(self):
        self.band = None
        self.origin = None
        self.events, self.samples = [], []

    def declare(self, base, rope, centerline, backend):
        from topogym.primitives.fem_attachment import FEMRopeAttachment
        # A fixed material location is required for mesh-refinement comparisons.
        # Halfway along source segment 79 is 6.875 mm before endpoint 80,
        # independently of the number of subdivisions used by this run.
        subdivisions = (len(centerline)-1)//80
        center = (centerline[-1]+centerline[-1-subdivisions])/2
        self.band = FEMRopeAttachment(rope, center, radius=.008, strength=100.)

    def specification(self):
        return dict(kind="declared_soft_grasp_fixture", fixture_strength=100.,
            band_radius_m=.008, material_selector="6.875 mm before endpoint 80",
            engage_s=1., insertion_interval_s=[5., 7.], tangential_slide_interval_s=[9., 11.],
            release_s=12., minimum_duration_s=20.,
            required_observations=["R1- crossing", "native ring contact", "contact sliding >= 10 mm",
                                   "full release", "post-release rest"],
            robot_grasp_executed=False, runtime_fem_position_overwrites=False)

    def configure(self, task, controller, monitor):
        self.task, self.monitor = task, monitor
        self.ring = task.layout.rings()[0]
        self.center = np.asarray(self.ring["center_m"])
        self.part = next(p for p in monitor.ccd.parts if p["name"] == task.fixtures["R1"].base_link.name)

    def update(self, t):
        if t < 1.:
            return
        if self.origin is None:
            self.origin = self.band.attach().copy()
            c = self.center
            self.waypoints = [(1., self.origin), (3., [self.origin[0], self.origin[1], c[2]+.045]),
                (5., c+[.12, 0, 0]), (7., c+[-.12, 0, 0]), (9., c+[-.12, 0, 0]),
                (11., c+[-.12, .045, 0]), (12., c+[-.12, .045, 0])]
            self.events.append(dict(time_s=t, event="fixture_engaged"))
        if t >= 12.:
            if self.band.active:
                self.band.release()
                self.events.append(dict(time_s=t, event="fixture_released"))
            return
        for (a, p), (b, q) in zip(self.waypoints[:-1], self.waypoints[1:]):
            if a <= t <= b:
                p, q = np.asarray(p), np.asarray(q)
                self.target = p+smoothstep((t-a)/(b-a))*(q-p)
                self.band.drive_to(self.target)
                break

    def observe(self, t, monitor):
        if self.samples and t-self.samples[-1]["time_s"] < .049:
            return
        crossings = route_crossings(monitor.last_centers, [self.ring], self.task.layout.radius)
        gap = None
        if self.part["checker"] is not None:
            gap = self.part["checker"].minimum_distance(
                np.vstack((monitor.last_positions, self.part["previous"])), .0012)
        error = (float(np.linalg.norm(self.band.band_center()-self.target))
                 if self.band.active else 0.)
        self.samples.append(dict(time_s=t, active_constraint=self.band.active, ring_gap_m=gap,
            band_center=self.band.band_center().tolist(), follow_error_m=error, crossings=crossings))

    def report(self):
        threaded = [s for s in self.samples if 7. <= s["time_s"] < 12.
                    and [h["sign"] for h in s["crossings"]] == [-1]]
        contact = [s for s in threaded if s["ring_gap_m"] is not None and s["ring_gap_m"] < .0008]
        crossing_points = np.array([s["crossings"][0]["point_m"] for s in contact])
        slide = float(np.linalg.norm(np.ptp(crossing_points, axis=0))) if len(contact) else 0.
        follow_error = max((s["follow_error_m"] for s in self.samples), default=0.)
        checks = dict(threaded=len(threaded) >= 20, contacted=len(contact) >= 3,
                      tangential_slide=slide >= .01, follow_error=follow_error < .002,
                      released=bool(self.origin is not None and not self.band.active),
                      post_release_duration=bool(self.samples and self.samples[-1]["time_s"] >= 19.9))
        return dict(kind="declared_soft_grasp_fixture", events=self.events, checks=checks,
            passed=all(checks.values()), contact_samples=len(contact), threaded_samples=len(threaded),
            observed_contact_crossing_travel_m=slide, max_band_follow_error_m=follow_error,
            material_vertices=self.band.indices.tolist(), final_active_constraints=int(self.band.active),
            robot_grasp_executed=False)
