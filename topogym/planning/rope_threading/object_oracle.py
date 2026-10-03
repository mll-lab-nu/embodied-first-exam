"""Constructive object-only witness for Rope Threading: follow-the-leader model.

Model. The rope centerline is a chain of material stations sliding along one
fixed track: its own initial U-shaped centerline on the table, continued by a
planned tip route. At tip travel sigma, station u sits at track(u + sigma).
Hands are clearance spheres attached to material stations for scheduled travel
intervals (two-hand relay: one hand pushes the tip through a ring, the other
receives it on the exit side, then the pusher releases).

Certified (geometry only, with stated numerical error budgets): for every
travel value the rope tube keeps the requested clearance to rings, stands and
bases (each surface point moves at most the travel difference, so sampled FCL
distances give interval lower bounds); the rope stays above the table; the
observed signed crossing sequence only grows as a prefix of the target; the
final polyline satisfies the Task's own geometric crossing rule; attached hand
spheres keep their clearance and never overlap each other.

Not certified: gravity sag, drooping of unheld rope, FEM/IPC dynamics, rim
friction, settling, gripper geometry, robot reachability, Task success.
"""
import time

import numpy as np
import trimesh

from topogym.utils.geometry.passage import aperture_crossings
from topogym.utils.geometry.rope import catmull_rom_centerline, make_elastic_tube_mesh
from .geometry import (FixtureDistance, frozen_problem, geometric_crossings, task_like_evaluation,
                       world_rings)

TUBE_SEGMENTS = 12
# Inscribed 12-gon tube underestimates the true circular surface by r(1-cos(pi/12)).
TUBE_SURFACE_ERROR = 1.-np.cos(np.pi/TUBE_SEGMENTS)
FCL_DISTANCE_ERROR_M = 1e-6

DEFAULT_ROUTE = dict(approach_m=.06, exit_m=.06, lift="hook", hop_m=0., tip_overhang_m=.13,
                     smoothing_m=.002, control_alpha=.5, hook_forward_m=.10, hook_height_m=.24,
                     # Wang placement: after the last ring, turn the tail towards the right arm base.
                     tail_toward_xy=(0.333, -0.019))
DEFAULT_HANDS = dict(hand_radius_m=.02, hand_separation_m=.045, overlap_m=.0)


def default_relay(ring_count, hands=("A", "B")):
    """Poke-and-receive relay: the pusher holds 100 mm behind the tip and stops
    short of the ring plane; the receiver takes the tip on the exit side, pulls
    it further, then the next pusher regrasps 100 mm behind the tip."""
    plan = []
    for k in range(ring_count):
        pusher = hands[k % 2]
        plan.append(dict(ring=k, pusher=pusher, pusher_station_m=.10, poke_m=.05,
                         receiver=hands[(k+1) % 2], receiver_station_m=.02, pull_m=.12))
    return plan


class Track:
    def __init__(self, initial, tip_route):
        initial, tip_route = np.asarray(initial, float), np.asarray(tip_route, float)
        if np.linalg.norm(tip_route[0]-initial[-1]) > 1e-9:
            raise ValueError("Tip route must start at the initial tip")
        self.initial, self.tip_route = initial, tip_route
        self.points = np.vstack([initial, tip_route[1:]])
        self.tau = np.r_[0., np.cumsum(np.linalg.norm(np.diff(self.points, axis=0), axis=1))]
        self.rope_length = float(np.sum(np.linalg.norm(np.diff(initial, axis=0), axis=1)))
        self.tip_length = float(self.tau[-1]-self.rope_length)

    def at(self, tau):
        tau = np.clip(np.asarray(tau, float), 0., self.tau[-1])
        return np.column_stack([np.interp(tau, self.tau, self.points[:, i]) for i in range(3)])

    def tangent(self, tau, *, half_step=.004):
        """Unit direction of increasing material coordinate (towards the tip)."""
        a, b = self.at(np.asarray(tau)-half_step), self.at(np.asarray(tau)+half_step)
        d = b-a
        return d/np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-12)

    def rope(self, stations, sigma):
        return self.at(np.asarray(stations)+sigma)

    def tip_arc(self, sigma):
        """Track parameter of the tip after travel sigma."""
        return self.rope_length+sigma


