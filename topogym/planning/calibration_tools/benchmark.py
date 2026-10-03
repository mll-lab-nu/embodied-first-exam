"""Bounded IPC hold benchmark using the same development owner and profiler.

Run as a module, e.g. --task slotted_post_ring --variation easy --output <new dir>.
Keeps task/solver parameters unchanged. This is a baseline, not a loaded grasp test.
"""
import argparse
import json
from pathlib import Path
import statistics
import time


class HoldPolicy:
    def __init__(self, steps):
        self.remaining = steps

    def act(self, observation):
        if self.remaining == 0:
            return None
        self.remaining -= 1
        return {}


def make_policy(steps):
    return HoldPolicy(steps)


def completed_spans(path):
    active, completed = {}, []
    with Path(path).open() as stream:
        for line in stream:
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                break
            row = message["span"]
            if message["kind"] == "span_begin":
                parent = active.get(row["parent_id"])
                active[row["span_id"]] = dict(row, child_s=0.,
                    ancestors=[] if parent is None else parent["ancestors"]+[parent["span_id"]])
            else:
                opened = active.pop(row["span_id"])
                duration = row["ended"]-opened["started"]
                if opened["parent_id"] in active:
                    active[opened["parent_id"]]["child_s"] += duration
                completed.append(dict(opened, seconds=duration,
                    self_seconds=max(0., duration-opened["child_s"]), failed=row["failed"]))
    return completed


def summarize(path, operation_id, warmup_steps):
    spans = [row for row in completed_spans(path) if row.get("operation_id") == operation_id]
    steps = []
    for row in sorted((s for s in spans if s["stage"] == "control_step"), key=lambda s: s["span_id"]):
        costs = {}
        for child in spans:
            if child["span_id"] == row["span_id"] or row["span_id"] in child["ancestors"]:
                cost = costs.setdefault(child["stage"], dict(calls=0, seconds=0., self_seconds=0.))
                cost["calls"] += 1
                cost["seconds"] += child["seconds"]
                cost["self_seconds"] += child["self_seconds"]
        steps.append(dict(index=len(steps), seconds=row["seconds"], failed=row["failed"], costs=costs))
    measured = [row for row in steps[warmup_steps:] if not row["failed"]]
    return dict(control_steps=steps, warmup_steps=warmup_steps,
                measured_steps=len(measured),
                median_control_step_s=statistics.median(r["seconds"] for r in measured) if measured else None,
                min_control_step_s=min((r["seconds"] for r in measured), default=None),
                max_control_step_s=max((r["seconds"] for r in measured), default=None),
                mean_self_s_by_stage={stage: sum(r["costs"].get(stage, {}).get("self_seconds", 0.) for r in measured)/len(measured)
                    for stage in sorted({stage for r in measured for stage in r["costs"]})} if measured else {})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", choices=("slotted_post_ring", "rope_threading", "knot_untying", "orbits"), required=True)
    parser.add_argument("--variation", default="easy")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--steps", type=int, default=5)
    parser.add_argument("--warmup-steps", type=int, default=1)
    parser.add_argument("--no-rgb", action="store_true")
    parser.add_argument("--startup-s", type=float, default=600.)
    parser.add_argument("--physics-step-s", type=float, default=120.)
    parser.add_argument("--policy-s", type=float, default=600.)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.steps < 1 or args.warmup_steps < 0 or args.steps+args.warmup_steps > 100:
        parser.error("Use 1..100 total control steps")
    from .api import open_session
    from topogym.utils.io import write_json_atomic
    config = dict(task_id=args.task, variation_id=args.variation, seed=args.seed,
                  compute_backend="cuda", enable_rgb=not args.no_rgb, control_mode="JOINT_ABS",
                  history_storage="segment", physics_dt_s=.0025, control_decimation=10, solver_substeps=4)
    report = dict(config=config, status="running", scope="initial home/hold baseline; no grasp, squeeze, or task success qualification",
                  timing_units=dict(control_dt_s=.025, world_tick_dt_s=.0025, ipc_substep_dt_s=.000625,
                                    world_ticks_per_control=10, native_substeps_per_control=40),
                  frames=[], full_oracle_success=False, hardware_contention="inspect external GPU resource log")
    dev = None
    op = "hold-benchmark"
    started = time.monotonic()
    try:
        dev = open_session(config, args.output, budgets=dict(startup_s=args.startup_s,
            operation_s=180., render_s=180., policy_s=args.policy_s, physics_step_s=args.physics_step_s))
        report["session_startup_wall_s"] = time.monotonic()-started
        report["capabilities"] = dev.capabilities()
        if not args.no_rgb:
            report["frames"].append(dev.capture_frame("cam_high", record_video=True))
        dev.watch(["tracking_error", "contact_changed"], before_steps=3, after_steps=2)
        count = args.steps+args.warmup_steps
        token = dev.run_policy(dict(path=str(Path(__file__).resolve()), factory="make_policy", kwargs=dict(steps=count)),
                               request_id=op, max_control_steps=count+1)
        while dev.status(token)["status"] == "running":
            try:
                dev.wait(token, timeout_s=10.)
            except TimeoutError:
                progress = dev.status()["progress"]
                print(json.dumps(dict(stage=progress.get("stage"), physics_step=progress.get("physics_step"),
                                      active_spans=[dict(stage=s["stage"], elapsed_s=s["elapsed_s"]) for s in progress.get("active_spans", [])])), flush=True)
        report["result"] = dev.wait(token)
        if not args.no_rgb:
            report["frames"].append(dev.capture_frame("cam_high", record_video=True))
        report.update(summarize(args.output/"profile.jsonl", op, args.warmup_steps))
        report["timings"] = dev.timings()
        report["status"] = "passed" if report["measured_steps"] == args.steps else "incomplete"
    except BaseException as error:
        report.update(status="failed", error=f"{type(error).__name__}: {error}")
        if (args.output/"profile.jsonl").exists():
            report.update(summarize(args.output/"profile.jsonl", op, args.warmup_steps))
        raise
    finally:
        if dev is not None:
            dev.close()
        if args.output.exists():
            report["total_wall_s"] = time.monotonic()-started
            write_json_atomic(args.output/"benchmark.json", report)
            print(json.dumps(dict(status=report["status"], output=str(args.output), median_control_step_s=report.get("median_control_step_s"))), flush=True)


if __name__ == "__main__":
    main()
