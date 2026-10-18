"""Operator reference validation; writes evidence outside the source tree."""

import argparse
import hashlib
import importlib.metadata
import sys
from http.server import HTTPServer
import json
from pathlib import Path
import threading
from .reference.iterate import run
from .public.policy import DEFAULT
from .public.model import AIRFRAME, TASK_VERSION
from .trusted.grade import grade
from .trusted.session import Session
from .trusted.server import handler
from .trusted.simulation import rollout


def validate(out, residual, render=True, oracle_workers=4):
    out.mkdir(parents=True, exist_ok=False)
    bank = {
        "adaptation": [{"seed": x, "scale": 1.0} for x in (71, 72, 73)],
        "held_out": [{"seed": x, "scale": 1.0} for x in (101, 102, 103, 104, 105, 106)],
    }
    session = Session(out / "session", residual, bank=bank, render=render, oracle_workers=oracle_workers)
    rows = []
    for name in ("nominal", "baseline", "oracle"):
        for i, seed in enumerate((71, 72, 73)):
            policy = DEFAULT
            if name == "oracle":
                policy = json.loads((out / "session/oracle" / f"adaptation-{i}/policy.json").read_text())
            _, record = rollout(
                policy,
                residual_path=None if name == "nominal" else residual,
                seed=seed,
                oracle=name == "oracle",
                reference_time_s=None
                if name == "nominal"
                else session.oracle_references["adaptation"][i]["oracle_time_s"],
                out=out / f"{name}-{seed}",
                render=render and seed == 71,
            )
            rows.append({"controller": name, "seed": seed, **record["metrics"]})
            print(name, seed, record["metrics"]["success"], flush=True)
    server = HTTPServer(("127.0.0.1", 0), handler(session))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        # The reference learner only calls HTTP and receives the same payload available to a coding agent.
        submission = run(out / "learner", f"http://127.0.0.1:{server.server_port}")
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    for entry in session.state["rounds"]:
        for i in range(3):
            r = json.loads((out / "session" / entry["id"] / f"case-{i}" / "record.json").read_text())
            rows.append({"controller": entry["id"], "case": i, **r["metrics"]})
    report = grade(out / "session", residual, render=render)
    manifest = {
        "kind": "scripted_reference_validation",
        "task_version": TASK_VERSION,
        "airframe": AIRFRAME,
        "model_evaluations": 0,
        "oracle_bank_sha256": session.state["oracle_bank_sha256"],
        "runtime": {
            "python": sys.version.split()[0],
            **{n: importlib.metadata.version(n) for n in ("mujoco", "numpy", "Pillow", "scipy")},
        },
        "source_sha256": {
            str(p.relative_to(Path(__file__).parent)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(__file__).parent.rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts
        },
        "residual_family": "full author model: z, world velocity, quaternion xyzw, normalized actual RPM -> world force xyz",
        "rounds": 3,
        "adaptation_cases_per_round": 3,
        "held_out_cases": 6,
        "submission": submission,
        "runs": rows,
        "held_out": report,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps({"output": str(out), "held_out_successes": report["successes"], "cases": 6}), flush=True)
    return manifest


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--residual", type=Path, required=True)
    p.add_argument("--no-video", action="store_true")
    p.add_argument("--oracle-workers", type=int, default=4)
    a = p.parse_args()
    validate(a.out, a.residual, not a.no_video, a.oracle_workers)