def ordered_rings(problem):
    rings = {r["name"]: r for r in world_rings(problem)}
    return [(rings[name], sign) for name, sign in problem.required]


def build_tip_route(problem, route):
    """Control points then a smooth resampled route; both are returned."""
    p = dict(DEFAULT_ROUTE, **route)
    tip0 = problem.initial_m[-1]
    controls = [tip0]
    rings = ordered_rings(problem)
    first_center = np.asarray(rings[0][0]["center_m"])
    if p["lift"] == "vertical":
        controls.append(tip0+[0., 0., first_center[2]-tip0[2]-.03])
    elif p["lift"] == "hook":
        # Continue the rope's own end direction while rising, then turn back
        # towards the first ring on a wide arc: no hairpin at the lift-off.
        t_end = problem.initial_m[-1]-problem.initial_m[-2]
        t_end = t_end/np.linalg.norm(t_end)
        controls.append(tip0+.6*p["hook_forward_m"]*t_end+[0., 0., .4*p["hook_height_m"]])
        controls.append(tip0+p["hook_forward_m"]*t_end+[0., 0., p["hook_height_m"]])
    elif p["lift"] != "diagonal":
        raise ValueError("lift must be diagonal, vertical or hook")
    previous_exit = None
    for ring, sign in rings:
        c, n = np.asarray(ring["center_m"]), np.asarray(ring["normal"])
        t = sign*n/np.linalg.norm(n)
        entry, exit_ = c-p["approach_m"]*t, c+p["exit_m"]*t
        if previous_exit is not None and p["hop_m"] > 0:
            mid = (previous_exit+entry)/2
            controls.append(mid+[0., 0., p["hop_m"]])
        controls += [entry, c, exit_]
        previous_exit = exit_
    # Beyond the last ring the unheld tip hangs; model the route turning down.
    # tail_heading_xy (optional unit vector) turns the tail towards a side of
    # the table a receiving arm can reach, after a short straight run-out.
    last_ring, last_sign = rings[-1]
    t = last_sign*np.asarray(last_ring["normal"])
    horizontal = np.array([t[0], t[1], 0.]); horizontal /= max(np.linalg.norm(horizontal), 1e-9)
    heading = p.get("tail_heading_xy")
    toward = p.get("tail_toward_xy")
    if heading is None and toward is not None:
        # Turn the tail towards a world point (e.g. the receiving arm's base).
        heading = [float(toward[0])-previous_exit[0], float(toward[1])-previous_exit[1]]
    if heading is not None:
        heading = np.array([float(heading[0]), float(heading[1]), 0.]); heading /= max(np.linalg.norm(heading), 1e-9)
        runout = previous_exit+.06*t
        controls.append(runout)
        drop = runout+.15*heading+[0., 0., -.10]
    else:
        drop = previous_exit+.06*horizontal+[0., 0., -.10]
    controls.append(drop)
    bottom = np.array([drop[0], drop[1], problem.table_height_m+problem.rope_radius_m+.001])
    controls.append(bottom)
    controls = np.asarray(controls)
    dense = catmull_rom_centerline(controls, max_segment_length=p["smoothing_m"], alpha=p["control_alpha"])
    dense[0] = tip0
    return controls, dense, p


def plane_travel(track, ring, sign, rope_radius):
    """Tip travel at which the tip crosses this ring's aperture in the required sense."""
    c, n = np.asarray(ring["center_m"]), np.asarray(ring["normal"])
    hits, _ = aperture_crossings(track.tip_route, c, n, ring["radius_m"]-ring["tube_radius_m"]-rope_radius)
    hits = [h for h in hits if h["sign"] == sign]
    if len(hits) != 1:
        raise ValueError(f"Tip route must cross {ring['name']} exactly once in the required sense, found {len(hits)}")
    i = int(np.floor(hits[0]["material_coordinate"]))
    frac = hits[0]["material_coordinate"]-i
    arcs = np.r_[0., np.cumsum(np.linalg.norm(np.diff(track.tip_route, axis=0), axis=1))]
    return float(arcs[i]+frac*(arcs[min(i+1, len(arcs)-1)]-arcs[i]))


