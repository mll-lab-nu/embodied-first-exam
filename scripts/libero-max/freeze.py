"""Freeze one LIBERO-MAX case and record its reference solution (trusted authoring step; runs in the eai-libero-max
image, one process per case, see freeze.sh).

    python freeze.py <cases.json> <case_id> <out_dir>

1. Build the case with LIBERO-MAX's own code (lmx_tool.build) and freeze it: the case's parameters plus the hash of
   the simulator state the agent starts from (after LIBERO's 10 warm-up steps).
2. Check it: LIBERO's success check does not hold at the start.
3. Record the reference: a scripted controller with privileged state (reference.py, authoring only) that re-reads every
   object's pose each control step, so it follows an object the event moves.
4. Verify it: two replays, each in a fresh process, reach the live final state (same hash) and succeed.
Writes <out_dir>/instance.json, oracle.npy and report.json.
"""

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "shared"))
sys.path.insert(0, str(HERE))
import lmx_tool  # noqa: E402
import reference  # noqa: E402


def main(cases_path: str, case_id: str, out: str) -> None:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    case = next(c for c in json.loads(Path(cases_path).read_text())["cases"] if c["case_id"] == case_id)
    inst = {"schema": lmx_tool.INSTANCE_SCHEMA, "case": case, "instance_sha": lmx_tool.sha(case)}
    s = lmx_tool.Session(inst, check=False)
    inst["initial_state_sha"] = s.initial_state_sha
    rec = {"case_id": case_id, "event": case["scenario"]["change_type"], "suite": case["task_suite_name"],
           "language": s.instruction, "goal": s.goal(), "initial_success": s.check(),
           "initial_state_sha": s.initial_state_sha, "robot_base": s.robot_base(), "controller": s.controller()}  # fmt: skip
    (out / "instance.json").write_text(json.dumps(inst, indent=1, sort_keys=True) + "\n")
    if rec["initial_success"]:
        rec["ok"], rec["why"] = False, "solved at the start"
    else:
        try:
            plan = reference.run(s)
            rec.update(plan=plan, live=s.result())
        except reference.Unsupported as exc:
            rec.update(ok=False, why=f"no scripted reference: {exc}")
    if "live" in rec:
        live = rec["live"]
        if not live["success"]:
            rec.update(ok=False, why=f"reference failed ({rec['plan'].get('phase')}, {live['control_steps']} steps)")
        else:
            np.save(out / "oracle.npy", np.asarray(s.actions, dtype=np.float64))
            reps = []
            for _ in range(2):
                p = subprocess.run(
                    [sys.executable, "-c", REPLAY, str(out / "instance.json"), str(out / "oracle.npy")],
                    check=True,
                    capture_output=True,
                    text=True,
                    cwd=str(HERE / "shared"),
                )
                reps.append(json.loads(p.stdout.strip().splitlines()[-1]))
            rec["replays"] = reps
            same = all(r["state_sha"] == live["state_sha"] and r["success"] for r in reps)
            rec.update(ok=same, why="" if same else "fresh-process replay differs or fails")
    (out / "report.json").write_text(json.dumps(rec, indent=1, default=lambda o: np.asarray(o).tolist()) + "\n")
    print(json.dumps({k: rec.get(k) for k in ("case_id", "event", "suite", "ok", "why")}))


REPLAY = """
import json, sys
import numpy as np
import lmx_tool
s = lmx_tool.Session(sys.argv[1])
print(json.dumps(s.replay(np.load(sys.argv[2]))))
"""

if __name__ == "__main__":
    main(*sys.argv[1:4])
