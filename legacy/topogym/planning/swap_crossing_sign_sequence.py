"""Offline sequence planner for swap_crossing_sign: which rope, lifted from where, laid where.

Physical picture. Ropes grow out of a power strip and end in flat plugs; the arm
only ever grasps a plug. One move = grasp a plug, lift until a length ``hang`` of
rope hangs below the hand, carry it sideways, lay it down. The rope leaves the
table at the *peel point* (``hang`` of arclength back from the plug); everything
past it comes up, everything before it stays where it lies. Laid back down, the
lifted part lies on top of every rope it crosses -- the rope placed last is on
top -- and that is the only way a crossing's over/under can change: pulling a rope
out from under another was measured not to work (FEM+IPC contact test run17,
`docs/develop/physics/rope_backend_migration_zh.md`: the crossing survives).

So flipping a crossing takes two moves at least (take the upper rope off, lay
the lower one over), and with two crossings the order is forced and the plugs
walk sideways move after move. This module searches for such a sequence on
geometry alone, before any physics runs.

Model (what "on geometry alone" means here):

- a rope is a top-down polyline plus, per vertex, its true arclength -- a tail
  laid as a straight chord is still the rope's full length (the slack is simply
  not drawn), and every lift is computed from true arclength;
- a move replaces the rope past the peel point with the straight chord
  peel -> landing, stacked above everything laid before it;
- **the hand stays within ``carry_taut * hang`` of the peel point** at every
  waypoint -- lifting, swinging round, at the end of the sideways carry. Held
  further, the hand asks for more rope than it lifted and the rope answers by
  peeling further -- the peel point this model treats as fixed then moves.
  Measured on the 2026-09-11 stage C episodes: a hand at height = hang travelling
  0.7-0.9 of hang needs 1.23-1.26x the tail it holds and dragged the rope 4-8 cm
  per move (band_untwist measured the same drag, 85-91 mm, on the same rope model);
- **how high the carried tail rides is measured, not a straight line** from the
  peel point to the hand (`carried_height`): its first stretch stays on the
  table, longer the lower the hand. A crossing clears the rope under it when that
  height reaches ``obstacle_top + rope_over_rope_clearance`` plus the fit's error,
  and the hand is carried at the lowest height that gives every crossing that;
- **the tail is laid nearly straight**, 95-97 % of its length out from the peel
  point, and has to cross the same ropes in the same order when bent out to
  either side by the bend that slack leaves plus 1 cm (2026-09-13, measured
  bends in `candidate_moves`);
- a rope still pinned under another rope upstream (it is under a crossing before
  the peel point) may be lifted past that crossing only by a hang that leaves
  ``hold`` of rope on the table beyond it. Whether friction really holds it there
  is the open physical question of this task (plan stage B probe).

Candidates per state: every rope x a few hang lengths (just enough to lift each
crossing it is on top of, plus a grid) x landings on a ring round the peel point,
in every direction. Landings that end up with the same crossings are one choice,
represented by up to four of them: nearest the plug's current place, furthest
out in x, widest margins, nearest the other ropes' plugs -- the widest alone
walks plugs into corners from which no later move reaches. Best-first search on
(moves so far + half the crossings still wrong) finds short sequences quickly.
"""

from __future__ import annotations

import heapq
import itertools
import math
from dataclasses import dataclass

import numpy as np

from .rope_crossings import (
    CrossingCode,
    arclength,
    crossing_code,
    find_crossings,
    flip_code,
    pair_tops,
    segment_hits,
)


