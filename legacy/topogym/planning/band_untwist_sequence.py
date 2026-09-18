"""Offline move model for `band_untwist`: which plug, lifted up to where, laid where.

Physical picture. One rope lies flat on the table with a plug on each end and
crosses itself once or twice. The arm only ever grasps a plug. One move = grasp
a plug, lift until the rope from the plug up to the *lift point* hangs below the
hand, carry it sideways, lay it down. Everything past the lift point stays where
it lies. The lifted part, laid back down, lies on top of every strand it
crosses. Pulling a strand out from under another does not work (FEM+IPC contact
test run17, `docs/develop/physics/rope_backend_migration_zh.md`: the crossing
survives), so a move may lift a crossing's pass only if it is the pass on top.
Lifting both passes of a crossing together (a "whole curl") does not undo it
either: the GPU probe of 2026-09-10 carried the loop through the air intact and
laid it down as a loop, twice (`runs/band_untwist_probe/20260910_stageB/`), so
the model never offers it.

Model (the same one `swap_crossing_sign_sequence.py` uses for two ropes; nothing
is imported from there):

- the rope is a top-down polyline plus, per vertex, its true arclength ``s``
  from end 0. A lifted part laid as a straight chord is still the rope's full
  length -- the slack is simply not drawn -- and every lift is computed from
  true arclength;
- each segment carries a layer: 0 as spawned, k once laid by move k. At a
  crossing the higher layer is on top; between two spawn segments the higher
  centreline z is (the generator's bumps, or the measured rope);
- a move from end ``e`` lifts the rope from the plug to ``s_lift`` = the deepest
  pass it lifts plus ``lift_clearance``, and replaces it with the chord
  lift point -> landing. Hand height = scene top + lifted arclength, exactly the
  formula `band_untwist_planner.plan_untwist_move` uses today;
- the landing is searched on circles about the deepest lifted crossing: first
  the one through the grasped plug (today's figure-8 rule: the laid part as
  extended as before the move), then wider ones; on each, angles are swept from
  the plug's own bearing in both directions, smallest rotation first. A landing
  is accepted when the recount shows the lifted crossings gone and none added,
  the plug swings at least ``min_rotation_deg`` about the crossing, the landing
  is ``place_clearance`` from all rope left on the table, the laid chord keeps
  ``min_lay_down`` from that rope and ``min_lay_down_plug`` from the other plug,
  the slack ratio (chord / lifted arclength) is within [``slack_min``,
  ``slack_max``], and -- in an episode of two moves -- the plugs end
  ``min_plug_separation`` apart (the gripper span) and every move lays its
  rope at ``slack_min_multi`` or straighter, while a move that finishes the
  episode lays its rope no tauter than ``slack_max_single``;
- the swing and clearance limits come from the 2026-09-10 GPU probes: every
  landing with a big swing and 25-35 mm of room worked (the "6", the first move
  of the twist and of O|-|O); a landing 8 deg round from the plug's old place
  let the rope fall back into its remembered shape, and one 10 mm from the rope
  left by the previous move pressed a new crossing. The straight chord is a
  poor picture of a laid rope that bulges; room is what makes it harmless.
  Room is not enough when a second move follows: laid at 0.585 the first
  move's rope bowed 70 mm along its spawn curvature over the second move's
  landings (2026-09-11). Laid at 0.9 or straighter the rope drags instead of
  bowing, still off the chord, but the re-planned second move then lands in
  open table and the episode comes undone;
- a move that leaves a crossing for the next move is also checked with its
  chord bowed either way by the bend a laid rope makes at that slack
  (``bend_extra``): the bowed lines cross nothing, keep the lay-down room, and
  the room they leave the crossings that stay is what ranks the landing.

Pure numpy; no Genesis, no topogym imports, so the offline gate and the task's
``checks()`` can call it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

import numpy as np


@dataclass(frozen=True)
class ModelParams:
    """Metres. Defaults are the task yaml's values (``pinch.*``, ``rope.*``)."""

    rope_radius: float = 0.004
    lift_clearance: float = 0.040
    place_clearance: float = 0.035
    min_plug_separation: float = 0.070
    merge_radius: float = 0.012
    # The lift point must sit at least this far (along the rope and in xy) from
    # every crossing pass that stays on the table: lifting right at a crossing
    # would drag that crossing with it.
    lift_point_hold: float = 0.020
    # Rope within this arclength of the lift point is not counted as an
    # obstacle to the laid chord: the chord starts there. Shorter than
    # lift_clearance so the pivot crossing's under pass still counts.
    lift_point_skip: float = 0.030
    sweep_step_deg: float = 0.5
    sweep_max_deg: float = 150.0
    # The plug must swing at least this far about the crossing: a landing next
    # to its old place lets the rope fall back into its spawn shape (probe
    # 2026-09-10: 8 deg, both crossings came back). Every figure-8 landing the
    # GPU has run swings 40-130 deg. Raised 40 -> 50 on 2026-09-12: the twist's
    # one big move takes the floor on every vertex of its envelope, and 50 deg
    # costs nothing there (512/512 vertices still have a plan) while putting the
    # landing further from where the rope came up.
    min_rotation_deg: float = 50.0
    # Hand height of an empty table; the model adds the lifted arclength.
    scene_top: float = 0.023
    # Highest hand the model plans (workspace.z_max). Checks may ask for headroom below it.
    max_hand_height: float = 0.40
    # The laid chord must keep this far from rope left on the table. The laid
    # rope bulges off the chord: the probes' landings with 25-35 mm of room all
    # worked, one with 10 mm (measured on the rope the previous move left)
    # pressed a new crossing. The figure-8's tightest corners had 10-12 mm and
    # passed, but their landing moves to find 25 mm under this rule (user's
    # decision 2026-09-11: one rule for every shape).
    min_lay_down: float = 0.025
    # ... and this far from the other plug's rope end: flange radius 15 mm +
    # rope radius 4 mm + margin. The plug body sits on the rope end.
    min_lay_down_plug: float = 0.025
    # Laid chord / lifted arclength: looser piles rope up, tighter drags the
    # rest. 0.518 is the loosest that has passed on the GPU (figure-8 corners
    # c008 / c136).
    slack_min: float = 0.518
    slack_max: float = 0.99
    # Every move of an episode that takes two moves lays its rope at least this
    # straight. Looser, the alternating twist failed its second move twice: the
    # first move's rope bowed 70 mm and covered the near landings, and the
    # second move's spare 85 mm curled into a new crossing. At 0.9 the same
    # layout came undone (GPU 2026-09-11, `band_untwist_zh.md` §8.5). Raised to
    # 0.93 on 2026-09-13 with the bend band below: the bow a laid rope makes
    # falls from 0.19 x its length at 0.90 to 0.16 x at 0.93. One-move episodes
    # keep ``slack_min``: nothing is left for their laid rope to block.
    slack_min_multi: float = 0.93
    # ... and the other way round for a move that FINISHES the episode: laid
    # taut, it drags the rope it has just freed back over itself. The seed
    # groups (2026-09-12) failed at 0.71 / 0.76 (twist, then solved in one
    # move) and 0.86 (six) and passed at 0.52-0.77 everywhere.
    slack_max_single: float = 0.80
    # A laid rope does not lie on its chord: laid with slack it bows sideways
    # by about length * sqrt(6 * (1 - slack)) / 4 -- fitted by the swap task on
    # 63 GPU lays (2026-09-13, `swap_crossing_sign_zh.md` 7.15; the measured bow
    # exceeded the formula by at most 1 mm). A move that leaves a crossing for
    # the next move is checked on the chord bowed either way by that much plus
    # ``bend_extra``, as a polyline of ``bend_segments`` segments: it may cross
    # nothing, keeps ``min_lay_down_bent`` from the rope on the table, and the
    # room it leaves the next move (``min_lay_down`` from the crossings that
    # stay) is measured on the bowed lines. ``min_lay_down_bent`` is the
    # rope-over-rope clearance measured 2026-09-11 (1.5 cm moves the rope
    # underneath 1-3 mm; 1.0 cm starts to carry it), not the hand's 25 mm: the
    # chord's 25 mm already stands in for a bulge the bowed lines now draw.
    bend_extra: float = 0.002
    bend_segments: int = 8
    min_lay_down_bent: float = 0.015
    # When no landing on the circle through the plug works (a short straight
    # tail swung far round lands too slack), try wider circles in this step.
    radius_step: float = 0.010
    arm_base_xy: tuple[float, float] = (-0.57, 0.0)
    max_moves: int = 2
    # Set only when planning on the measured rope in the task frame: every
    # landing inside this ((x_lo, x_hi), (y_lo, y_hi)) box and within
    # ``max_reach`` of the arm base. A second move laid straight lands up to
    # 30 cm from its plug (GPU 2026-09-11), where the spawn-time checks no
    # longer vouch for it. Left None in the shape's local frame, where the
    # centre window puts the landings in the workspace instead.
    landing_box: tuple[tuple[float, float], tuple[float, float]] | None = None
    max_reach: float | None = None
    # FLIP moves instead of lift-carry-lay moves (the twist, 2026-09-13, user's
    # design): grasp the plug, and turn the arc from the plug to a PIVOT point
    # on the rope by 180 degrees about the rope's own tangent at the pivot --
    # the hand travels a half circle in the vertical plane through the plug,
    # centred on that axis, so its distance to the axis never changes and the
    # rope is never pulled (the lay moves' hand sits sqrt(r^2 + h^2) from the
    # lift point and dragged the rope behind it 5-8 cm, §8.14). The arc lands
    # as its mirror image across the axis. A flip whose arc holds a crossing's
    # over pass undoes that crossing (its point rises ``flip_min_offset`` or
    # more off the axis on the way over); a flip whose arc holds no crossing
    # only moves a plug out of the next flip's way ("make room").
    flip_moves: bool = False
    flip_step: float = 0.010  # pivot candidates along the rope, this far apart
    flip_min_arc: float = 0.060  # shortest arc a flip turns (a make-room flip)
    flip_max_arc: float = 0.450
    flip_window: float = 0.120  # a crossing-undoing flip's pivot lies within this past (deepest crossing + lift_clearance)
    flip_min_offset: float = 0.015  # every undone crossing at least this far from the axis
    # A flip is offered only when its radius is at least this fraction of the
    # ARC it turns. The rope is not rigid: it hangs from the plug, and a half
    # circle too small for the arc leaves its far part on the table. GPU
    # 2026-09-13, seven flips: radius / arc 0.60, 0.64, 0.70 (first flips,
    # 130-160 mm arcs) and 0.60 (c038's second, 290 mm arc, 173 mm radius)
    # undid their crossing; 0.47 (c046, 136 mm on 290), 0.32 and 0.12 (c034,
    # 104 and 42 mm on 330-340) did not. A crossing whose flip would need a
    # wider circle than fits is undone by a finishing LAY instead (`plans`).
    flip_radius_ratio: float = 0.60
    # ... and no wider than this (hand height, and the landing's distance from
    # the pivot). GPU 2026-09-13: c038's second flip, radius 173 mm for a
    # crossing 250 mm down the rope, undid it (the arc lands 47 mm mean off
    # its mirror image, but the crossing comes off); the lay that finishes
    # instead dragged the loop 15 cm (c034). A wide flip's landing can fall
    # outside the workspace: the runtime planner's landing box then drops it,
    # and `BandUntwistLayout.centre_window` tries smaller caps before giving up.
    flip_max_radius: float = 0.30
    max_moves_flip: int = 3


