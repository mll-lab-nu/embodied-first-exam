"""Coil reference motions and sampling, without physics execution."""

from dataclasses import dataclass
import numpy as np
from topogym.utils.geometry.rigid_motion import RigidMotionSegment
from topogym.assets.geometry.cast_coil_variants import family_parameter, KINDS
from topogym.solvers.collision.box_compounds import box_corners


@dataclass
class ScrewMotion(RigidMotionSegment):
    advance: np.ndarray | None = None

    def __post_init__(self):
        super().__post_init__()
        self.advance = np.array(self.advance, dtype=float, copy=True)
        if self.advance.shape != (3,) or not np.isfinite(self.advance).all():
            raise ValueError("Screw motion requires a finite advance vector")

    def pose(self, u):
        r, t = super().pose(u)
        return r, t + self.advance * u

    def point_speed_bound(self, corners):
        return super().point_speed_bound(corners) + float(np.linalg.norm(self.advance))


def variant_route(kind, parameters=None):
    if kind not in KINDS:
        raise ValueError(kind)
    amount = family_parameter(kind, parameters)
    pivot = np.array([0.0045, 0.0, -0.0315])
    slide = np.array([-0.02175, 0.0, 0.0])
    if kind == "eccentric_turn":
        pivot += [amount, 0, 0]
        slide += [-2 * amount, 0, 0]
    moves = [RigidMotionSegment("prototype_slide", 1.5, np.eye(3), np.zeros(3), slide)]
    kw = dict(axis=np.array([0.0, 1.0, 0.0]), pivot=pivot)
    if kind == "split_turn_offset":
        moves.append(
            RigidMotionSegment(
                "turn_first_45", 1.5, np.eye(3), slide, angle_rad=-np.pi / 4, **kw
            )
        )
        r, t = moves[-1].pose(1)
        shift = np.array([0.0, 0.0, amount])
        moves.append(RigidMotionSegment("intermediate_offset", 1.0, r, t, t + shift))
        r, t = moves[-1].pose(1)
        moves.append(
            RigidMotionSegment(
                "turn_second_45",
                1.5,
                r,
                t,
                axis=kw["axis"],
                pivot=pivot + shift,
                angle_rad=-np.pi / 4,
            )
        )
    elif kind == "axial_screw_turn":
        moves.append(
            ScrewMotion(
                "screw_turn",
                3.0,
                np.eye(3),
                slide,
                angle_rad=-np.pi / 2,
                advance=np.array([0.0, amount, 0.0]),
                **kw,
            )
        )
    else:
        moves.append(
            RigidMotionSegment(
                "prototype_quarter_turn",
                3.0,
                np.eye(3),
                slide,
                angle_rad=-np.pi / 2,
                **kw,
            )
        )
    r, t = moves[-1].pose(1)
    moves.append(RigidMotionSegment("prototype_extract", 2.5, r, t, t + [0.207, 0, 0]))
    return moves


def sample_route(motions, boxes, displacement_m=0.00015):
    corners = box_corners(boxes)
    samples = []
    for motion in motions:
        n = max(
            2, int(np.ceil(motion.point_speed_bound(corners) / (2 * displacement_m)))
        )
        for u in np.linspace(0, 1, n + 1):
            samples.append((*motion.pose(float(u)), motion.name))
    return samples


def prototype_route(assembly):
    """A discovered three-motion route. This is NOT the official eight steps."""
    u = assembly.unit
    slide = RigidMotionSegment(
        "prototype_slide", 1.5, np.eye(3), np.zeros(3), np.array([-7.25, 0, 0]) * u
    )
    R, t = slide.pose(1.0)
    turn = RigidMotionSegment(
        "prototype_quarter_turn",
        3.0,
        R,
        t,
        axis=np.array([0.0, 1.0, 0.0]),
        angle_rad=-np.pi / 2,
        pivot=np.array([1.5, 0, -10.5]) * u,
    )
    R, t = turn.pose(1.0)
    extract = RigidMotionSegment(
        "prototype_extract", 2.5, R, t, np.array([60.0, 0, -19.25]) * u
    )
    return [slide, turn, extract]