@dataclass(frozen=True)
class SequenceParams:
    table_z: float = 0.0
    obstacle_top: float = 0.023  # top of a rope lying across another: base_z + over_lift + radius
    # Daylight a carried rope keeps over the top of a rope it passes over
    # (pinch.rope_over_rope_clearance). NOT the hand's own lift clearance, which
    # is what this borrowed until 2026-09-11: 4 cm of it demands 9-11 cm of rope
    # past the peel point and left a quarter of the one-crossing layouts with no
    # plan. Measured at 1.5 cm the rope underneath moves 1-3 mm; at 1.0 cm it
    # starts to be dragged (16 mm).
    rope_over_rope_clearance: float = 0.015
    # Margin under the workspace ceiling for lift-estimate error. swap's own GPU
    # runs measured the separate lift within 1 mm of the prediction (2026-09-06);
    # band_untwist's old "+-26 mm" turned out to be a lobe-arc formula error, not
    # physics (found 2026-09-10). 1 cm covers spline-vs-control-polygon arc.
    lift_error: float = 0.010
    z_max: float = 0.40  # workspace.z_max
    anchor_run: float = 0.03  # rope held at the strip; never lifted
    hold: float = 0.03  # rope left on the table past a crossing it is pinned under
    tau_min: float = 0.95  # |landing - peel| / hang: the tail is laid nearly straight (candidate_moves)
    tau_max: float = 0.97  # pinch.max_taut_ratio
    # How taut the lifted tail is carried: the hand sits this fraction of the
    # hanging length away from the peel point, along the straight line from it.
    # 1.0 would be dead taut (and any error peels more rope); above 1.0 the rope
    # is dragged, which is what the stage C episodes did.
    carry_taut: float = 0.95
    place_clearance: float = 0.035  # landing to any other rope (fingers)
    plug_clearance: float = 0.070  # landing to any other plug (free_end_connector.min_clearance)
    corridor_clearance: float = 0.026  # laid tail to ropes it does not cross: 0.016 + spring-back band
    corridor_skip: float = 0.04  # rope ignored either side of a crossing when measuring the corridor
    x_min: float = -0.21  # workspace.x[0] + margin: landings now go all round, so behind the strip too
    x_max: float = 0.221  # plug pin tip inside workspace.x
    y_limits: tuple[float, float] = (-0.26, 0.26)  # workspace.y minus margin
    merge_radius: float = 0.012  # success.crossing_merge_radius
    # Landings on a ring round the peel point, every direction. 2 degrees, not 4,
    # and a 1 cm hang grid below: with the tail laid nearly straight and the carry
    # height from carried_height, which landing and hang work is a narrow choice --
    # the coarser search left 15/300 layouts without a plan, this one 3/300
    # (2026-09-13, docs/develop/tasks/swap_crossing_sign_zh.md 7.15).
    fan_step_deg: float = 2.0
    fan_taus: tuple[float, ...] = (0.95, 0.97)  # ring radii as a fraction of the hang
    # Sideways margin on top of the predicted bend (length * sqrt(6 * slack) / 4).
    # Over 63 GPU lays the measured bend exceeded that formula by at most 0.1 cm.
    bend_extra: float = 0.002
    bend_segments: int = 8  # polyline segments of a bent tail
    # The laid tail's bend when the swing drags rope in from before the peel point
    # (candidate_moves): the ratio x the lifted length, ramping in from
    # `slide_free_swing_deg` over `slide_ramp_deg`. Upper envelope of 12 GPU moves on
    # 2026-09-13 at rope-on-table friction 0.17, so conservative at higher friction.
    slide_free_swing_deg: float = 35.0
    slide_ramp_deg: float = 25.0
    slide_bend_ratio: float = 0.28
    slide_short_hang: float = 0.15  # tails shorter than this may not swing further than:
    slide_short_swing_deg: float = 60.0
    # No swing beyond what the slide above was measured over (120 deg). The 2x1 demo
    # of 2026-09-13 swung a rope 148 deg into the corner by the strip, and the next
    # rope could no longer be laid across it.
    max_swing_deg: float = 120.0
    # carried_height's fit (2026-09-12 carry dumps) and its 95th-percentile
    # over-estimate where a clearance is decided (2-6 cm off the table)
    runout_slope: float = 1.08
    runout_offset: float = -0.030
    height_margin: float = 0.012
    hand_floor: float = 0.08  # lowest carry; 8.3 cm is the lowest that has run and matched its plan
    hand_step: float = 0.01
    swing_step_deg: float = 30.0  # hand waypoints round the peel point at most this far apart
    hang_grid: tuple[float, ...] = tuple(round(0.10 + 0.01 * i, 2) for i in range(31))  # 10-40 cm, 1 cm apart
    min_margin: float = 0.008  # a landing "with some margin" when picking the one nearest the plug
    max_moves: int = 5
    max_expansions: int = 3000

    @property
    def clear_arc(self) -> float:
        return self.obstacle_top + self.rope_over_rope_clearance

    @property
    def max_hand(self) -> float:
        return self.z_max - self.lift_error


@dataclass
class RopeLay:
    xyz: np.ndarray  # (N, 3): xy centerline; z = stacking height (only its order matters)
    s: np.ndarray  # true arclength of each vertex from the anchored end

    @property
    def length(self) -> float:
        return float(self.s[-1])

    @property
    def anchor(self) -> np.ndarray:
        return self.xyz[0, :2]

    @property
    def plug(self) -> np.ndarray:
        return self.xyz[-1, :2]

    def at(self, s: float) -> np.ndarray:
        i = int(np.clip(np.searchsorted(self.s, s) - 1, 0, len(self.s) - 2))
        t = (s - self.s[i]) / max(self.s[i + 1] - self.s[i], 1e-12)
        return self.xyz[i] + float(np.clip(t, 0.0, 1.0)) * (self.xyz[i + 1] - self.xyz[i])