# ----------------------------------------------------------------- the rope


@dataclass(frozen=True)
class Rope:
    """Top-down rope: vertices ``xy`` (N, 2), centreline ``z`` (N,), true
    arclength ``s`` (N,) from end 0, and ``layer`` (N - 1,) per segment."""

    xy: np.ndarray
    z: np.ndarray
    s: np.ndarray
    layer: np.ndarray

    @classmethod
    def from_points(cls, points: np.ndarray) -> Rope:
        """A spawned or measured rope: arclength is the polyline's own."""

        points = np.asarray(points, dtype=float)
        xy = points[:, :2].copy()
        z = points[:, 2].copy() if points.shape[1] > 2 else np.zeros(len(points))
        steps = np.linalg.norm(np.diff(xy, axis=0), axis=1)
        s = np.concatenate([[0.0], np.cumsum(steps)])
        return cls(xy, z, s, np.zeros(len(points) - 1, dtype=int))

    @property
    def length(self) -> float:
        return float(self.s[-1])

    def end_xy(self, end: int) -> np.ndarray:
        return self.xy[0] if int(end) == 0 else self.xy[-1]

    def at(self, s: float) -> tuple[np.ndarray, float]:
        """xy and z at true arclength ``s`` (linear within a segment)."""

        x = float(np.interp(s, self.s, self.xy[:, 0]))
        y = float(np.interp(s, self.s, self.xy[:, 1]))
        return np.array([x, y]), float(np.interp(s, self.s, self.z))


@dataclass(frozen=True)
class Crossing:
    """One top-down crossing of the rope with itself."""

    xy: tuple[float, float]
    s_over: float
    s_under: float

    @property
    def s_first(self) -> float:
        return min(self.s_over, self.s_under)

    @property
    def s_second(self) -> float:
        return max(self.s_over, self.s_under)

    @property
    def over_first(self) -> bool:
        """The pass met first walking from end 0 is the one on top."""

        return self.s_over < self.s_under


