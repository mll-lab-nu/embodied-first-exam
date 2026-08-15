"""Is the rope being wrung, since when, and by how much.

`rope_twist_turns` in `rope_winding.py` answers the same question spatially --
one number per call, end to end along the rope -- and it carries a bias nobody
could size. Measured 2026-08-14: it read +0.40 turns with the rope lying
untouched on the board, ten steps into a run. A rope cannot acquire 0.4 turns of
torsion lying still, so that is not torsion.

The bias is a frame mismatch. That measure compares each cross section's SPAWN
phase against its CURRENT phase, but the two phases are read in frames
parallel-transported along different curves: the spawn phase along the dense
design spline (`world/rope.py` `tube_material_coords`), the current phase along
the 150-bin polyline. Parallel transport is path dependent, this task's spawn
route is not planar (the anchored end dives into the terminal and arcs back out),
so the two accumulate different frame rotation and the difference lands straight
in the reading. It also drifts as the rope changes shape, so it cannot be
subtracted as a constant.

This module measures the same physical quantity a different way: it never
transports a frame ALONG the rope. Each material bin carries its own reference
direction, transported forward IN TIME as its tangent turns, and the bin's twist
is how far its material has rotated away from that reference. At t=0 the reading
is zero by construction, so there is no bias to size.

That the time-transported reference has holonomy of its own -- a tangent tracing
a loop on the direction sphere brings the reference back rotated -- is not an
error to correct. It is the Bishop frame, and twist is defined as the material
frame's departure from it. A rope that is bent without being wrung reads zero,
which is exactly what the spatial measure cannot promise.
"""

from __future__ import annotations

import numpy as np

from .cable_routing import rope_particles
from .pbd_probe import StepProbe
from .rope_winding import material_bins, material_coords


def _wrap_to_pi(angle):
    return np.arctan2(np.sin(angle), np.cos(angle))


def _perpendicular(vectors: np.ndarray) -> np.ndarray:
    """Some unit vector perpendicular to each row. Any choice will do.

    The reference direction's starting phase is arbitrary -- every reading here
    is a difference against where it started -- so this only has to be stable and
    non-degenerate. Crossing with whichever axis the tangent leans on least is
    both.
    """

    axes = np.zeros_like(vectors)
    axes[np.arange(len(vectors)), np.argmin(np.abs(vectors), axis=1)] = 1.0
    out = np.cross(vectors, axes)
    return out / np.linalg.norm(out, axis=1, keepdims=True)