State = dict[int, RopeLay]


@dataclass(frozen=True)
class Move:
    strand: int
    hang: float  # rope lifted off the table, measured back along the rope from the plug
    hand_height: float  # how high the hand carries it: the lowest that lifts every crossing clear (carried_height)
    peel_xy: tuple[float, float]
    land_xy: tuple[float, float]
    pinned_at: float | None  # arclength of the crossing this rope is still under, if any
    hang_window: tuple[float, float]  # hang range that keeps the lifted crossings clear and the pin held
    reach: float  # |landing - peel| / (tau_max * hang); <= 1 is reachable
    land_clearance: float  # to the nearest other rope
    corridor_clearance: float  # laid tail to the nearest rope it does not cross
    code_after: CrossingCode

    @property
    def margin(self) -> float:
        return min(
            self.land_clearance - 0.035,
            self.corridor_clearance - 0.026,
            0.5 * (self.hang_window[1] - self.hang_window[0]),
        )


@dataclass(frozen=True)
class Plan:
    moves: tuple[Move, ...]
    target: CrossingCode
    expansions: int

    @property
    def max_hand_height(self) -> float:
        """Highest the hand goes in the sequence -- what the workspace ceiling limits."""

        return max((m.hand_height for m in self.moves), default=0.0)


def params_from_config(task_cfg, **overrides) -> SequenceParams:
    """The planner's numbers from the swap task config (task frame: table at z = 0).

    Only what the task yaml already pins is read from it; the rest keeps the
    defaults above, which were set by the offline feasibility study.
    """

    ws = task_cfg.workspace
    pinch = task_cfg.pinch
    connector = task_cfg.rope.free_end_connector
    plug_ahead = 0.5 * float(connector.column_height) + float(connector.flange_height) + float(connector.pin_depth)
    margin = float(ws.margin)
    values = dict(
        rope_over_rope_clearance=float(
            getattr(pinch, "rope_over_rope_clearance", None) or pinch.lift_clearance
        ),
        z_max=float(ws.z_max),
        tau_max=float(pinch.max_taut_ratio),
        place_clearance=float(pinch.place_clearance),
        plug_clearance=float(getattr(connector, "min_clearance", 0.07)),
        x_min=float(ws.x[0]) + margin,
        x_max=float(ws.x[1]) - plug_ahead,
        y_limits=(float(ws.y[0]) + margin, float(ws.y[1]) - margin),
        merge_radius=float(task_cfg.success.crossing_merge_radius),
    )
    values.update(overrides)
    return SequenceParams(**values)


def rope_lays(polylines: dict[int, np.ndarray]) -> State:
    """Spawn (or measured) polylines -> planner state, arclength = drawn length."""

    return {k: RopeLay(np.asarray(p, dtype=float).copy(), arclength(p)) for k, p in polylines.items()}


def crossings_of(state: State, params: SequenceParams):
    return find_crossings(
        {k: lay.xyz for k, lay in state.items()},
        merge_radius=params.merge_radius,
        arcs={k: lay.s for k, lay in state.items()},
    )


def code_of(state: State, params: SequenceParams) -> CrossingCode:
    return crossing_code(crossings_of(state, params))


def _point_polyline_distance(points: np.ndarray, poly: np.ndarray) -> np.ndarray:
    """Distance from each xy point to a polyline (vectorized over points)."""

    a = poly[:-1, :2][None]
    b = poly[1:, :2][None]
    p = np.asarray(points, dtype=float)[:, None, :2]
    ab = b - a
    denom = np.maximum(np.einsum("ijk,ijk->ij", ab, ab), 1e-18)
    t = np.clip(np.einsum("ijk,ijk->ij", p - a, ab) / denom, 0.0, 1.0)
    closest = a + t[..., None] * ab
    return np.linalg.norm(closest - p, axis=2).min(axis=1)