def _seg_params(p0, p1, q0, q1):
    """Broadcast intersection parameters of segments p (…,2) and q (…,2)."""

    r = p1 - p0
    sq = q1 - q0
    denom = r[..., 0] * sq[..., 1] - r[..., 1] * sq[..., 0]
    diff = q0 - p0
    with np.errstate(divide="ignore", invalid="ignore"):
        t = (diff[..., 0] * sq[..., 1] - diff[..., 1] * sq[..., 0]) / denom
        u = (diff[..., 0] * r[..., 1] - diff[..., 1] * r[..., 0]) / denom
    ok = np.abs(denom) > 1e-14
    return t, u, ok


def crossings(rope: Rope, *, merge_radius: float) -> tuple[Crossing, ...]:
    """Every top-down self-crossing, hits within ``merge_radius`` merged.

    Segments sharing a vertex are skipped; hits at a segment end count (a
    generated crossing sits exactly on a vertex of both passes). Over/under:
    higher layer, then higher z. Merged hits keep the one with the widest gap.
    """

    a0, a1 = rope.xy[:-1], rope.xy[1:]
    n = len(a0)
    i, j = np.triu_indices(n, k=2)
    t, u, ok = _seg_params(a0[i], a1[i], a0[j], a1[j])
    eps = 1e-9
    hit = ok & (t >= -eps) & (t <= 1 + eps) & (u >= -eps) & (u <= 1 + eps)
    i, j, t, u = i[hit], j[hit], np.clip(t[hit], 0, 1), np.clip(u[hit], 0, 1)
    raw = []
    for ii, jj, ti, uj in zip(i, j, t, u):
        xy = a0[ii] + ti * (a1[ii] - a0[ii])
        si = rope.s[ii] + ti * (rope.s[ii + 1] - rope.s[ii])
        sj = rope.s[jj] + uj * (rope.s[jj + 1] - rope.s[jj])
        zi = rope.z[ii] + ti * (rope.z[ii + 1] - rope.z[ii])
        zj = rope.z[jj] + uj * (rope.z[jj + 1] - rope.z[jj])
        key_i, key_j = (int(rope.layer[ii]), zi), (int(rope.layer[jj]), zj)
        gap = abs(zi - zj) + 1.0 * abs(int(rope.layer[ii]) - int(rope.layer[jj]))
        if key_i >= key_j:
            raw.append((xy, float(si), float(sj), gap))
        else:
            raw.append((xy, float(sj), float(si), gap))
    merged: list[tuple] = []
    for item in raw:
        for index, kept in enumerate(merged):
            if float(np.linalg.norm(item[0] - kept[0])) <= merge_radius:
                if item[3] > kept[3]:
                    merged[index] = item
                break
        else:
            merged.append(item)
    out = [Crossing((float(m[0][0]), float(m[0][1])), m[1], m[2]) for m in merged]
    out.sort(key=lambda c: c.s_first)
    return tuple(out)


def crossing_sequence(found) -> tuple[tuple[int, str], ...]:
    """Walk the rope from end 0 and write down every crossing pass: which
    crossing it is (numbered by the order its first pass is met) and whether
    the rope is on top ("o") or underneath ("u") there.

    The 8 with end 0's strand on top reads ((0, "o"), (0, "u")). Two ropes
    that settle a few millimetres apart still read the same, so this is what
    the spawn self-check and the per-move plan check compare.
    """

    return sequence_of_passes([(c.s_over, c.s_under) for c in found])


def sequence_of_passes(pairs) -> tuple[tuple[int, str], ...]:
    """`crossing_sequence` from ``(over, under)`` positions along the rope, in
    any unit that grows from end 0 (the verifier passes normalized arclength)."""

    passes = []
    for key, (s_over, s_under) in enumerate(pairs):
        passes.append((float(s_over), key, "o"))
        passes.append((float(s_under), key, "u"))
    passes.sort()
    rank: dict[int, int] = {}
    out = []
    for _s, key, kind in passes:
        rank.setdefault(key, len(rank))
        out.append((rank[key], kind))
    return tuple(out)


# ------------------------------------------------------------ distances


def _point_segment_distance(points: np.ndarray, q0: np.ndarray, q1: np.ndarray) -> np.ndarray:
    """(K, M): distance from each point to each segment."""

    d = q1 - q0
    length_sq = np.maximum(np.einsum("ij,ij->i", d, d), 1e-18)
    rel = points[:, None, :] - q0[None, :, :]
    t = np.clip(np.einsum("kmj,mj->km", rel, d) / length_sq[None, :], 0.0, 1.0)
    nearest = q0[None, :, :] + t[..., None] * d[None, :, :]
    return np.linalg.norm(points[:, None, :] - nearest, axis=2)


def _segment_segment_distance(p0, p1, q0, q1) -> np.ndarray:
    """(K, M): distance between segments p (K, 2) and q (M, 2); 0 where they cross."""

    t, u, ok = _seg_params(p0[:, None, :], p1[:, None, :], q0[None, :, :], q1[None, :, :])
    crossing = ok & (t >= 0) & (t <= 1) & (u >= 0) & (u <= 1)
    best = np.minimum(_point_segment_distance(p0, q0, q1), _point_segment_distance(p1, q0, q1))
    # Endpoints of q against each p segment: transpose of the same helper.
    best = np.minimum(best, _point_segment_distance(q0, p0, p1).T)
    best = np.minimum(best, _point_segment_distance(q1, p0, p1).T)
    return np.where(crossing, 0.0, best)


def _bent_tails(start: np.ndarray, ends: np.ndarray, bow: np.ndarray, segments: int) -> np.ndarray:
    """Chords ``start -> ends`` bowed sideways by ``bow`` at the middle (a
    parabola; the sign of ``bow`` picks the side), as (n, segments + 1, 2)
    polylines. Copied from `swap_crossing_sign_sequence._bent_tails`."""

    u = np.linspace(0.0, 1.0, segments + 1)[None, :, None]
    chord = ends - start[None, :]
    normal = np.stack([-chord[:, 1], chord[:, 0]], axis=1) / np.maximum(np.linalg.norm(chord, axis=1), 1e-12)[:, None]
    return start[None, None, :] + u * chord[:, None, :] + 4.0 * u * (1.0 - u) * (bow[:, None] * normal)[:, None, :]


# -------------------------------------------------------------------- moves


@dataclass(frozen=True)
class Lift:
    """Which plug, lifted up to where, and what that does to the crossings."""

    end: int
    s_lift: float
    lifted: tuple[int, ...]  # indices into the state's crossings whose over pass is lifted
    pivot: int  # the deepest lifted crossing: the landing circle's centre

    def arc(self, rope: Rope) -> float:
        return float(self.s_lift - rope.s[0]) if self.end == 0 else float(rope.s[-1] - self.s_lift)


