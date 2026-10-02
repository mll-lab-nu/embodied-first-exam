#!/usr/bin/env python3
"""Check blanket_flatten's coverage skip (image 0.2.8) against the full per-tick evaluation it replaced, on the GPU.

    python scripts/check_blanket_coverage_skip.py <instance.json> <trajectory.npz> [--rows 120] [--out report.json]

Replays the trajectory's first rows in one Session; at every physics tick the task's evaluate_state (with the skip) and the
previous full evaluation (coverage at every tick) run on the same state. Pass: the goal decision identical at every tick,
the coverage and gates identical whenever the skip computed them, and every control step's reported metrics complete.
Reports the time of both evaluations. Run inside the TopoGym image with the task tooling importable."""
import argparse, json, sys, time
import numpy as np
from rcb_topogym import Session


def full(task, state):
    """BlanketFlattenTask.evaluate_state before the skip (dev/jianwen 4e8f2bdbd)."""
    from topogym.evaluation.cloth_metrics import footprint_area
    p = state["particles"]["blanket"]; positions = np.asarray(p["position_m"]); velocity = np.asarray(p["velocity_m_s"])
    if not np.isfinite(positions).all() or not np.isfinite(velocity).all():
        return False, "Non-finite cloth particle state", {}
    heights = positions[:, 2] - task.table_height_m
    if heights.min() < -0.1:
        return False, "Cloth fell below the table", {}
    cfg = task.config
    coverage = footprint_area(positions, task.particle_faces) / (task.layout.length_m * task.layout.width_m)
    stretch = np.linalg.norm(positions[task.particle_edges[:, 1]] - positions[task.particle_edges[:, 0]], axis=1) / task.rest_lengths
    speed = float(np.linalg.norm(velocity, axis=1).max())
    gates = dict(covered=coverage >= cfg["minimum_coverage_ratio"], flat=float(heights.max()) <= cfg["maximum_height_m"],
                 above_table=float(heights.min()) >= -task.layout.particle_size_m,
                 material_intact=float(stretch.max()) <= cfg["maximum_stretch_ratio"], settled=speed <= cfg["maximum_speed_m_s"])
    return all(gates.values()), None, dict(gates=gates, coverage_ratio=float(coverage))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("instance"); ap.add_argument("trajectory"); ap.add_argument("--rows", type=int, default=120); ap.add_argument("--out")
    a = ap.parse_args()
    s = Session("blanket_flatten", instance=a.instance, strict=True)
    task = s.env._task; new_eval = task.evaluate_state
    log = dict(ticks=0, step_ticks=0, computed=0, diffs=[], new_s=0.0, old_s=0.0, reached_ticks=0)

    def compared(state):
        t = time.perf_counter(); r_new = new_eval(state); t1 = time.perf_counter(); r_old = full(task, state); t2 = time.perf_counter()
        log["new_s"] += t1 - t; log["old_s"] += t2 - t1; log["ticks"] += 1; log["reached_ticks"] += bool(r_old[0])
        last = getattr(task, "complete_metrics", True)
        log["step_ticks"] += bool(last)
        if r_new[0] != r_old[0] or r_new[1] != r_old[1]:
            log["diffs"].append(f"tick {log['ticks']}: decision {r_new[:2]} != {r_old[:2]}")
        cov = (r_new[2] or {}).get("coverage_ratio")
        if cov is not None:
            log["computed"] += 1
            if cov != r_old[2].get("coverage_ratio") or r_new[2]["gates"] != r_old[2]["gates"]:
                log["diffs"].append(f"tick {log['ticks']}: metrics {r_new[2].get('gates')} {cov} != {r_old[2].get('gates')} {r_old[2].get('coverage_ratio')}")
        elif last and r_old[2]:
            log["diffs"].append(f"tick {log['ticks']}: a control step's last tick lacks its coverage")
        return r_new

    task.evaluate_state = compared
    acts = np.asarray(np.load(a.trajectory)["actions"], dtype=np.float32)[: a.rows]
    t0 = time.time()
    for row in acts:
        s.step(row)
        if s.status()["episode_end"] is not None:
            break
    report = dict(rows=len(acts), ticks=log["ticks"], step_last_ticks=log["step_ticks"], coverage_computed=log["computed"],
                  goal_true_ticks=log["reached_ticks"], identical=not log["diffs"], diffs=log["diffs"][:20],
                  evaluate_new_s_per_tick=round(log["new_s"] / max(log["ticks"], 1), 5),
                  evaluate_old_s_per_tick=round(log["old_s"] / max(log["ticks"], 1), 5), wall_s=round(time.time() - t0, 1),
                  episode_end=s.status()["episode_end"])
    print(json.dumps(report), flush=True)
    if a.out:
        open(a.out, "w").write(json.dumps(report, indent=1) + "\n")
    s.close()
    return 0 if report["identical"] and report["ticks"] else 1


if __name__ == "__main__":
    sys.exit(main())