def _hang_candidates(lay: RopeLay, on_rope, params: SequenceParams) -> list[tuple[float, float, float, float | None]]:
    """(hang, window_lo, window_hi, pinned_at) choices for one rope."""

    over = sorted(s for s, is_over in on_rope if is_over)
    under = [s for s, is_over in on_rope if not is_over]
    pinned_at = max(under) if under else None
    # The hand height is chosen separately (candidate_moves), so the workspace
    # ceiling limits the hand, not how much rope comes up: a crossing near the
    # anchor can only be lifted clear by lifting nearly the whole rope.
    hang_hi = lay.length - params.anchor_run
    if pinned_at is not None:
        hang_hi = min(hang_hi, lay.length - pinned_at - params.hold)
    # Just enough to lift each crossing clear, plus 2 mm so the boundary test
    # below does not throw the minimum away on rounding -- and two to four times
    # that, because the first stretch of a lifted tail stays on the table
    # (carried_height) and a crossing then has to sit further along to ride clear.
    wanted = {
        lay.length - s + multiple * params.clear_arc + 0.002
        for s in over
        for multiple in (1.0, 2.0, 3.0, 4.0)
    } | set(params.hang_grid)
    out = []
    for hang in sorted(wanted):
        if not 0.08 <= hang <= hang_hi:
            continue
        peel = lay.length - hang
        # A crossing this rope is on top of must be either left alone (before the
        # peel point) or lifted clear -- not half lifted and dragged.
        if any(peel < s < peel + params.clear_arc - 1e-6 for s in over):
            continue
        lifted = [s for s in over if s > peel]
        window_lo = max((lay.length - s + params.clear_arc for s in lifted), default=0.08)
        out.append((float(hang), float(window_lo), float(hang_hi), pinned_at))
    return out


def carried_height(a, hang: float, hand, params: SequenceParams):
    """Height of the carried tail's underside at arclength ``a`` past the peel point.

    Measured, not the straight line from the peel point to the hand: the first
    stretch of a lifted tail stays on the table, the longer the lower the hand and
    the longer the tail. Fitted on 821 samples from 18 carries saved at the end of
    the sideways carry (2026-09-12 runs, ``carry_NN.npz``): a run-out of
    ``1.08 * (hang - hand) - 3.0 cm``, then a straight rise to the hand. Where a
    clearance is decided (2-6 cm off the table) the fit is 0.4 cm low at the median
    and at most 1.2 cm high for 95 % of samples; the straight line it replaces was
    3.5 cm high at the median.
    """

    reach = params.carry_taut * hang
    runout = np.clip(params.runout_slope * (hang - hand) + params.runout_offset, 0.0, 0.9 * reach)
    return hand * np.maximum(a - runout, 0.0) / (reach - runout)


def _bent_tails(peel: np.ndarray, lands: np.ndarray, bow: np.ndarray, segments: int) -> np.ndarray:
    """Tails peel -> landing bowed sideways by ``bow`` at the middle (a parabola), (n, segments + 1, 2)."""

    u = np.linspace(0.0, 1.0, segments + 1)[None, :, None]
    chord = lands - peel[None]
    normal = np.stack([-chord[:, 1], chord[:, 0]], axis=1) / np.maximum(np.linalg.norm(chord, axis=1), 1e-12)[:, None]
    return peel[None, None] + u * chord[:, None] + 4.0 * u * (1.0 - u) * (bow[:, None] * normal)[:, None]


def _tail_contacts(tails: np.ndarray, state: State, r: int, others, crossings, s_peel: float, params: SequenceParams):
    """Where candidate tails meet the other ropes.

    ``tails`` is (n, m + 1, 2): one polyline of m equal segments per candidate.
    Returns, per candidate, the ropes it crosses as (fraction along the tail, rope),
    and how close it passes to rope it does not cross (the corridor) -- not counting
    a rope near where the tail crosses it, nor near this rope's own remaining
    crossings with it (the pin).
    """

    n, m = tails.shape[0], tails.shape[1] - 1
    starts = tails[:, :-1].reshape(-1, 2)
    ends = tails[:, 1:].reshape(-1, 2)
    signature = [[] for _ in range(n)]
    corridor = np.full(n, np.inf)
    for q in others:
        qpoly = state[q].xyz
        s_q_axis = state[q].s
        ks, js, ts, us = segment_hits(starts, ends, qpoly)
        tail_of = ks // m
        s_hits = s_q_axis[js] + us * (s_q_axis[js + 1] - s_q_axis[js])
        for k, t in zip(tail_of, (ks % m + ts) / m):
            signature[k].append((round(float(t), 2), q))
        keep = np.ones((n, len(qpoly)), dtype=bool)
        for c in crossings:
            if {c.a, c.b} == {r, q}:
                s_on_q = c.s_a if c.a == q else c.s_b
                s_on_r = c.s_a if c.a == r else c.s_b
                if s_on_r <= s_peel:
                    keep &= (np.abs(s_q_axis - s_on_q) > params.corridor_skip)[None]
        if len(ks):
            near_hit = np.abs(s_q_axis[None, :] - s_hits[:, None]) <= params.corridor_skip
            blocked = np.zeros_like(keep)
            np.logical_or.at(blocked, tail_of, near_hit)
            keep &= ~blocked
        d = ends - starts
        w = qpoly[None, :, :2] - starts[:, None, :]
        t_proj = np.clip(np.einsum("ijk,ik->ij", w, d) / np.maximum(np.einsum("ik,ik->i", d, d), 1e-18)[:, None], 0.0, 1.0)
        gap = np.linalg.norm(w - t_proj[..., None] * d[:, None, :], axis=2).reshape(n, m, -1).min(axis=1)
        corridor = np.minimum(corridor, np.where(keep, gap, np.inf).min(axis=1))
    return signature, corridor


