"""Continuous collision certificates for the authored box-compound prototype.

SAT projections are exact for detecting OBB overlap. A positive SAT gap is a
lower bound on Euclidean separation, not the Euclidean distance itself. Motion
certification bounds every material point's speed between sampled poses, so a
successful report covers the whole continuous path, not just its keyframes.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from .geometry import ASSET_ROOT, CoilAssembly, geometry_report, load_template

REFERENCE_URL = "https://www.eureka-puzzle.eu/wp-content/uploads/2022/09/515056-Huzzle-Cast-Coil-Oct-2017.pdf"
REFERENCE_STEPS = [
    "相对滑开", "银件向右转动四分之一圈", "银件向下滑动", "银件向上翻转四分之一圈",
    "银件向右转动四分之一圈", "银件向下翻转四分之一圈", "银件再次向右转动四分之一圈", "向上移出银件",
]

VARIANTS = json.loads((ASSET_ROOT/"variants.json").read_text())["presets"]


class CompoundCollision:
    def __init__(self, fixed_boxes, moving_boxes):
        self.fixed = np.asarray(fixed_boxes, dtype=float)
        self.moving = np.asarray(moving_boxes, dtype=float)
        for boxes in (self.fixed, self.moving):
            if boxes.ndim != 3 or boxes.shape[1:] != (2, 3) or not len(boxes):
                raise ValueError("Expected nonempty (N, 2, 3) box bounds")
            if not np.isfinite(boxes).all() or np.any(boxes[:, 1] <= boxes[:, 0]):
                raise ValueError("Invalid box bounds")
        self.ac, self.bc = self.fixed.mean(axis=1), self.moving.mean(axis=1)
        self.ah, self.bh = np.diff(self.fixed, axis=1)[:, 0]/2, np.diff(self.moving, axis=1)[:, 0]/2

    def gap(self, rotation, translation):
        """Min over pairs of maximal normalized separating-axis gaps, in m."""
        R, t = np.asarray(rotation, dtype=float), np.asarray(translation, dtype=float)
        if R.shape != (3, 3) or t.shape != (3,) or not np.isfinite(np.r_[R.ravel(), t]).all():
            raise ValueError("Invalid relative pose")
        axes = np.concatenate((np.eye(3), R.T, np.cross(np.eye(3)[:, None, :], R.T[None]).reshape(-1, 3)))
        norm = np.linalg.norm(axes, axis=1)
        axes = axes[norm > 1e-10]/norm[norm > 1e-10, None]
        delta = (self.bc@R.T+t)[None]-self.ac[:, None]
        intervals = np.abs(delta@axes.T) - (self.ah@np.abs(axes.T))[:, None] - (self.bh@np.abs(R.T@axes.T))[None]
        return float(intervals.max(axis=-1).min())


def box_corners(boxes):
    indices = np.array([[x, y, z] for x in (0, 1) for y in (0, 1) for z in (0, 1)])
    return np.concatenate([np.where(indices, hi, lo) for lo, hi in boxes])


@dataclass
class Motion:
    name: str
    duration_s: float
    start_rotation: np.ndarray
    start_translation: np.ndarray
    end_translation: np.ndarray | None = None
    axis: np.ndarray | None = None
    angle_rad: float = 0.
    pivot: np.ndarray | None = None

    def pose(self, u):
        if self.axis is None:
            return self.start_rotation, (1-u)*self.start_translation+u*self.end_translation
        delta = Rotation.from_rotvec(self.axis*self.angle_rad*u).as_matrix()
        return delta@self.start_rotation, self.pivot+delta@(self.start_translation-self.pivot)

    def point_speed_bound(self, corners):
        """Maximum material-point speed with respect to normalized u, not time."""
        if self.axis is None:
            return float(np.linalg.norm(self.end_translation-self.start_translation))
        p = corners@self.start_rotation.T+self.start_translation-self.pivot
        radius = np.linalg.norm(np.cross(p, self.axis), axis=1).max()
        return float(abs(self.angle_rad)*radius)

    def to_dict(self):
        return {k: v.tolist() if isinstance(v, np.ndarray) else v for k, v in vars(self).items()}


def prototype_route(assembly):
    """A discovered three-motion route. This is NOT the official eight steps."""
    u = assembly.unit
    slide = Motion("prototype_slide", 1.5, np.eye(3), np.zeros(3), np.array([-7.25, 0, 0])*u)
    R, t = slide.pose(1.)
    turn = Motion("prototype_quarter_turn", 3.0, R, t, axis=np.array([0., 1., 0.]),
                  angle_rad=-np.pi/2, pivot=np.array([1.5, 0, -10.5])*u)
    R, t = turn.pose(1.)
    extract = Motion("prototype_extract", 2.5, R, t, np.array([60., 0, -19.25])*u)
    return [slide, turn, extract]


def assembly_route(assembly):
    if "appearance_design" in assembly.template:
        from .appearance import appearance_route
        return appearance_route(assembly)
    if "inverse_design" in assembly.template:
        from .inverse_design import variant_route
        if not np.isclose(assembly.scale, 3.0):
            raise ValueError("Inverse-designed routes are authored for the 3x instance")
        design = assembly.template["inverse_design"]
        return variant_route(design["kind"], design.get("parameters"))
    return prototype_route(assembly)


def certify_motion(collision, motion, *, margin_m, max_depth=22):
    """Prove separation on every interval using a material-speed bound.

    A midpoint gap g and displacement bound L*du/2 imply all points in that
    interval have separation >= g-L*du/2. Unresolved intervals fail closed.
    """
    if not np.isfinite(margin_m) or margin_m <= 0:
        raise ValueError("The certificate requires a positive margin")
    speed = motion.point_speed_bound(box_corners(collision.moving))
    pending, count, leaves = [(0., 1., 0)], 0, 0
    lower, minimum_sample = float("inf"), float("inf")
    witness = None
    for endpoint in (0., 1.):
        gap = collision.gap(*motion.pose(endpoint))
        minimum_sample = min(minimum_sample, gap)
        count += 1
        if gap < margin_m:
            witness = dict(u=endpoint, gap_m=gap, reason="endpoint violates margin")
            break
    while pending and witness is None:
        a, b, depth = pending.pop()
        u = (a+b)/2
        gap = collision.gap(*motion.pose(u))
        count += 1
        minimum_sample = min(minimum_sample, gap)
        bound = gap-speed*(b-a)/2
        if bound >= margin_m:
            leaves += 1
            lower = min(lower, bound)
        elif gap < margin_m:
            witness = dict(u=u, gap_m=gap, reason="sample violates margin")
        elif depth >= max_depth:
            witness = dict(u=u, gap_m=gap, reason="continuous interval unresolved")
        else:
            pending.extend(((u, b, depth+1), (a, u, depth+1)))
    return dict(name=motion.name, passed=witness is None, method="SAT plus adaptive material-displacement bound",
        margin_m=margin_m, pose_queries=count, certified_intervals=leaves,
        minimum_sample_sat_gap_m=minimum_sample,
        certified_separation_lower_bound_m=lower if witness is None else None,
        witness=witness, motion=motion.to_dict())


def geometric_audit(assembly):
    collision = CompoundCollision(*(b.boxes for b in assembly.bodies))
    route = assembly_route(assembly)
    margin = .02*assembly.unit
    certificate = [certify_motion(collision, m, margin_m=margin) for m in route]
    wrong = Motion("opposite_turn_negative_control", 3., route[1].start_rotation,
        route[1].start_translation, axis=route[1].axis, angle_rad=np.pi/2, pivot=route[1].pivot)
    wrong_result = certify_motion(collision, wrong, margin_m=margin)
    straight = []
    for axis in range(3):
        for sign in (-1, 1):
            motion = Motion(f"straight_{'xyz'[axis]}_{sign:+d}", 1., np.eye(3), np.zeros(3),
                            np.eye(3)[axis]*sign*80*assembly.unit)
            straight.append(certify_motion(collision, motion, margin_m=margin))
    final_R, final_t = route[-1].pose(1)
    a, b = assembly.bodies
    final_points = box_corners(b.boxes)@final_R.T+final_t
    exit_gap = float(final_points[:, 0].min()-a.boxes[:, 1, 0].max())
    payload = json.dumps(assembly.template, sort_keys=True, separators=(",", ":"))
    return dict(scope="authored prototype; continuous rigid geometry without robot or dynamics",
        template_sha256=hashlib.sha256(payload.encode()).hexdigest(), geometry=geometry_report(assembly),
        source=dict(url=REFERENCE_URL, steps_zh=REFERENCE_STEPS,
                    metric_poses_provided=False, exact_pivots_provided=False),
        prototype_route_certified=all(c["passed"] for c in certificate) and exit_gap > 0,
        route_identity=("motion_first_inverse_" + assembly.template["inverse_design"]["kind"]
                        if "inverse_design" in assembly.template else "discovered_three_motion_prototype_route_not_official_tutorial"),
        route=certificate, final_separating_plane_gap_m=exit_gap,
        opposite_turn_negative_control=wrong_result, straight_extraction_controls=straight,
        official_route_verified=False, commercial_replica_verified=False,
        global_unsolvability_claim=False,
        limitations=["The eight illustrated official moves have not been mapped to verified metric poses.",
            "A shorter route in the approximation does not establish an error in the commercial puzzle.",
            "This certificate concerns the authored compounds, not robot reachability or contact dynamics."])


def write_geometric_audit(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    result = {}
    for name, parameters in VARIANTS.items():
        result[name] = dict(**parameters, **geometric_audit(CoilAssembly(scale=parameters["scale"])))
    (output/"geometry_audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+"\n")
    return result


def shape_sensitivity_audit():
    """Unqualified geometry perturbations: reject path reuse, not all solutions."""
    results = []
    for width in (7.5, 8., 9.):
        template = load_template()
        template["band_width"] = width
        template["bridge_height"] = template["outer_width"]/2-width-.375
        audit = geometric_audit(CoilAssembly(template, scale=3))
        results.append(dict(band_width_mm=width, bridge_height_mm=template["bridge_height"],
            initial_geometry_valid=audit["geometry"]["passed"],
            existing_route_reusable=audit["prototype_route_certified"],
            failed_segments=[s for s in audit["route"] if not s["passed"]],
            qualified_variant=False, global_unsolvability_claim=False))
    return results