class TwistTracker:
    """Per-bin twist against a reference frame transported in time.

    Arrays in, numbers out -- no scene -- so the construction can be checked
    against synthesised motion without a solver
    (`tests/check_rope_winding_geometry.py`).

    Sampling rate is a correctness requirement, not a convenience: no bin's phase
    may move more than half a turn between two `update` calls, or the unwrap
    silently loses turns. `max_step` reports the worst move each call so an
    under-sampled run announces itself. It cannot catch an exact whole-turn
    alias -- that is invisible in the signal -- so pick the rate from the fastest
    motion in the route rather than from this number.
    """

    #: A bin needs a few outer nodes for its circular mean to mean anything.
    MIN_OUTER_NODES = 3

    def __init__(self, nodes, groups, outer) -> None:
        nodes = np.asarray(nodes, dtype=float)
        outer = np.asarray(outer, dtype=bool)
        # Keep only bins with enough shell nodes; a bin of near-axis nodes has no
        # meaningful azimuth, the same reason `rope_twist_turns` filters them.
        self._members = [
            group[outer[group]]
            for group in groups
            if int(np.count_nonzero(outer[group])) >= self.MIN_OUTER_NODES
        ]
        if len(self._members) < 2:
            raise ValueError(
                "TwistTracker needs at least two bins with shell nodes; got "
                f"{len(self._members)}."
            )
        self._centers = self._bin_centers(nodes)
        tangents = self._tangents(self._centers, previous=None)
        self._tangents_prev = tangents
        self._u = _perpendicular(tangents)
        self._phase0 = self._phases(nodes, self._centers, tangents, self._u)
        #: Bins that survived the shell filter. Worth reporting: a lighter
        #: mesh keeps fewer, and how many there are sets `peak_s`'s resolution.
        self.bin_count = len(self._members)
        self._psi = np.zeros(len(self._members), dtype=float)
        self._total = np.zeros(len(self._members), dtype=float)

    # -- geometry -------------------------------------------------------------

    def _bin_centers(self, nodes: np.ndarray) -> np.ndarray:
        return np.stack([nodes[members].mean(axis=0) for members in self._members])

    def _tangents(self, centers: np.ndarray, *, previous) -> np.ndarray:
        delta = np.empty_like(centers)
        delta[1:-1] = centers[2:] - centers[:-2]
        delta[0] = centers[1] - centers[0]
        delta[-1] = centers[-1] - centers[-2]
        norm = np.linalg.norm(delta, axis=1, keepdims=True)
        # A bin pair that has collapsed has no direction to offer; hold the last
        # one rather than normalising noise.
        degenerate = (norm < 1e-9).ravel()
        out = np.where(degenerate[:, None], 0.0, delta / np.maximum(norm, 1e-12))
        if np.any(degenerate):
            fallback = previous if previous is not None else _perpendicular(out + 1e-9)
            out[degenerate] = fallback[degenerate]
        return out

    def _phases(self, nodes, centers, tangents, u) -> list[np.ndarray]:
        v = np.cross(tangents, u)
        return [
            np.arctan2(
                (nodes[members] - centers[i]) @ v[i],
                (nodes[members] - centers[i]) @ u[i],
            )
            for i, members in enumerate(self._members)
        ]

    # -- update ---------------------------------------------------------------

    def update(self, nodes) -> dict:
        nodes = np.asarray(nodes, dtype=float)
        centers = self._bin_centers(nodes)
        tangents = self._tangents(centers, previous=self._tangents_prev)

        # Transport the reference forward in time: drop whatever component the
        # new tangent absorbed, renormalise. This is what makes a bend read as
        # zero twist -- the reference turns with the rope, the material does not
        # have to.
        u = self._u - tangents * np.einsum("ij,ij->i", self._u, tangents)[:, None]
        norm = np.linalg.norm(u, axis=1, keepdims=True)
        flipped = (norm < 1e-6).ravel()
        if np.any(flipped):
            # The tangent turned through a right angle or more in one step. The
            # reference cannot be carried across that; restart it there and let
            # `max_step` say the sampling was too coarse.
            u[flipped] = _perpendicular(tangents[flipped])
            norm = np.linalg.norm(u, axis=1, keepdims=True)
        u = u / np.maximum(norm, 1e-12)

        phases = self._phases(nodes, centers, tangents, u)
        # Circular mean of each node's departure from where it started: robust to
        # the odd node the solver has moved across the section.
        psi = np.array(
            [
                float(np.angle(np.mean(np.exp(1j * (now - was)))))
                for now, was in zip(phases, self._phase0)
            ]
        )
        step = _wrap_to_pi(psi - self._psi)
        self._total += step
        self._psi = psi
        self._u = u
        self._tangents_prev = tangents
        self._centers = centers

        turns = self._total / (2.0 * np.pi)
        return {
            "net": float(turns[-1] - turns[0]),
            "span": float(turns.max() - turns.min()),
            "peak_s": float((int(np.argmax(np.abs(turns))) + 0.5) / len(turns)),
            "max_step": float(np.max(np.abs(step))),
        }