def relay_schedule(problem, track, plan, hands, sigma_final):
    """Turn a per-ring poke-and-receive plan into hand holds over tip travel.

    Each hold: one hand pinching one material station over a travel interval.
    A hand that must change its station releases and regrasps; when no other
    hand holds the rope meanwhile the regrasp is flagged as unheld.
    """
    rings = ordered_rings(problem)
    if len(plan) != len(rings):
        raise ValueError("Relay plan needs one entry per required ring")
    L, holds, events = track.rope_length, [], []
    sigma, holder = 0., None

    def grasp(hand, behind, start, role, ring_name, orientation=None):
        hold = dict(hand=hand, station_behind_tip_m=float(behind), station_m=L-float(behind),
                    sigma_start=float(start), sigma_end=None, role=role, ring=ring_name, unheld_regrasp=False,
                    orientation=[list(map(lambda v: v if isinstance(v, str) else float(v), row)) for row in orientation] if orientation else None)
        holds.append(hold)
        events.append(dict(kind="grasp", hand=hand, role=role, ring=ring_name, sigma=float(start),
                           station_behind_tip_m=float(behind),
                           position_m=track.rope([L-behind], start)[0].tolist()))
        return hold

    for k, ((ring, sign), entry) in enumerate(zip(rings, plan)):
        name, s_p = ring["name"], float(entry["pusher_station_m"])
        if holder is None or holder["hand"] != entry["pusher"] or abs(holder["station_behind_tip_m"]-s_p) > 1e-12:
            unheld = holder is not None and holder["hand"] == entry["pusher"]
            if holder is not None and unheld:
                holder["sigma_end"] = sigma
                events.append(dict(kind="release", hand=holder["hand"], sigma=sigma, reason="regrasp"))
            new = grasp(entry["pusher"], s_p, sigma, "pusher", name, entry.get("pusher_orientation"))
            new["unheld_regrasp"] = bool(unheld)
            if holder is not None and not unheld:
                holder["sigma_end"] = sigma+hands["overlap_m"]
                events.append(dict(kind="release", hand=holder["hand"], sigma=sigma+hands["overlap_m"], reason="handed_over"))
            holder = new
        crossing = plane_travel(track, ring, sign, problem.rope_radius_m)
        events.append(dict(kind="plane_crossing", ring=name, sign=int(sign), sigma=crossing))
        last = k == len(rings)-1
        poke = float(entry["poke_m"])
        handoff = crossing+poke
        if handoff <= sigma:
            raise ValueError(f"Ring {name}: poke handoff does not advance travel")
        events.append(dict(kind="poke", ring=name, sigma=handoff, tip_beyond_plane_m=poke,
                           pusher_beyond_plane_m=poke-s_p, pusher_position_m=track.rope([L-s_p], handoff)[0].tolist()))
        s_r = float(entry["receiver_station_m"])
        receiver = entry.get("receiver")
        if receiver == entry["pusher"]:
            raise ValueError("Receiver must be the other hand or null (solo)")
        if receiver is not None and abs(s_r-s_p) < hands["hand_separation_m"]:
            raise ValueError("Receiver and pusher stations are closer than the hand separation")
        pull = float(route_pull(entry, last, sigma_final-handoff))
        if receiver is None and abs(s_r-s_p) < 1e-9:
            events.append(dict(kind="keep_holding", hand=holder["hand"], sigma=handoff, ring=name))
        elif receiver is None:
            holder["sigma_end"] = handoff
            events.append(dict(kind="release", hand=holder["hand"], sigma=handoff, reason="solo_poke"))
            holder = grasp(entry["pusher"], s_r, handoff, "receiver", name, entry.get("receiver_orientation"))
            holder["unheld_regrasp"] = True
        else:
            new = grasp(receiver, s_r, handoff, "receiver", name, entry.get("receiver_orientation"))
            holder["sigma_end"] = handoff+hands["overlap_m"]
            events.append(dict(kind="release", hand=holder["hand"], sigma=handoff+hands["overlap_m"], reason="handed_over"))
            holder = new
        events.append(dict(kind="handoff", ring=name, sigma=handoff, receiver=holder["hand"],
                           receiver_beyond_plane_m=poke-s_r, receiver_position_m=track.rope([L-s_r], handoff)[0].tolist()))
        sigma = handoff+pull
        if sigma > sigma_final+1e-9:
            raise ValueError(f"Ring {name}: pull exceeds the final travel")
    holder["sigma_end"] = sigma_final
    events.append(dict(kind="release", hand=holder["hand"], sigma=sigma_final, reason="final",
                       position_m=track.rope([holder["station_m"]], sigma_final)[0].tolist()))
    for hold in holds:
        hold["sigma_end"] = float(hold["sigma_end"])
        if hold["sigma_end"] < hold["sigma_start"]-1e-12:
            raise ValueError("Hold ends before it starts")
    return holds, events


