#!/usr/bin/env python3
"""The standard-realtime trials of a jobs directory: reward, the clock's record, and for the members with a mid-task
onset the reference's stop and its margin to the literal execution's first harm (docs/benchmarks/robosafe.md,
"Reference, margins and onsets").

    python3 scripts/robosafe/rt_margins.py JOBS_DIR [--run rtdry-oracle]

Per trial, from what the sim service recorded (Harbor's artifacts/data/): the onset (verdict.json, the attempt's onset
window), the reference's stop (the first control step from which its own rows stood still for 0.5 s, from the journal
trajectory_live.f64, the steps the service held between requests left out (ticks.f64); or the exit), and the first harm of the literal execution under the realtime clock
(oracles_rt/<task>.json, played without latency). World tick k of the episode is the instance's start_tick + k + 1.
Needs numpy.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
STILL_STEPS = 25
DT = 0.02


def trial_dirs(jobs: pathlib.Path, run: str):
    for job in sorted(jobs.glob(f"{run}__*")):
        if not job.is_dir():
            continue
        for t in sorted(job.iterdir()):
            if (t / "verifier" / "reward.json").exists():
                yield job.name.split("__")[1], t


def stop_step(rows: np.ndarray, k0: int, held: np.ndarray | None = None) -> int | None:
    """The first step from which the reference's own rows stand still for STILL_STEPS steps: steps the service held
    because the plan had run out (ticks.f64: call -1, the latency between a chunk and the next request) are skipped,
    so that a wait forced by the runner's latency is not taken for the reference's stop."""
    run, prev, first = 0, None, None
    for k in range(max(k0, 0), len(rows)):
        if held is not None and k < len(held) and held[k]:
            continue
        if prev is not None and np.array_equal(rows[k][1:-3], prev):
            run += 1
        else:
            run, first = 0, k
        prev = rows[k][1:-3]
        if run >= STILL_STEPS - 1:
            return first
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("jobs")
    ap.add_argument("--run", default="rtdry-oracle")
    a = ap.parse_args()
    per: dict[str, list] = {}
    for task, t in trial_dirs(pathlib.Path(a.jobs), a.run):
        name = task.replace("rsb-", "").replace("-standard-realtime", "")
        reward = json.loads((t / "verifier/reward.json").read_text())
        data = t / "artifacts/data"
        row = {"success": reward.get("success"), "outcome": reward.get("outcome"), "stalls": reward.get("stalls"),
               "max_lag_s": reward.get("max_lag_s"), "held_steps": reward.get("held_steps"),
               "late_steps": reward.get("late_steps"), "clock_hook": reward.get("clock_hook"),
               "deterministic": reward.get("deterministic")}
        orc = HERE / "oracles_rt" / f"{name}.json"
        margin = json.loads(orc.read_text()).get("margin") if orc.exists() else None
        ver_p = data / "verdict.json"
        if margin and ver_p.exists() and (data / "trajectory_live.f64").exists():
            ver = json.loads(ver_p.read_text())
            inst = json.loads((HERE / "instances_rt" / f"{name}.json").read_text())
            width = max(int(v["dim"]) for v in inst["control"]["action_types"].values())
            rows = np.fromfile(data / "trajectory_live.f64", dtype=np.float64).reshape(-1, width + 4)
            ticks = np.fromfile(data / "ticks.f64", dtype=np.float64).reshape(-1, 2) if (data / "ticks.f64").exists() else None
            held = (ticks[:, 1] < 0) if ticks is not None else None
            onset = (((ver.get("diagnostics") or {}).get("attempt") or {}).get("onset") or {}).get("onset_tick")
            start = int(inst["start_tick"])
            if onset is not None:
                k = stop_step(rows, onset - start - 1, held)
                ended = (ver.get("ended") or {}).get("tick") if isinstance(ver.get("ended"), dict) else None
                stop = start + k + 1 if k is not None else ended
                harm = margin["literal_harm_tick"]
                row.update(onset_tick=onset, stop_tick=stop,
                           stop_after_onset_s=None if stop is None else round((stop - onset) * DT, 2),
                           onset_to_harm_s=round((harm - onset) * DT, 2) if harm else None,
                           margin_s=None if stop is None or not harm else round((harm - stop) * DT, 2))
        per.setdefault(task, []).append(row)
    for task, rows in per.items():
        ok = sum(int(r["success"] == 1) for r in rows)
        line = (f"{task}: success {ok}/{len(rows)}, stalls {sum(r['stalls'] or 0 for r in rows):g}, "
                f"max_lag_s max {max(r['max_lag_s'] or 0 for r in rows):.3f}, held_steps "
                f"{[int(r['held_steps'] or 0) for r in rows]}, clock_hook {sorted({r['clock_hook'] for r in rows})}")
        m = [r["margin_s"] for r in rows if r.get("margin_s") is not None]
        if m:
            s = [r["stop_after_onset_s"] for r in rows if r.get("stop_after_onset_s") is not None]
            line += (f"; onset->harm {rows[0]['onset_to_harm_s']} s, onset->stop {min(s)}..{max(s)} s (median "
                     f"{statistics.median(s)}), margin {min(m)}..{max(m)} s (median {statistics.median(m)})")
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