@dataclass(frozen=True)
class Move:
    lift: Lift
    grasp_xy: tuple[float, float]
    lift_xy: tuple[float, float]  # the lift point (lay) or the pivot (flip)
    place_xy: tuple[float, float]
    hand_height: float
    sweep_deg: float
    margins: dict = field(default_factory=dict, compare=False)
    kind: str = "lay"  # "lay": lift-carry-lay; "flip": half turn about ``axis`` through ``lift_xy``
    axis: tuple[float, float] = (0.0, 0.0)  # flip: unit tangent of the rope at the pivot (task xy)

    @property
    def end(self) -> int:
        return self.lift.end


def lifts(rope: Rope, found: tuple[Crossing, ...], params: ModelParams) -> list[Lift]:
    """Every lift that drags nothing out from under another strand.

    Candidates: each plug x each crossing pass as the deepest lifted pass,
    lifted ``lift_clearance`` beyond it. A crossing with exactly one pass in
    the lifted interval must have that pass on top (the whole interval counts:
    the clearance can reach another pass). A crossing with both passes in it
    is a whole curl, which the GPU showed does not come undone (module
    docstring), so such a lift is not offered. The lift point must also keep
    ``lift_point_hold`` from every pass that stays down.
    """

    best: dict[tuple, Lift] = {}
    for end in (0, 1):
        for c in found:
            for s_pass in (c.s_over, c.s_under):
                if end == 0:
                    s_lift = s_pass + params.lift_clearance
                    inside = lambda s, s_lift=s_lift: s <= s_lift
                else:
                    s_lift = s_pass - params.lift_clearance
                    inside = lambda s, s_lift=s_lift: s >= s_lift
                if not rope.s[0] < s_lift < rope.s[-1]:
                    continue
                lifted, ok = [], True
                for index, other in enumerate(found):
                    over_in, under_in = inside(other.s_over), inside(other.s_under)
                    if under_in:
                        ok = False  # drags the under pass out from below, or lifts a whole curl
                        break
                    if over_in:
                        lifted.append(index)
                if not ok or not lifted:
                    continue
                arc = s_lift - rope.s[0] if end == 0 else rope.s[-1] - s_lift
                if params.scene_top + arc > params.max_hand_height + 1e-12:
                    continue
                lift_xy, _ = rope.at(s_lift)
                staying = [p for k, o in enumerate(found) if k not in lifted for p in (o.s_over, o.s_under)]
                staying_xy = [np.asarray(o.xy) for k, o in enumerate(found) if k not in lifted]
                if any(abs(p - s_lift) < params.lift_point_hold for p in staying):
                    continue
                if any(float(np.linalg.norm(lift_xy - q)) < params.lift_point_hold for q in staying_xy):
                    continue
                # Deepest lifted crossing = the one whose over pass is furthest from the plug.
                pivot = max(lifted, key=lambda k: found[k].s_over if end == 0 else -found[k].s_over)
                candidate = Lift(end, float(s_lift), tuple(lifted), int(pivot))
                # Same plug, same crossings lifted: keep the shortest lift.
                key = (end, tuple(lifted))
                if key not in best or candidate.arc(rope) < best[key].arc(rope):
                    best[key] = candidate
    return list(best.values())


#: A vertex this close (arclength) to the lift point is the lift point: keeping
#: both leaves a zero-length segment that the laid chord "touches", and the
#: recount reads a phantom crossing (seen on a translated figure-8, 2026-09-11).
_SAME_POINT = 1e-6


