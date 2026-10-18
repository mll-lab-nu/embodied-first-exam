"""Public historical circuit shapes and time-indexed path geometry (no hidden draws)."""

from functools import lru_cache
import json
from pathlib import Path


@lru_cache(maxsize=1)
def catalog():
    return json.loads(Path(__file__).with_name("circuits.json").read_text())


def track_ids():
    return ["zigzag", *sorted(k for k, v in catalog()["circuits"].items() if v["available"])]


def resolve_track(name):
    if name == "zigzag":
        return name
    if name in catalog()["circuits"]:
        if not catalog()["circuits"][name]["available"]:
            raise ValueError(catalog()["circuits"][name]["unavailable_reason"])
        return name
    choices = [
        (max(v["years"]), k) for k, v in catalog()["circuits"].items() if v["circuit_id"] == name and v["available"]
    ]
    if not choices:
        raise ValueError(f"Unknown circuit/layout: {name}")
    return max(choices)[1]


class Route:
    def __init__(self, name, revision="circuit-sector/1"):
        import numpy as np

        self.name = resolve_track(name)
        if revision not in ("circuit-sector/1", "circuit-lap/2", "compact-30s/1"):
            raise ValueError(f"Unknown route revision: {revision}")
        self.revision = revision
        if self.name == "zigzag":
            t = np.linspace(0, 2 * np.pi, 1024, endpoint=False)
            points = np.column_stack((12 * np.cos(t), 6 * np.sin(t) + 1.8 * np.sin(5 * t)))
            self.metadata = dict(name="Synthetic zigzag", circuit_id="zigzag", source_length_m=None)
        else:
            self.metadata = catalog()["circuits"][self.name]
            points = np.asarray(self.metadata["points"], dtype=float)
        if revision == "compact-30s/1":
            points = np.asarray(compact_catalog()["routes"][self.name]["points"], dtype=float)
        # Uniform scaling preserves aspect ratio; account for fixed RC steering limit.
        derivative = (np.roll(points, -1, axis=0) - np.roll(points, 1, axis=0)) / 2
        second = np.roll(points, -1, axis=0) - 2 * points + np.roll(points, 1, axis=0)
        curvature = (derivative[:, 0] * second[:, 1] - derivative[:, 1] * second[:, 0]) / np.maximum(
            np.linalg.norm(derivative, axis=1) ** 3, 1e-18
        )
        perimeter = np.linalg.norm(np.roll(points, -1, axis=0) - points, axis=1).sum()
        factor = max(80 / perimeter, float(np.max(np.abs(curvature))) / 0.85)
        if revision == "compact-30s/1":
            factor = 1.0
        self.points = points * factor
        self.delta = np.roll(self.points, -1, axis=0) - self.points
        self.segment_lengths = np.linalg.norm(self.delta, axis=1)
        self.arc = np.r_[0, np.cumsum(self.segment_lengths)]
        self.length = float(self.arc[-1])
        self.half_extent = float(np.max(np.abs(self.points))) + 3
        self.scale = self.length / self.metadata["source_length_m"] if self.metadata["source_length_m"] else None

    def at(self, distance):
        """Periodic Catmull-Rom interpolant returns x,y,yaw,curvature."""
        import numpy as np

        s = np.asarray(distance) % self.length
        index = np.minimum(np.searchsorted(self.arc, s, side="right") - 1, len(self.points) - 1)
        u = (s - self.arc[index]) / self.segment_lengths[index]
        p0, p1, p2, p3 = (self.points[(index + j) % len(self.points)] for j in (-1, 0, 1, 2))
        a = 2 * p1
        b = -p0 + p2
        c = 2 * p0 - 5 * p1 + 4 * p2 - p3
        d = -p0 + 3 * p1 - 3 * p2 + p3
        u = u[..., None]
        xy = (a + b * u + c * u * u + d * u * u * u) / 2
        tangent = (b + 2 * c * u + 3 * d * u * u) / 2
        second = c + 3 * d * u
        curvature = (tangent[..., 0] * second[..., 1] - tangent[..., 1] * second[..., 0]) / np.maximum(
            np.linalg.norm(tangent, axis=-1) ** 3, 1e-18
        )
        return np.concatenate(
            (xy, np.arctan2(tangent[..., 1], tangent[..., 0])[..., None], curvature[..., None]), axis=-1
        )

    def reference(self, t, command):
        import numpy as np

        velocity = float(command.get("speed", 0.85))
        s = command.get("start_fraction", 0.0) * self.length + velocity * (t * t / 2 if t < 1 else t - 0.5)
        x, y, yaw, curvature = self.at(s)
        return np.array([x, y, yaw, velocity * min(t, 1.0), curvature])

    def distance(self, positions):
        """Exact distance to the discretized centerline, chunked to bound memory."""
        import numpy as np

        result = []
        for chunk in np.array_split(np.asarray(positions), max(1, len(positions) // 128)):
            diff = chunk[:, None, :] - self.points[None, :, :]
            alpha = np.clip(np.sum(diff * self.delta, axis=-1) / self.segment_lengths**2, 0, 1)
            result.extend(np.sqrt(np.min(np.sum((diff - alpha[..., None] * self.delta) ** 2, axis=-1), axis=1)))
        return np.asarray(result)


@lru_cache(maxsize=8)
def get_route(name, revision="circuit-sector/1"):
    return Route(name, revision)


@lru_cache(maxsize=1)
def route_metadata_catalog():
    """Frozen lengths for stdlib-only generation and worker budgeting; no physics imports."""
    import hashlib

    data = json.loads(Path(__file__).with_name("route_lengths.json").read_text())
    actual = hashlib.sha256(Path(__file__).with_name("circuits.json").read_bytes()).hexdigest()
    if data["catalog_sha256"] != actual:
        raise ValueError("Route length metadata does not match circuit catalog")
    return data


def route_metadata(name):
    """Return a copy of the public length and full-lap budget for one layout."""
    return dict(route_metadata_catalog()["routes"][resolve_track(name)])


def route_budget(name):
    """Public stdlib budgets from frozen geometry, never from policy/request values.

    Simulation/row bounds are conservative; wall time is a hardware-specific
    planning estimate, not a guaranteed limit or an agent time-cap decision.
    """
    import math

    metadata = route_metadata(name)
    horizon_bound = math.ceil(metadata["horizon_s"]) + 1
    return dict(
        schema="anycar-lap-budget/1",
        track_id=resolve_track(name),
        horizon_upper_bound_s=horizon_bound,
        control_steps_upper_bound=horizon_bound * 50,
        telemetry_rows_upper_bound=horizon_bound * 10 + 1,
        decoded_frames_upper_bound=horizon_bound * 10 + 1,
        render_wall_time_estimate_s=2 * horizon_bound + 60,
        wall_time_estimate_basis="CPU OSMesa planning estimate: 2 wall seconds per simulated second plus 60 seconds; validate on deployment hardware",
        wall_time_is_guaranteed_bound=False,
    )


@lru_cache(maxsize=1)
def compact_catalog():
    """Public, precomputed compact geometry; loaded without NumPy."""
    import hashlib

    data = json.loads(Path(__file__).with_name("compact_routes.json").read_text())
    actual = hashlib.sha256(Path(__file__).with_name("circuits.json").read_bytes()).hexdigest()
    if data["source_catalog_sha256"] != actual:
        raise ValueError("Compact geometry does not match source circuit catalog")
    return data


def compact_route_budget(name):
    layout = resolve_track(name)
    if layout not in compact_catalog()["routes"]:
        raise ValueError("Unavailable compact layout")
    return dict(schema="anycar-lap-budget/1", track_id=layout, route_revision="compact-30s/1",
                horizon_upper_bound_s=30, control_steps_upper_bound=1500,
                telemetry_rows_upper_bound=301, decoded_frames_upper_bound=301,
                render_wall_time_estimate_s=120,
                wall_time_estimate_basis="CPU OSMesa planning estimate; validate on deployment hardware",
                wall_time_is_guaranteed_bound=False)