def candidate_moves(state: State, params: SequenceParams, stamp: float, *, moved_bystanders: frozenset = frozenset()):
    """Yield (Move, next_state) -- one representative per distinct outcome."""

    crossings = crossings_of(state, params)
    code_now = crossing_code(crossings)
    ropes = sorted(state)
    involved = {c.a for c in crossings} | {c.b for c in crossings}
    for r in ropes:
        lay = state[r]
        # Where the other ropes' plugs sit: a landing near here keeps this rope
        # within reach of whatever has to cross it later.
        others_plugs = [state[q].plug for q in ropes if q != r]
        homes = np.mean(others_plugs, axis=0) if others_plugs else lay.plug
        on_r = [((c.s_a if c.a == r else c.s_b), c.over == r) for c in crossings if r in (c.a, c.b)]
        others = [q for q in ropes if q != r]
        for hang, win_lo, win_hi, pinned_at in _hang_candidates(lay, on_r, params):
            s_peel = lay.length - hang
            peel = lay.at(s_peel)[:2]
            # Landings on a ring round the peel point, 95-97 % of the lifted length
            # out, in every direction. Laid shorter, the tail bends out by about
            # length * sqrt(6 * slack) / 4 (55 GPU lays 2026-09-12: 7.1 cm median at
            # the 10-30 % slack the 70-90 % window used to leave, correlation 0.81)
            # and the plan no longer says where the rope lies. Every direction,
            # because the lay that puts one rope across two others can point back
            # past the strip's side: seed 0 and 3's last lays (2026-09-13) had none
            # within the 85 degrees of +x this used to search.
            bearings = np.radians(np.arange(0.0, 360.0, params.fan_step_deg))
            lands = np.concatenate(
                [peel[None] + tau * hang * np.stack([np.cos(bearings), np.sin(bearings)], axis=1) for tau in params.fan_taus]
            )
            spread = np.linalg.norm(lands - peel[None], axis=1)
            ok = (spread >= params.tau_min * hang - 1e-9) & (spread <= params.tau_max * hang + 1e-9)
            ok &= (lands[:, 0] >= params.x_min) & (lands[:, 0] <= params.x_max)
            ok &= (lands[:, 1] >= params.y_limits[0]) & (lands[:, 1] <= params.y_limits[1])
            # reach from the anchor as well (the whole rope, not just the tail)
            ok &= np.linalg.norm(lands - lay.anchor[None], axis=1) <= params.tau_max * lay.length
            land_clear = np.full(len(lands), np.inf)
            for q in others:
                land_clear = np.minimum(land_clear, _point_polyline_distance(lands, state[q].xyz))
                ok &= np.linalg.norm(lands - state[q].plug[None], axis=1) >= params.plug_clearance
            ok &= land_clear >= params.place_clearance
            # the new tail may not cross the rope's own remaining part
            prefix = lay.xyz[: max(int(np.searchsorted(lay.s, s_peel - 0.01)), 2)]
            if len(prefix) >= 2:
                k_self, _, _, _ = segment_hits(np.repeat(peel[None], len(lands), 0), lands, prefix)
                ok[np.unique(k_self)] = False
            if not ok.any():
                continue

            # Which ropes each candidate tail crosses, in order along it, and how
            # close it passes to rope it does not cross.
            straight = np.stack([np.repeat(peel[None], len(lands), 0), lands], axis=1)
            signature, corridor = _tail_contacts(straight, state, r, others, crossings, s_peel, params)
            ok &= corridor >= params.corridor_clearance
            keys = [tuple(q for _t, q in sorted(hits)) for hits in signature]
            # The rope will not lie on the chord. Laid with 3-5 % slack it still
            # bends out ~3 cm, and the end directions pick the side only 4 times in
            # 5 (52 GPU lays), so the tail has to cross the same ropes in the same
            # order bent out either way by the predicted bend plus `bend_extra`.
            # Swing: how far the tail turns round the peel point, from where the plug
            # lies now to the landing. That turn drags the rope lying just before the
            # peel point along (12 GPU moves 2026-09-13: 0.3-1.1 cm at <= 41 deg,
            # 3.6-4.8 cm at 53-79 deg, 6.7-13.1 cm at 108-120 deg; rank correlation
            # +0.94, none with hand height), and the extra rope bends the laid tail
            # further out than its planned slack says: 0.21-0.28 x the lifted length
            # at swings of 60 deg and more, 0.14-0.16 at 53-61 deg.
            to_plug = lay.plug - peel
            swing = np.degrees(np.arccos(np.clip(
                ((lands - peel[None]) @ to_plug) / np.maximum(spread * np.linalg.norm(to_plug), 1e-12), -1.0, 1.0)))
            # The one short tail swung far (11 cm lifted, 120 deg) slid its whole length.
            ok &= ~((swing > params.slide_short_swing_deg) & (hang < params.slide_short_hang))
            ok &= swing <= params.max_swing_deg
            live = np.nonzero(ok)[0]
            if len(live):
                slack_bend = hang * np.sqrt(6.0 * np.clip(1.0 - spread[live] / hang, 0.0, 1.0)) / 4.0
                slide_bend = params.slide_bend_ratio * hang * np.clip(
                    (swing[live] - params.slide_free_swing_deg) / params.slide_ramp_deg, 0.0, 1.0)
                bow = np.maximum(slack_bend, slide_bend) + params.bend_extra
                for side in (1.0, -1.0):
                    bent = _bent_tails(peel, lands[live], side * bow, params.bend_segments)
                    bent_signature, _ = _tail_contacts(bent, state, r, others, crossings, s_peel, params)
                    for k, hits in zip(live, bent_signature):
                        if tuple(q for _t, q in sorted(hits)) != keys[k]:
                            ok[k] = False
                    if len(prefix) >= 2:
                        # Against the rope's own remaining part only the slack bend counts.
                        # The slide part of the band is that remaining part itself being
                        # dragged along with the swing, so testing it against where the
                        # head lay before the move counts the drag twice. (2x1 demo seed 1,
                        # 09-13: the one lay that would have finished the episode failed
                        # only this test.)
                        own = _bent_tails(peel, lands[live], side * (slack_bend + params.bend_extra), params.bend_segments)
                        k_self, _, _, _ = segment_hits(own[:, :-1].reshape(-1, 2), own[:, 1:].reshape(-1, 2), prefix)
                        ok[live[np.unique(k_self // params.bend_segments)]] = False
            # Carry height: the lowest on the grid at which every crossing the tail
            # has to pass over rides clear -- the ones this rope is on top of and is
            # lifting off, and the ropes the new tail will lie across (at arclength
            # t * hang along it).
            lifted_over = [s - s_peel for s, is_over in on_r if is_over and s > s_peel]
            first_new = np.array([min((t for t, _q in hits), default=np.inf) for hits in signature]) * hang
            nearest = np.minimum(first_new, min(lifted_over, default=np.inf))
            hands = np.arange(params.hand_floor, min(params.max_hand, 0.9 * params.carry_taut * hang) + 1e-9, params.hand_step)
            if not len(hands):
                continue
            clears = carried_height(nearest[None, :], hang, hands[:, None], params) >= params.clear_arc + params.height_margin
            ok &= clears.any(axis=0)
            hand_height = hands[np.argmax(clears, axis=0)]
            if not ok.any():
                continue

            reach = spread / (params.tau_max * hang)
            displacement = np.linalg.norm(lands - lay.plug[None], axis=1)
            # Per outcome, two representatives: the landing nearest where the plug
            # is now among those with some margin (keeps the plugs from walking
            # off -- every later move has to reach past them), and the landing with
            # the widest margin.
            groups: dict[tuple, list[int]] = {}
            for k in np.nonzero(ok)[0]:
                groups.setdefault(tuple(q for _t, q in sorted(signature[k])), []).append(int(k))
            picks: list[tuple[tuple, int]] = []
            for key, members in groups.items():
                margin = {
                    k: min(land_clear[k] - params.place_clearance, corridor[k] - params.corridor_clearance)
                    for k in members
                }
                roomy = [k for k in members if margin[k] >= params.min_margin] or members
                chosen = [
                    min(roomy, key=lambda k: displacement[k]),
                    max(roomy, key=lambda k: (round(lands[k][0], 3), -displacement[k])),
                    max(members, key=lambda k: margin[k]),
                    # ...and the landing that stays nearest the other ropes' plugs.
                    # Without it a move that only has to get a rope out of the way
                    # takes the roomiest landing, which is the table's edge, and the
                    # rope it parked there is then out of reach of every later move
                    # (2026-09-12: a 3-rope episode parked one rope at +24 cm of y
                    # and no later lay could cross it again).
                    min(roomy, key=lambda k: float(np.linalg.norm(lands[k] - homes))),
                ]
                for k in dict.fromkeys(chosen):
                    picks.append((key, k))
            for key, k in picks:
                if not key and r in involved:
                    lifted_over = [s for s, is_over in on_r if is_over and s > s_peel]
                    if not lifted_over:
                        continue  # moves nothing that matters
                if not key and r not in involved and r in moved_bystanders:
                    continue
                land = lands[k]
                n_tail = max(2, int(math.ceil(float(np.linalg.norm(land - peel)) / 0.01)))
                t = np.linspace(0.0, 1.0, n_tail + 1)[1:]
                keep_n = max(int(np.searchsorted(lay.s, s_peel)), 1)
                head_xyz = lay.xyz[:keep_n]
                head_s = lay.s[:keep_n]
                peel_xyz = np.array([peel[0], peel[1], lay.at(s_peel)[2]])
                tail_xyz = np.column_stack([peel[0] + t * (land[0] - peel[0]), peel[1] + t * (land[1] - peel[1]), np.full(len(t), stamp)])
                new_lay = RopeLay(
                    np.vstack([head_xyz, peel_xyz[None], tail_xyz]),
                    np.concatenate([head_s, [s_peel], s_peel + t * hang]),
                )
                nxt = dict(state)
                nxt[r] = new_lay
                code_after = code_of(nxt, params)
                if code_after == code_now and r in involved:
                    continue
                yield (
                    Move(
                        strand=int(r),
                        hang=float(hang),
                        hand_height=float(hand_height[k]),
                        peel_xy=(float(peel[0]), float(peel[1])),
                        land_xy=(float(land[0]), float(land[1])),
                        pinned_at=pinned_at,
                        hang_window=(float(win_lo), float(win_hi)),
                        reach=float(reach[k]),
                        land_clearance=float(land_clear[k]),
                        corridor_clearance=float(corridor[k]),
                        code_after=code_after,
                    ),
                    nxt,
                )


def _mismatch(code: CrossingCode, target: CrossingCode) -> int:
    """How far ``code`` is from the goal, counted per rope pair.

    The goal is "every pair that crossed at spawn crosses the same number of times
    with the other rope on top" (decision 2026-09-12), so the order of a pair's
    crossings along the ropes does not count against it -- ``target`` is one end
    state that satisfies the goal and is used here only to read the pairs and their
    tops out of. A pair is 2 away when it is missing or extra, 1 away when it
    crosses the right number of times with the wrong rope on top.
    """

    got, want = pair_tops(code), pair_tops(target)
    wrong = 0
    for pair in set(got) | set(want):
        here, there = got.get(pair, ()), want.get(pair, ())
        # a crossing that is there but with the wrong rope on top is wrong twice
        # (this top is not wanted, the wanted one is not here); a missing or extra
        # crossing is wrong once -- the same scale the exact comparison used.
        wrong += 2 * sum(g != w for g, w in zip(here, there))
        wrong += abs(len(here) - len(there))
    return wrong


def goal_reached(code: CrossingCode, target: CrossingCode) -> bool:
    """Does ``code`` satisfy what ``target`` asks for, judged per rope pair?

    The judge grades the over/under of each pair that crossed at spawn, not the
    exact code (decision 2026-09-12), so an end state whose two crossings sit in
    the other order along a rope counts as reached.
    """

    return _mismatch(code, target) == 0


def _pair_counts(code: CrossingCode) -> dict[tuple[int, int], int]:
    counts: dict[tuple[int, int], int] = {}
    for a, _ra, b, _rb, _o in code:
        counts[(a, b)] = counts.get((a, b), 0) + 1
    return counts


def _allowed(code: CrossingCode, cap: dict[tuple[int, int], int]) -> bool:
    """No crossing between ropes that cross neither at the start nor in the target,
    and no more crossings per pair than the larger of the two -- a sequence taking
    crossings away still has some left halfway."""

    return all(count <= cap.get(pair, 0) for pair, count in _pair_counts(code).items())


def plan_sequence(
    state: State,
    target: CrossingCode,
    params: SequenceParams | None = None,
    moved_bystanders: frozenset = frozenset(),
) -> Plan | None:
    """Shortest-first search for moves that turn ``state`` into ``target``.

    ``moved_bystanders`` carries the episode's own history into the search: ropes
    already moved and left in no crossing are not moved again as bystanders, as
    within one plan. Re-planning from scratch after every move forgot that, and two
    episodes spent their budget re-laying the same rope to make room that its lay
    kept taking away again (seed 6 on 2026-09-12, the 2x1 demo seed 1 on 09-13).

    No move may leave more crossing-code entries wrong than the one before it.
    Taking crossings apart is still allowed -- removing a wrong crossing puts the
    code *closer* to the target, since a missing entry counts once and a wrong one
    counts twice. What it rules out is undoing progress, which costs nothing
    offline (2026-09-12: identical plans and move counts over 90 seeds in all
    three cells) and cost a real episode: seed 5's route took its two crossings
    apart, laid them back the way they spawned (mismatch 2 -> 4) and stripped them
    again, spending four of its six moves to return to where it started.
    """

    params = params or SequenceParams()
    start = code_of(state, params)
    # The goal is per rope pair, not the exact code: any end state whose pairs
    # cross as often as the target's with the same rope on top counts (decision
    # 2026-09-12), so two crossings on different pairs may end up in either order.
    if _mismatch(start, target) == 0:
        return Plan((), target, 0)
    at_start, in_target = _pair_counts(start), _pair_counts(target)
    cap = {pair: max(at_start.get(pair, 0), in_target.get(pair, 0)) for pair in set(at_start) | set(in_target)}
    tie = itertools.count()
    frontier = [(0.5 * _mismatch(start, target), 0, next(tie), state, (), frozenset(moved_bystanders), _mismatch(start, target), 1.0)]
    seen: set = set()
    expansions = 0
    while frontier and expansions < params.max_expansions:
        _f, depth, _t, st, moves, bystanders, wrong, worst = heapq.heappop(frontier)
        key = (code_of(st, params), tuple(tuple(np.round(st[k].plug, 2)) for k in sorted(st)))
        if key in seen:
            continue
        seen.add(key)
        expansions += 1
        if depth >= params.max_moves:
            continue
        for move, nxt in candidate_moves(st, params, stamp=1.0 + depth, moved_bystanders=bystanders):
            if not _allowed(move.code_after, cap):
                continue
            after = _mismatch(move.code_after, target)
            if after > wrong:
                continue
            chain = moves + (move,)
            if after == 0:
                return Plan(chain, target, expansions)
            involved = {c for entry in move.code_after for c in (entry[0], entry[2])}
            new_by = bystanders | ({move.strand} if move.strand not in involved else set())
            # Take the rope that has nothing lying on it first (C off A, then A off
            # B, then B): grasping a rope another rope still pins means lifting only
            # the part past the pin and trusting friction to hold the rest, which
            # works (2026-09-10 probe) but is the harder move, so it is the fallback
            # rather than the default. A third of a move's worth of penalty keeps a
            # top-first plan ahead of a pinned plan of the same length.
            # Among plans of the same length, prefer the one whose TIGHTEST move has
            # the most room: every move is re-planned from the measured ropes, and a
            # move that only just satisfies its clearances is the one a few cm of
            # settle drift takes away. Weighted so it never outranks a shorter plan
            # (a whole move costs 1; 5 cm of room costs 0.1).
            room = min(worst, max(move.margin, -1.0))
            f = (depth + 1 + 0.5 * after - 2.0 * room
                 + (0.35 if move.pinned_at is not None else 0.0))
            heapq.heappush(frontier, (f, depth + 1, next(tie), nxt, chain, frozenset(new_by), after, room))
    return None


def best_progress_move(state: State, target: CrossingCode, params: SequenceParams | None = None) -> Move | None:
    """The single move that gets the crossing code closest to ``target``, or None.

    For when no complete sequence exists from here. Measured 2026-09-12 on the
    3-rope 2-crossing episodes: both dead ends still had a move that put one more
    crossing right (mismatch 2 -> 1), while the sequence search found nothing
    within its five, so the oracle stopped with a move available. Two crossings
    have to be taken apart before they can be rebuilt, and from the stripped-out
    state a full rebuild is often beyond the search's horizon even though the
    first step of it is there.

    Every returned move must *strictly* reduce the mismatch, which is what keeps
    this from oscillating: the count only falls, and it starts at four at worst.
    """

    params = params or SequenceParams()
    now = _mismatch(code_of(state, params), target)
    best: tuple[int, float, Move] | None = None
    for move, _nxt in candidate_moves(state, params, stamp=1.0):
        score = _mismatch(move.code_after, target)
        if score >= now:
            continue
        if best is None or (score, -move.margin) < (best[0], -best[2].margin):
            best = (score, move.margin, move)
    return None if best is None else best[2]


def target_for(mode: str, spawn: CrossingCode) -> CrossingCode:
    """oracle: flip every crossing; flip_nearest: only the one with the largest ranks."""

    if mode == "oracle":
        return flip_code(spawn)
    if mode == "flip_nearest":
        if not spawn:
            return spawn
        nearest = max(spawn, key=lambda e: e[1] + e[3])
        return tuple(sorted(flip_code((nearest,)) + tuple(e for e in spawn if e != nearest)))
    raise ValueError(f"unknown mode {mode!r}")


__all__ = [
    "Move",
    "Plan",
    "RopeLay",
    "SequenceParams",
    "best_progress_move",
    "candidate_moves",
    "code_of",
    "goal_reached",
    "params_from_config",
    "plan_sequence",
    "rope_lays",
    "target_for",
]