def route_pull(entry, last, remaining):
    return remaining if last else entry["pull_m"]


def _rope_gap(problem, checker, track, sigma):
    points = track.rope(problem.stations_m, sigma)
    vertices, faces = make_elastic_tube_mesh(points, radius=problem.rope_radius_m, radial_segments=TUBE_SEGMENTS)
    gap = checker.tube(vertices, faces)
    table = float(points[:, 2].min()-problem.rope_radius_m-problem.table_height_m)
    return points, gap, table


def certify(problem, track, holds, *, sigma_final, margin_m=.001, hand_margin_m=.003,
            hand_radius_m=.02, step_m=.002, max_depth=6, progress=None):
    """Adaptive interval certificate over tip travel; fails closed."""
    checker = FixtureDistance(trimesh.util.concatenate([problem.fixtures, *problem.risers]))
    tube_error = problem.rope_radius_m*TUBE_SURFACE_ERROR+FCL_DISTANCE_ERROR_M
    expected = problem.required
    samples = {}

    def sample(sigma):
        sigma = round(float(sigma), 9)
        if sigma in samples:
            return samples[sigma]
        points, gap, table = _rope_gap(problem, checker, track, sigma)
        sequence = [(h["ring"], h["sign"]) for h in geometric_crossings(points, problem)]
        hands = {}
        for hold in holds:
            if hold["sigma_start"]-1e-9 <= sigma <= hold["sigma_end"]+1e-9:
                center = track.rope([hold["station_m"]], sigma)[0]
                hands[hold["hand"]] = (center, checker.sphere(center, hand_radius_m))
        samples[sigma] = dict(sigma=sigma, gap=gap, table=table, sequence=sequence, hands=hands)
        return samples[sigma]

    grid = list(np.arange(0., sigma_final, step_m))+[sigma_final]
    for hold in holds:
        grid += [hold["sigma_start"], hold["sigma_end"]]
    grid = sorted({round(float(g), 9) for g in grid if 0. <= g <= sigma_final+1e-12})
    failures, bounds, hand_bounds, progress_sequence = [], [], [], []
    minimum_gap, minimum_table, minimum_hand = float("inf"), float("inf"), float("inf")
    previous_length = 0
    stack = [(grid[i], grid[i+1], 0) for i in range(len(grid)-1)][::-1]
    checked = 0
    while stack and not failures:
        lo, hi, depth = stack.pop()
        a, b = sample(lo), sample(hi)
        for row in (a, b):
            if row["gap"] <= margin_m+tube_error:
                failures.append(dict(reason="rope_fixture_clearance", sigma=row["sigma"], gap_m=row["gap"]))
            if row["table"] < -1e-6:
                failures.append(dict(reason="rope_below_table", sigma=row["sigma"], depth_m=row["table"]))
            if row["sequence"] != expected[:len(row["sequence"])]:
                failures.append(dict(reason="crossing_sequence_not_prefix", sigma=row["sigma"], sequence=row["sequence"]))
            for hand, (center, gap) in row["hands"].items():
                if gap <= hand_margin_m+FCL_DISTANCE_ERROR_M:
                    failures.append(dict(reason="hand_fixture_clearance", hand=hand, sigma=row["sigma"], gap_m=gap))
            if len(row["hands"]) == 2:
                (c1, _), (c2, _) = row["hands"].values()
                if np.linalg.norm(c1-c2) < 2*hand_radius_m+hand_margin_m:
                    failures.append(dict(reason="hands_overlap", sigma=row["sigma"], distance_m=float(np.linalg.norm(c1-c2))))
        if failures:
            break
        half = (hi-lo)/2
        lower = min(a["gap"], b["gap"])-half-tube_error
        hand_lower = min([g for _, g in a["hands"].values()]+[g for _, g in b["hands"].values()], default=float("inf"))-half-FCL_DISTANCE_ERROR_M
        if len(b["sequence"]) < len(a["sequence"]):
            failures.append(dict(reason="crossing_retreat", sigma=b["sigma"], sequence=b["sequence"]))
            break
        if lower > margin_m and hand_lower > hand_margin_m:
            checked += 1
            bounds.append((lo, hi, lower))
            hand_bounds.append(hand_lower)
            minimum_gap, minimum_hand = min(minimum_gap, lower), min(minimum_hand, hand_lower)
            minimum_table = min(minimum_table, a["table"], b["table"])
            if len(b["sequence"]) > previous_length:
                progress_sequence.append(dict(sigma_between=[lo, hi], sequence=b["sequence"]))
                previous_length = len(b["sequence"])
        elif depth >= max_depth:
            failures.append(dict(reason="subdivision_budget_exhausted", sigma_between=[lo, hi],
                                 rope_lower_bound_m=lower, hand_lower_bound_m=hand_lower))
        else:
            mid = round((lo+hi)/2, 9)
            stack += [(mid, hi, depth+1), (lo, mid, depth+1)]
        if progress and checked % 200 == 0:
            progress(lo, sigma_final, minimum_gap)
    final = sample(sigma_final)
    final_points = track.rope(problem.stations_m, sigma_final)
    evaluation = task_like_evaluation(final_points, problem)
    passed = not failures and evaluation["sequence_matches"]
    return dict(passed=bool(passed), failures=failures, intervals_checked=len(bounds),
                samples=len(samples), fcl_queries=checker.queries,
                requested_margin_m=margin_m, requested_hand_margin_m=hand_margin_m, hand_radius_m=hand_radius_m,
                tube_surface_error_m=float(problem.rope_radius_m*TUBE_SURFACE_ERROR),
                distance_error_m=FCL_DISTANCE_ERROR_M, travel_step_m=step_m,
                rope_clearance_lower_bound_m=None if not bounds else float(minimum_gap),
                hand_clearance_lower_bound_m=None if not np.isfinite(minimum_hand) else float(minimum_hand),
                table_gap_minimum_m=None if not np.isfinite(minimum_table) else float(minimum_table),
                crossing_progress=progress_sequence, final_geometric_sequence=final["sequence"],
                final_task_like_evaluation=evaluation, final_points_m=final_points.tolist(),
                interval_lower_bounds=[dict(sigma_from=lo, sigma_to=hi, rope_m=v) for lo, hi, v in bounds[::max(1, len(bounds)//400)]],
                coverage="rope tube vs rings/stands/bases; table by height; hands as spheres; linear track interpolation")


def material_budget(problem, track, sigma_final):
    L = track.rope_length
    final = track.rope(problem.stations_m, sigma_final)
    hits = geometric_crossings(final, problem)
    stations = problem.stations_m
    def station_arc(coordinate):
        i = int(np.floor(coordinate)); f = coordinate-i
        return float(stations[i]+f*(stations[min(i+1, len(stations)-1)]-stations[i]))
    arcs = [station_arc(h["material_coordinate"]) for h in hits]
    tail = final[0]
    return dict(rope_length_m=L, tip_route_length_m=track.tip_length, final_travel_m=sigma_final,
                tail_left_initial_curve=bool(sigma_final > L),
                tail_height_above_table_m=float(tail[2]-problem.rope_radius_m-problem.table_height_m),
                tail_side_length_before_first_crossing_m=None if not arcs else float(arcs[0]),
                tip_side_length_after_last_crossing_m=None if not arcs else float(L-arcs[-1]),
                crossing_material_arcs_m=arcs,
                note="Static balance of the hanging ends after release is not certified; rim friction and sag unmodelled")


def plan_object_path(output, *, variation="medium", seed=0, route=None, relay=None, hands=None,
                     margin_m=.001, hand_margin_m=.003, step_m=.002, progress=None):
    started = time.monotonic()
    problem = frozen_problem(output, variation=variation, seed=seed)
    hands = dict(DEFAULT_HANDS, **(hands or {}))
    rings = ordered_rings(problem)
    from .profiles import candidate_plans
    relay = candidate_plans(problem.variation)[0][1] if relay is None else relay
    controls, dense, route_used = build_tip_route(problem, route or {})
    track = Track(problem.initial_m, dense)
    report = dict(schema_version=1, scope="finite-instance object-only constructive witness (follow-the-leader)",
                  **problem.identity, status="planning", accepted_proof=False, robot_ik_verified=False,
                  robot_execution_verified=False, task_success=False,
                  model=dict(kind="follow_the_leader", track="initial centerline then smoothed tip route",
                             hands="clearance spheres on material stations", interpolation="linear along track"),
                  route=dict(parameters=route_used, control_points_m=controls.tolist(), dense_points=len(dense),
                             tip_route_length_m=track.tip_length),
                  relay=dict(parameters=hands, plan=relay))
    try:
        last_ring, last_sign = rings[-1]
        last_crossing = plane_travel(track, last_ring, last_sign, problem.rope_radius_m)
        sigma_final = last_crossing+route_used["tip_overhang_m"]
        if sigma_final > track.tip_length:
            raise ValueError("Tip route too short for the requested overhang")
        holds, events = relay_schedule(problem, track, relay, hands, sigma_final)
        report["schedule"] = dict(sigma_final=sigma_final, holds=holds, events=events)
        certificate = certify(problem, track, holds, sigma_final=sigma_final, margin_m=margin_m,
                              hand_margin_m=hand_margin_m, hand_radius_m=hands["hand_radius_m"], step_m=step_m,
                              progress=progress)
        report["certificate"] = certificate
        report["material_budget"] = material_budget(problem, track, sigma_final)
        report["status"] = "object_witness_verified" if certificate["passed"] else "object_witness_rejected"
    except ValueError as error:
        report.update(status="object_witness_rejected", error=str(error))
    report["limitations"] = [
        "Rope follows the track exactly: no gravity sag, no droop of the free tip, no rim friction or slip",
        "Hands are spheres on material stations; real gripper meshes, arm sides and IK belong to the next stage",
        "Numerical FCL distances assume the stated error budget; the tube is a 12-gon with its surface error added",
        "No FEM/IPC dynamics, settling, velocity or Task success qualification",
    ]
    report["wall_time_s"] = time.monotonic()-started
    return report, problem, track


def audit_object_path(witness, output, *, progress=None):
    """Rebuild the task geometry and replay the witness route; ignore stored flags."""
    problem = frozen_problem(output, variation=witness["variation_id"], seed=witness["seed"])
    from topogym.utils.io import to_jsonable
    identity = ("task_id", "variation_id", "model_revision", "terminal_revision", "instance_id",
                "asset_sha256", "required_crossings", "rings", "rope_radius_m", "rope_stations", "table_height_m", "robot_scene")
    mismatched = [k for k in identity if to_jsonable(witness.get(k)) != to_jsonable(problem.identity[k])]
    if mismatched:
        raise ValueError(f"Witness identity differs from the rebuilt task/geometry: {mismatched}")
    route = witness["route"]["parameters"]
    controls, dense, route_used = build_tip_route(problem, route)
    if np.abs(np.asarray(witness["route"]["control_points_m"])-controls).max() > 1e-9:
        raise ValueError("Witness control points do not follow from its route parameters")
    track = Track(problem.initial_m, dense)
    hands = witness["relay"]["parameters"]
    sigma_final = float(witness["schedule"]["sigma_final"])
    holds, events = relay_schedule(problem, track, witness["relay"]["plan"], hands, sigma_final)
    certificate = witness["certificate"]
    result = certify(problem, track, holds, sigma_final=sigma_final,
                     margin_m=float(certificate["requested_margin_m"]),
                     hand_margin_m=float(certificate["requested_hand_margin_m"]),
                     hand_radius_m=float(hands["hand_radius_m"]), step_m=float(certificate["travel_step_m"]),
                     progress=progress)
    same_final = result["final_geometric_sequence"] == [tuple(x) for x in certificate["final_geometric_sequence"]]
    passed = result["passed"] and same_final and result["final_task_like_evaluation"]["sequence_matches"]
    return dict(status="object_witness_verified" if passed else "object_witness_rejected", passed=bool(passed),
                identity_matched=True, final_sequence_matches_witness=bool(same_final),
                certificate=dict(result, final_points_m=None), material_budget=material_budget(problem, track, sigma_final),
                accepted_robot_proof=False, task_success=False)