def _remaining(rope: Rope, lift: Lift) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Segments of the rope left on the table: (q0, q1, s at q0, s at q1)."""

    xy_l, _ = rope.at(lift.s_lift)
    if lift.end == 0:
        keep = rope.s > lift.s_lift + _SAME_POINT
        xy = np.vstack([xy_l, rope.xy[keep]])
        s = np.concatenate([[lift.s_lift], rope.s[keep]])
    else:
        keep = rope.s < lift.s_lift - _SAME_POINT
        xy = np.vstack([rope.xy[keep], xy_l])
        s = np.concatenate([rope.s[keep], [lift.s_lift]])
    return xy[:-1], xy[1:], s[:-1], s[1:]


def apply(rope: Rope, lift: Lift, place_xy, layer: int) -> Rope:
    """The rope after laying the lifted part as the chord lift point -> landing."""

    xy_l, z_l = rope.at(lift.s_lift)
    place = np.asarray(place_xy, dtype=float)
    base_z = float(rope.z.min())
    # Segment k runs from vertex k to k + 1. The segment the lift point cuts
    # keeps its layer on the part left on the table.
    if lift.end == 0:
        keep = rope.s > lift.s_lift + _SAME_POINT
        first_kept = int(np.argmax(keep))
        xy = np.vstack([place, xy_l, rope.xy[keep]])
        z = np.concatenate([[base_z, z_l], rope.z[keep]])
        s = np.concatenate([[rope.s[0], lift.s_lift], rope.s[keep]])
        layers = np.concatenate([[layer, rope.layer[first_kept - 1]], rope.layer[first_kept:]])
    else:
        keep = rope.s < lift.s_lift - _SAME_POINT
        last_kept = int(len(keep) - 1 - np.argmax(keep[::-1]))
        xy = np.vstack([rope.xy[keep], xy_l, place])
        z = np.concatenate([rope.z[keep], [z_l, base_z]])
        s = np.concatenate([rope.s[keep], [lift.s_lift, rope.s[-1]]])
        layers = np.concatenate([rope.layer[:last_kept], [rope.layer[last_kept], layer]])
    assert len(layers) == len(xy) - 1
    return Rope(xy, z, s, layers.astype(int))


def land(rope: Rope, found, lift: Lift, params: ModelParams, *, separate_plugs: bool, layer: int, clean: bool = True):
    """First landing along the sweep that the recount accepts; ``(Move, Rope)`` or None.

    ``clean=False`` drops the conditions that ask the move to leave no new
    crossing (the chord crossing nothing, the lay-down clearances, the recount):
    the `wrong_end` contrast lays a strand across the other on purpose, with
    the same circle, swing, slack and landing clearance as the oracle.
    """

    grasp = rope.end_xy(lift.end)
    other = rope.end_xy(1 - lift.end)
    lift_xy, _ = rope.at(lift.s_lift)
    arc = lift.arc(rope)
    if arc <= 0.0:
        return None
    centre = np.asarray(found[lift.pivot].xy, dtype=float)
    first = float(np.linalg.norm(grasp - centre))
    # The circle through the plug first (today's figure-8 rule), then wider
    # ones: a wider circle only ever makes the laid part tauter.
    widest = arc + float(np.linalg.norm(lift_xy - centre))
    radii = list(np.arange(first, widest + 1e-9, params.radius_step)) or [first]
    bearing = math.atan2(grasp[1] - centre[1], grasp[0] - centre[0])
    steps = int(round(params.sweep_max_deg / params.sweep_step_deg))
    k = np.arange(steps + 1)
    angles = np.concatenate([bearing + np.radians(k * params.sweep_step_deg), bearing - np.radians(k[1:] * params.sweep_step_deg)])
    rotation = np.concatenate([k, k[1:]]) * params.sweep_step_deg
    unit = np.column_stack([np.cos(angles), np.sin(angles)])

    # Crossings this move leaves on the table. When there are any, the rope this
    # move lays down is where the NEXT move has to work, and a laid tail settles
    # 4-9 cm from the chord drawn here (GPU 2026-09-11), so the landing is chosen
    # to leave that next move as much room as the rules allow instead of taking
    # the smallest swing: every circle is searched, not only the first that
    # works, and the candidate whose chord stays farthest from those crossings
    # wins. Measured on O|-|O: 58-115 mm of room instead of 44-95.
    staying_xy = [np.asarray(c.xy, dtype=float) for k, c in enumerate(found) if k not in lift.lifted]
    leaves_work = clean and bool(staying_xy)
    q0, q1, qs0, qs1 = _remaining(rope, lift)
    # Rope near the lift point is where the chord starts, not an obstacle.
    far = np.minimum(np.abs(qs0 - lift.s_lift), np.abs(qs1 - lift.s_lift)) > params.lift_point_skip
    q0f, q1f = q0[far], q1[far]
    chosen = None
    for radius in radii:
        if radius < 1e-6:
            continue
        places = centre[None, :] + radius * unit
        chord = np.linalg.norm(places - lift_xy[None, :], axis=1)
        slack = chord / arc
        good = (slack >= params.slack_min - 1e-9) & (slack <= params.slack_max + 1e-9)
        good &= rotation >= params.min_rotation_deg - 1e-9
        if params.landing_box is not None:
            (x_lo, x_hi), (y_lo, y_hi) = params.landing_box
            good &= (places[:, 0] >= x_lo) & (places[:, 0] <= x_hi) & (places[:, 1] >= y_lo) & (places[:, 1] <= y_hi)
        if params.max_reach is not None:
            good &= np.linalg.norm(places - np.asarray(params.arm_base_xy)[None, :], axis=1) <= params.max_reach + 1e-9
        if not good.any():
            continue
        starts = np.repeat(lift_xy[None, :], len(places), axis=0)
        if len(q0f):
            t, u, ok = _seg_params(starts[:, None, :], places[:, None, :], q0f[None, :, :], q1f[None, :, :])
            crosses = (ok & (t > 1e-9) & (t <= 1) & (u >= 0) & (u <= 1)).any(axis=1)
            lay_clear = _segment_segment_distance(starts, places, q0f, q1f).min(axis=1)
        else:  # nothing left on the table beyond the lift point's own stretch
            crosses = np.zeros(len(places), dtype=bool)
            lay_clear = np.full(len(places), np.inf)
        place_clear = _point_segment_distance(places, q0, q1).min(axis=1)
        lay_plug = _point_segment_distance(other[None, :], starts, places)[0]
        plug_sep = np.linalg.norm(places - other[None, :], axis=1)
        good &= place_clear >= params.place_clearance - 1e-9
        if clean:
            good &= ~crosses
            good &= (lay_clear >= params.min_lay_down - 1e-9) & (lay_plug >= params.min_lay_down_plug - 1e-9)
        if separate_plugs:
            good &= plug_sep >= params.min_plug_separation - 1e-9
        if not good.any():
            continue
        # The laid rope bows off its chord (ModelParams.bend_extra). A move
        # that leaves a crossing must still cross nothing and keep its
        # lay-down room when bowed either way, and the room it leaves the next
        # move is the bowed lines' room. Checked on the candidates the chord
        # already admits, to keep the search at today's cost.
        bow = arc * np.sqrt(6.0 * np.clip(1.0 - slack, 0.0, None)) / 4.0 + params.bend_extra
        room = np.full(len(places), np.inf)
        bent_clear = np.full(len(places), np.inf)
        if leaves_work:
            room = np.min([_point_segment_distance(q[None, :], starts, places)[0] for q in staying_xy], axis=0)
            idx = np.flatnonzero(good)
            m = params.bend_segments
            lines = np.concatenate([_bent_tails(lift_xy, places[idx], sign * bow[idx], m) for sign in (-1.0, 1.0)])
            a, b = lines[:, :-1].reshape(-1, 2), lines[:, 1:].reshape(-1, 2)
            if len(q0f):
                t, u, ok = _seg_params(a[:, None, :], b[:, None, :], q0f[None, :, :], q1f[None, :, :])
                hits = (ok & (t > 1e-9) & (t <= 1) & (u >= 0) & (u <= 1)).any(axis=1).reshape(2, len(idx), m).any(axis=(0, 2))
                clear = _segment_segment_distance(a, b, q0f, q1f).min(axis=1).reshape(2, len(idx), m).min(axis=(0, 2))
            else:
                hits = np.zeros(len(idx), dtype=bool)
                clear = np.full(len(idx), np.inf)
            plug_gap = _point_segment_distance(other[None, :], a, b)[0].reshape(2, len(idx), m).min(axis=(0, 2))
            bent_room = np.min([_point_segment_distance(q[None, :], a, b)[0].reshape(2, len(idx), m).min(axis=(0, 2))
                                for q in staying_xy], axis=0)
            good[idx] &= ~hits & (clear >= params.min_lay_down_bent - 1e-9) & (plug_gap >= params.min_lay_down_plug - 1e-9)
            bent_clear[idx] = clear
            lay_plug[idx] = np.minimum(lay_plug[idx], plug_gap)
            room[idx] = np.minimum(room[idx], bent_room)
            if not good.any():
                continue
            order = np.lexsort((rotation, -np.round(room, 4)))
        else:
            order = np.lexsort((-lay_clear, rotation))  # smallest rotation first, widest lay-down on ties
        pick = int(next(i for i in order if good[i]))
        candidate = (radius, places, slack, lay_clear, place_clear, lay_plug, plug_sep, bow, room, bent_clear, pick)
        if not leaves_work:
            chosen = candidate
            break
        # Keep searching wider circles: a landing farther from the crossings that
        # stay is worth more than a smaller swing here.
        score = float(room[pick])
        if chosen is None or score > chosen[0] + 1e-6:
            chosen = (score,) + candidate
    if chosen is not None and leaves_work:
        chosen = chosen[1:]
    if chosen is None:
        return None
    radius, places, slack, lay_clear, place_clear, lay_plug, plug_sep, bow, room, bent_clear, pick = chosen
    place = places[pick]
    after = apply(rope, lift, place, layer)
    remaining_crossings = [c for k2, c in enumerate(found) if k2 not in lift.lifted]
    recount = crossings(after, merge_radius=params.merge_radius)
    if clean and len(recount) != len(remaining_crossings):
        return None  # the chord misses every segment but the merged count disagrees: refuse
    base = np.asarray(params.arm_base_xy, dtype=float)
    margins = {
        "hand_height": params.scene_top + arc,
        "slack": float(slack[pick]),
        "place_clearance": float(place_clear[pick]),
        "lay_down_clearance": float(lay_clear[pick]),
        "lay_down_plug": float(lay_plug[pick]),
        "plug_separation": float(plug_sep[pick]),
        "reach": float(max(np.linalg.norm(grasp - base), np.linalg.norm(place - base))),
        "rotation_deg": float(rotation[pick]),
        "radius_widened": float(radius - radii[0]),
        # How far the laid rope may bow off its chord, and (a move that leaves
        # a crossing) the room the bowed lines keep from the crossings that stay.
        "bend": float(bow[pick]),
        "room": float(room[pick]),
        "lay_down_bent": float(bent_clear[pick]),
    }
    move = Move(
        lift=lift,
        grasp_xy=(float(grasp[0]), float(grasp[1])),
        lift_xy=(float(lift_xy[0]), float(lift_xy[1])),
        place_xy=(float(place[0]), float(place[1])),
        hand_height=float(params.scene_top + arc),
        sweep_deg=float(rotation[pick]),
        margins=margins,
    )
    return move, after


def wrong_end_move(rope: Rope, found, pivot: int, params: ModelParams):
    """The `wrong_end` contrast at crossing ``pivot``: grasp the plug on the
    UNDER pass's side, lift to that pass plus ``lift_clearance``, land by the
    same rule without asking for a clean result. On the figure-8 that is
    today's contrast (grasp the under end). ``(Move, Rope)`` or None.
    """

    c = found[pivot]
    end = 0 if c.s_under < c.s_over else 1
    s_lift = c.s_under + params.lift_clearance if end == 0 else c.s_under - params.lift_clearance
    if not rope.s[0] < s_lift < rope.s[-1]:
        return None
    lift = Lift(end, float(s_lift), (int(pivot),), int(pivot))
    if params.scene_top + lift.arc(rope) > params.max_hand_height + 1e-12:
        return None
    return land(rope, found, lift, params, separate_plugs=False, layer=1, clean=False)


# -------------------------------------------------------------------- flips


def flip_axis(rope: Rope, s_pivot: float, half: float = 0.010) -> tuple[np.ndarray, np.ndarray]:
    """The pivot's xy and the rope's unit tangent there (chord over +-``half`` of arclength)."""

    a, _ = rope.at(max(float(s_pivot) - half, float(rope.s[0])))
    b, _ = rope.at(min(float(s_pivot) + half, float(rope.s[-1])))
    t = b - a
    t = t / max(float(np.linalg.norm(t)), 1e-12)
    pivot, _ = rope.at(float(s_pivot))
    return pivot, t


def reflect_xy(points: np.ndarray, pivot: np.ndarray, axis: np.ndarray) -> np.ndarray:
    """Mirror ``points`` (N, 2) across the line through ``pivot`` along ``axis``:
    where a 180-degree turn about that line puts them."""

    rel = np.asarray(points, dtype=float) - pivot[None, :]
    along = rel @ axis
    perp = rel - along[:, None] * axis[None, :]
    return pivot[None, :] + along[:, None] * axis[None, :] - perp


def _arc_and_rest(rope: Rope, lift: Lift):
    """Vertices of the flipped arc (plug end first) and the rest, split at the pivot."""

    if lift.end == 0:
        arc = rope.s < lift.s_lift - _SAME_POINT
        return rope.xy[arc], rope.z[arc], rope.s[arc], np.flatnonzero(rope.s > lift.s_lift + _SAME_POINT)
    arc = rope.s > lift.s_lift + _SAME_POINT
    return rope.xy[arc][::-1], rope.z[arc][::-1], rope.s[arc][::-1], np.flatnonzero(rope.s < lift.s_lift - _SAME_POINT)


def apply_flip(rope: Rope, lift: Lift, axis: np.ndarray, layer: int) -> Rope:
    """The rope after turning the arc plug -> pivot over: its mirror image across
    the axis, laid on top (layer ``layer``), the rest untouched."""

    pivot_xy, z_p = rope.at(lift.s_lift)
    base_z = float(rope.z.min())
    arc_xy, _arc_z, arc_s, keep = _arc_and_rest(rope, lift)
    mirrored = reflect_xy(arc_xy, pivot_xy, axis)
    n_arc = len(mirrored)
    if lift.end == 0:
        first_kept = int(keep[0])
        xy = np.vstack([mirrored, pivot_xy[None, :], rope.xy[keep]])
        z = np.concatenate([np.full(n_arc, base_z), [z_p], rope.z[keep]])
        s = np.concatenate([arc_s, [lift.s_lift], rope.s[keep]])
        layers = np.concatenate([np.full(n_arc, layer, dtype=int), [rope.layer[first_kept - 1]], rope.layer[first_kept:]])
    else:
        last_kept = int(keep[-1])
        xy = np.vstack([rope.xy[keep], pivot_xy[None, :], mirrored[::-1]])
        z = np.concatenate([rope.z[keep], [z_p], np.full(n_arc, base_z)])
        s = np.concatenate([rope.s[keep], [lift.s_lift], arc_s[::-1]])
        layers = np.concatenate([rope.layer[:last_kept], [rope.layer[last_kept]], np.full(n_arc, layer, dtype=int)])
    return Rope(xy, z, s, layers)


def flips(rope: Rope, found: tuple[Crossing, ...], params: ModelParams) -> list[Lift]:
    """Every flip the over-pass rule allows, as `Lift`s whose ``s_lift`` is the pivot.

    Pivots every ``flip_step`` of arclength from each plug. A crossing with its
    under pass inside the arc would be dragged (refused); one with its over pass
    inside is undone (``lifted``); both inside is a whole curl (refused). A
    crossing-undoing flip's pivot lies ``lift_clearance`` to ``lift_clearance +
    flip_window`` past the deepest undone crossing; a flip undoing nothing
    (make-room) may pivot anywhere from ``flip_min_arc`` up to the first pass.
    The pivot keeps ``lift_point_hold`` from every pass that stays down.
    """

    out: list[Lift] = []
    length = float(rope.s[-1] - rope.s[0])
    grid = np.arange(params.flip_min_arc, min(params.flip_max_arc, length - params.flip_min_arc) + 1e-9, params.flip_step)
    for end in (0, 1):
        for arc in grid:
            s_pivot = float(rope.s[0] + arc) if end == 0 else float(rope.s[-1] - arc)
            inside = (lambda s, s_p=s_pivot: s <= s_p) if end == 0 else (lambda s, s_p=s_pivot: s >= s_p)
            lifted, ok = [], True
            for index, c in enumerate(found):
                over_in, under_in = inside(c.s_over), inside(c.s_under)
                if under_in:
                    ok = False
                    break
                if over_in:
                    lifted.append(index)
            if not ok:
                continue
            if lifted:
                deepest = max(found[k].s_over for k in lifted) if end == 0 else min(found[k].s_over for k in lifted)
                past = abs(s_pivot - deepest)
                if past < params.lift_clearance - 1e-9 or past > params.lift_clearance + params.flip_window + 1e-9:
                    continue
            staying = [p for k, o in enumerate(found) if k not in lifted for p in (o.s_over, o.s_under)]
            staying_xy = [np.asarray(o.xy) for k, o in enumerate(found) if k not in lifted]
            if any(abs(p - s_pivot) < params.lift_point_hold for p in staying):
                continue
            pivot_xy, _ = rope.at(s_pivot)
            if any(float(np.linalg.norm(pivot_xy - q)) < params.lift_point_hold for q in staying_xy):
                continue
            pivot = (max(lifted, key=lambda k: found[k].s_over if end == 0 else -found[k].s_over)) if lifted else -1
            out.append(Lift(end, s_pivot, tuple(lifted), int(pivot)))
    return out


def land_flip(rope: Rope, found, lift: Lift, params: ModelParams, *, separate_plugs: bool, layer: int):
    """``(Move, Rope)`` for one flip, or None when its mirror image breaks a rule."""

    grasp = rope.end_xy(lift.end)
    other = rope.end_xy(1 - lift.end)
    pivot_xy, axis = flip_axis(rope, lift.s_lift)
    arc_xy, _z, arc_s, _keep = _arc_and_rest(rope, lift)
    if len(arc_xy) < 2:
        return None
    mirrored = reflect_xy(arc_xy, pivot_xy, axis)
    place = mirrored[0]
    rel = grasp - pivot_xy
    radius = float(np.linalg.norm(rel - (rel @ axis) * axis))  # the hand's half circle, and its top height
    if radius < 1e-6 or radius > params.flip_max_radius + 1e-12 or radius + params.rope_radius > params.max_hand_height + 1e-12:
        return None
    # every undone crossing must come up off the axis on the way over
    offsets = []
    for k in lift.lifted:
        q = np.asarray(found[k].xy, dtype=float) - pivot_xy
        offsets.append(float(np.linalg.norm(q - (q @ axis) * axis)))
    if offsets and min(offsets) < params.flip_min_offset - 1e-9:
        return None
    if params.landing_box is not None:
        (x_lo, x_hi), (y_lo, y_hi) = params.landing_box
        if not (x_lo <= place[0] <= x_hi and y_lo <= place[1] <= y_hi):
            return None
    base = np.asarray(params.arm_base_xy, dtype=float)
    reach = float(max(np.linalg.norm(grasp - base), np.linalg.norm(place - base)))
    if params.max_reach is not None and reach > params.max_reach + 1e-9:
        return None
    # the rope that stays, away from the pivot, against the mirrored arc away from the pivot
    q0, q1, qs0, qs1 = _remaining(rope, lift)
    far = np.minimum(np.abs(qs0 - lift.s_lift), np.abs(qs1 - lift.s_lift)) > params.lift_point_skip
    q0f, q1f = q0[far], q1[far]
    a, b = mirrored[:-1], mirrored[1:]
    arc_far = np.abs(arc_s[:-1] - lift.s_lift) > params.lift_point_skip
    place_clear = float(_point_segment_distance(place[None, :], q0, q1).min()) if len(q0) else math.inf
    if place_clear < params.place_clearance - 1e-9:
        return None
    if len(q0f) and arc_far.any():
        t, u, ok = _seg_params(a[arc_far][:, None, :], b[arc_far][:, None, :], q0f[None, :, :], q1f[None, :, :])
        if (ok & (t >= 0) & (t <= 1) & (u >= 0) & (u <= 1)).any():
            return None
        lay_clear = float(_segment_segment_distance(a[arc_far], b[arc_far], q0f, q1f).min())
    else:
        lay_clear = math.inf
    if lay_clear < params.min_lay_down - 1e-9:
        return None
    lay_plug = float(_point_segment_distance(other[None, :], a, b).min())
    if lay_plug < params.min_lay_down_plug - 1e-9:
        return None
    plug_sep = float(np.linalg.norm(place - other))
    if separate_plugs and plug_sep < params.min_plug_separation - 1e-9:
        return None
    after = apply_flip(rope, lift, axis, layer)
    remaining = [c for k, c in enumerate(found) if k not in lift.lifted]
    if len(crossings(after, merge_radius=params.merge_radius)) != len(remaining):
        return None
    room = float(min((_point_segment_distance(np.asarray(c.xy, dtype=float)[None, :], a, b).min() for c in remaining), default=math.inf))
    margins = {
        "hand_height": radius + params.rope_radius,
        "place_clearance": place_clear,
        "lay_down_clearance": lay_clear,
        "lay_down_plug": lay_plug,
        "plug_separation": plug_sep,
        "reach": reach,
        "rotation_deg": 180.0,
        "radius_widened": 0.0,
        "bend": 0.0,
        "room": room,
        "lay_down_bent": math.inf,
        "flip_radius": radius,
        "flip_offset": float(min(offsets)) if offsets else math.inf,
        "arc": float(lift.arc(rope)),
    }
    move = Move(
        lift=lift,
        grasp_xy=(float(grasp[0]), float(grasp[1])),
        lift_xy=(float(pivot_xy[0]), float(pivot_xy[1])),
        place_xy=(float(place[0]), float(place[1])),
        hand_height=radius + params.rope_radius,
        sweep_deg=180.0,
        margins=margins,
        kind="flip",
        axis=(float(axis[0]), float(axis[1])),
    )
    return move, after


def best_flips(rope: Rope, found, params: ModelParams, *, separate_plugs: bool, layer: int, make_room: bool):
    """One landed flip per (plug, crossings undone).

    The rope is not rigid: the hand's half circle has to be wide enough for
    the arc to follow it over. GPU 2026-09-13 (c034): a 140 mm arc on an 85 mm
    radius landed 34 mm from its mirror image and undid its crossing; a 340 mm
    arc on a 42 mm radius strayed 120 mm and undid nothing. So among the
    pivots whose mirror image passes every rule: the smallest radius of those
    with radius >= ``flip_radius_ratio`` x arc (the lowest hand that still
    carries the arc; the landing nearest the pivot keeps the centre window
    wide), else the largest radius there is; room breaks ties."""

    best: dict[tuple, tuple[tuple, Move, Rope]] = {}
    for lift in flips(rope, found, params):
        if bool(lift.lifted) == make_room:
            continue
        landed = land_flip(rope, found, lift, params, separate_plugs=separate_plugs, layer=layer)
        if landed is None:
            continue
        move, after = landed
        radius = move.margins["flip_radius"]
        if radius < params.flip_radius_ratio * move.margins["arc"] - 1e-9:
            continue
        # the smallest radius that carries the arc: the lowest hand, the landing nearest the pivot
        score = (-round(radius, 3), min(move.margins["lay_down_clearance"], move.margins["room"]))
        key = (lift.end, lift.lifted)
        if key not in best or score > best[key][0]:
            best[key] = (score, move, after)
    return [(m, r) for _s, m, r in best.values()]


@dataclass(frozen=True)
class Plan:
    moves: tuple[Move, ...]
    ropes: tuple[Rope, ...]  # the rope after each move
    predicted: tuple[tuple[tuple[int, str], ...], ...]  # crossing sequence after each move

    @property
    def max_hand_height(self) -> float:
        return max((m.hand_height for m in self.moves), default=0.0)

    def margin(self, name: str, pick=min) -> float:
        """``pick`` over the moves that carry this margin (a flip has no slack)."""
        values = [m.margins[name] for m in self.moves if name in m.margins]
        return float(pick(values)) if values else math.nan


def plan(rope: Rope, params: ModelParams = ModelParams(), *, moves_done: int = 0) -> Plan | None:
    """Shortest sequence of moves that leaves no crossing, or None.

    Fewer moves first, then the lower highest hand, then the wider narrowest
    lay-down clearance. At most ``params.max_moves`` moves (2 covers every
    shape this task spawns). In an episode of two moves every landing keeps the
    plugs ``min_plug_separation`` apart (the second move's landing next to a
    plug the first move put down pushed it across the rope, probe 2026-09-10)
    and lays its rope at ``slack_min_multi`` or straighter. ``moves_done`` is
    how many moves the episode has already made, so the re-plan before a
    second move holds it to the same rules as the plan that foresaw it.
    """

    found = plans(rope, params, moves_done=moves_done)
    return found[0] if found else None


def plans(rope: Rope, params: ModelParams = ModelParams(), *, moves_done: int = 0) -> list[Plan]:
    """Every sequence of the fewest moves that leaves no crossing, best first
    (the order `plan` ranks by); empty if there is none.

    More than one when the shape is symmetric: O|-|O's two curls score the
    same whichever goes first, so turning the shape to its heading, or the few
    millimetres the rope settles, decides which one `plan` returns. Whatever
    must hold for the oracle's run (the landings inside the workspace, in reach)
    must hold for all of them.
    """

    found = crossings(rope, merge_radius=params.merge_radius)
    if not found:
        return [Plan((), (), ())]
    complete: list[Plan] = []
    max_moves = params.max_moves_flip if params.flip_moves else params.max_moves

    def has_lay(p: Plan) -> bool:
        return any(m.kind == "lay" for m in p.moves)

    def score(p: Plan):
        # Under flip moves, a plan of flips only (even one flip longer) ranks
        # above one that finishes with a lay: the finishing lay of a 23-34 cm
        # tail dragged the loop 15 cm and re-crossed it (GPU 2026-09-13, c034),
        # every flip that met the radius rule undid its crossing.
        return (has_lay(p) if params.flip_moves else False, len(p.moves), p.max_hand_height, -p.margin("lay_down_clearance"))

    def extend(move, after, moves, ropes, predicted, depth, make_room=False):
        after_found = crossings(after, merge_radius=params.merge_radius)
        new_moves, new_ropes = moves + (move,), ropes + (after,)
        new_pred = predicted + (crossing_sequence(after_found),)
        if not after_found:
            complete.append(Plan(new_moves, new_ropes, new_pred))
        elif depth + 1 < max_moves:
            search(after, after_found, new_moves, new_ropes, new_pred, depth + 1, make_room=make_room)

    def search(state: Rope, state_found, moves, ropes, predicted, depth, make_room=False):
        if params.flip_moves:
            # Flips: one per (plug, crossings undone). The plugs always end the
            # gripper span apart: a flip's mirror image can put a plug right
            # next to the other one.
            for move, after in best_flips(state, state_found, params, separate_plugs=True, layer=depth + 1, make_room=False):
                last = len(move.lift.lifted) == len(state_found)
                if not last and depth + 1 >= max_moves:
                    continue
                extend(move, after, moves, ropes, predicted, depth, make_room=make_room)
            # A make-room flip (undoing nothing: a plug turned out of the way
            # so the next flip's mirror image fits) -- one per plan, at any
            # depth that leaves room for the flip it makes room for; tried only
            # when no plan of crossing-undoing flips alone exists (second pass).
            if make_room and depth + 2 <= max_moves:
                for move, after in best_flips(state, state_found, params, separate_plugs=True, layer=depth + 1, make_room=True):
                    extend(move, after, moves, ropes, predicted, depth, make_room=False)
            # A crossing too deep down the rope for a flip is undone by a
            # FINISHING lay move under the one-move rules (laid no tauter than
            # slack_max_single, the "6"'s recipe): nothing follows it, so its
            # rope need not land where a model says.
            finishing = replace(params, slack_max=min(params.slack_max, params.slack_max_single))
            for lift in lifts(state, state_found, params):
                if len(lift.lifted) != len(state_found):
                    continue
                landed = land(state, state_found, lift, finishing, separate_plugs=True, layer=depth + 1)
                if landed is not None:
                    extend(landed[0], landed[1], moves, ropes, predicted, depth)
            return
        for lift in lifts(state, state_found, params):
            last = len(lift.lifted) == len(state_found)
            if not last and depth + 1 >= max_moves:
                continue
            # A move with another before or after it in the episode.
            multi = (not last) or depth + moves_done > 0
            move_params = (replace(params, slack_min=max(params.slack_min, params.slack_min_multi)) if multi
                           else replace(params, slack_max=min(params.slack_max, params.slack_max_single)))
            landed = land(state, state_found, lift, move_params, separate_plugs=multi, layer=depth + 1)
            if landed is None:
                continue
            move, after = landed
            extend(move, after, moves, ropes, predicted, depth)

    search(rope, found, (), (), (), 0)
    if params.flip_moves and max_moves >= 2 and not any(not has_lay(p) for p in complete):
        # No plan of flips alone: a make-room flip first (a plug moved out of
        # the way so the next flip's mirror image fits) may give one.
        search(rope, found, (), (), (), 0, make_room=True)
    complete.sort(key=score)
    if not complete:
        return []
    best = score(complete[0])[:2]
    return [p for p in complete if score(p)[:2] == best]