class TwistProbe(StepProbe):
    """Drive a `TwistTracker` from the live scene and report what it says."""

    #: Below this the reading is settling noise rather than a wrung rope. A
    #: class constant rather than a config key, as `RopeWindingProbe`'s own
    #: thresholds are: it is a reporting cutoff, not something a run tunes.
    ONSET_TURNS = 0.15
    #: Half a turn is where the unwrap breaks; warn well before it.
    STEP_WARN = 0.5 * np.pi
    #: Own binning rather than the criterion's `success.centerline_bins`. That
    #: one is 150, chosen for winding-number resolution; at `run.lite`'s coarser
    #: mesh 150 bins leave some with too few shell nodes for a circular mean to
    #: mean anything. 32 bins is 20 mm of rope each -- finer than `peak_s` needs
    #: and thick enough to survive the lightest mesh this task ships.
    BINS = 32

    def __init__(self, scene, status, *, every: int) -> None:
        super().__init__(scene.scene, every=every)
        self.rope_scene = scene
        self.status = status if status is not None else {}
        groups = material_bins(scene, bins=self.BINS)
        coords = material_coords(scene)
        shell = 0.5 * float(scene.layout.cfg.rope.radius)
        outer = np.hypot(coords[:, 1], coords[:, 2]) > shell
        self.tracker = TwistTracker(rope_particles(scene), groups, outer)
        self.latest = {"net": 0.0, "span": 0.0, "peak_s": float("nan"), "max_step": 0.0}
        self.max_net = 0.0
        self.max_span = 0.0
        self.worst_step = 0.0
        self.onset_step: int | None = None
        self.onset_phase: str | None = None

    def _swivel_text(self) -> str:
        """How far the follow bands have let the rope's ends turn, in turns.

        The other half of the twist question: the rope's only route out of a
        wrung state is a band that yields. `-` where the backend has no bands to
        report (PBD), which is not the same as a band reading zero.
        """

        backend = getattr(self.rope_scene, "rope_backend", None)
        turns = getattr(backend, "swivel_turns", None)
        if turns is None:
            return "-"
        return ",".join(f"{value:+.3f}" for value in turns()) or "-"

    def _sample(self) -> None:
        metrics = self.tracker.update(rope_particles(self.rope_scene))
        self.latest = metrics
        phase = str(self.status.get("phase", "?"))
        self.max_net = max(self.max_net, abs(metrics["net"]))
        self.max_span = max(self.max_span, metrics["span"])
        self.worst_step = max(self.worst_step, metrics["max_step"])
        flags = " UNDERSAMPLED" if metrics["max_step"] > self.STEP_WARN else ""
        if self.onset_step is None and metrics["span"] >= self.ONSET_TURNS:
            self.onset_step = self.count
            self.onset_phase = phase
            print(
                f"twist_onset step={self.count:05d} phase={phase} "
                f"span={metrics['span']:+.3f} net={metrics['net']:+.3f} "
                f"peak_s={metrics['peak_s']:.3f}",
                flush=True,
            )
        print(
            f"TWIST step={self.count:05d} phase={phase} "
            f"span={metrics['span']:+.3f} net={metrics['net']:+.3f} "
            f"peak_s={metrics['peak_s']:.3f} "
            f"swivel={self._swivel_text()} "
            f"max_step_deg={np.degrees(metrics['max_step']):.1f}{flags}",
            flush=True,
        )

    def summary_text(self) -> str:
        onset = "none" if self.onset_step is None else f"{self.onset_step:05d}"
        # `span` leads because it is the answer to "how wrung is the rope". `net`
        # is end-to-end and cancels whenever the twist piles up in the middle,
        # which is exactly what this route does -- on 2026-08-14's two-turn run
        # net read +0.24 while span read +0.88, and net's small number was taken
        # for success. Order the line so that cannot happen twice.
        return (
            f"span={self.latest['span']:+.3f} max_span={self.max_span:.3f} "
            f"peak_s={self.latest['peak_s']:.3f} bins={self.tracker.bin_count} "
            f"net={self.latest['net']:+.3f} max_net={self.max_net:.3f} "
            f"onset_step={onset} onset_phase={self.onset_phase or 'none'} "
            f"worst_step_deg={np.degrees(self.worst_step):.1f} "
            f"swivel={self._swivel_text()}"
        )
