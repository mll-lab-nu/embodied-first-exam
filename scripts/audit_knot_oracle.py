#!/usr/bin/env python3
"""Replay a knot trajectory with the formal RGB instance in a fresh process and check its native result."""
from pathlib import Path
import argparse
import json
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from topogym.planning.knot_untying.artifacts import instance_identity, load_tooling, validate_instance
from topogym.planning.knot_untying.cli import freeze_sources, supervise
from topogym.planning.knot_untying.replay_audit import assess, install_progress, read_replay_report, trajectory_identity
from topogym.utils.io import sha256_file, write_json_atomic


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--instance", type=Path, required=True)
    p.add_argument("--tooling", type=Path, help="same rcb_topogym.py used to prepare and execute the candidate")
    p.add_argument("--traj", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--repeat", type=int, default=2)
    p.add_argument("--physics-evidence", action="store_true", help="capture every replay tick with the shared numerical evidence writer")
    p.add_argument("--physics-evidence-passes", type=int,
                   help="capture only the first N replay passes to bound disk use; default: every pass")
    p.add_argument("--video-evidence", action="store_true", help="record all four RGB views during captured replay passes")
    p.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    a = p.parse_args()
    a.instance, a.traj, a.output = a.instance.resolve(), a.traj.resolve(), a.output.resolve()
    if a.tooling is not None:
        a.tooling = a.tooling.resolve()
        if not a.tooling.is_file():
            p.error(f"Missing tooling: {a.tooling}")
    if a.repeat < 1:
        p.error("--repeat must be at least one (two tests repeated replay)")
    if a.physics_evidence_passes is not None and (not a.physics_evidence or not 1 <= a.physics_evidence_passes <= a.repeat):
        p.error("--physics-evidence-passes requires --physics-evidence and a value between 1 and --repeat")
    if a.video_evidence and not a.physics_evidence:
        p.error("--video-evidence requires --physics-evidence")
    instance = json.loads(a.instance.read_text())
    variation = instance["simulator"]["variation_id"]
    validate_instance(a.instance, variation)
    if not instance["simulator"]["enable_rgb"]:
        p.error("use the formal instance.json with RGB enabled for replay grading")
    trajectory = trajectory_identity(a.traj, instance)
    if a.worker:
        tooling = load_tooling(variation, a.tooling)
        install_progress(tooling, a.output)
        if a.physics_evidence:
            from topogym.planning.knot_untying.replay_evidence import install_physics_capture
            install_physics_capture(tooling, a.output, max_passes=a.physics_evidence_passes, record_video=a.video_evidence)
        tooling.cmd_replay(SimpleNamespace(task="knot_untying", instance=str(a.instance), traj=str(a.traj),
                                          repeat=a.repeat, strict=True, video=None, fps=15))
        return 0
    a.output.mkdir(parents=True, exist_ok=False)
    source = freeze_sources(a.output, a.tooling)
    command = [sys.executable, str(source/"scripts/audit_knot_oracle.py"), "--worker", "--instance", str(a.instance),
               "--traj", str(a.traj), "--repeat", str(a.repeat), "--output", str(a.output)]
    if a.tooling is not None:
        command += ["--tooling", str(source/"oracle_tooling"/a.tooling.name)]
    if a.physics_evidence:
        command.append("--physics-evidence")
    if a.physics_evidence_passes is not None:
        command += ["--physics-evidence-passes", str(a.physics_evidence_passes)]
    if a.video_evidence:
        command.append("--video-evidence")
    write_json_atomic(a.output/"command.json", command)
    code = supervise(command, a.output, source)
    native = read_replay_report(a.output/"run.log")
    result = dict(assess(native, repeat=a.repeat, exit_code=code, actions=trajectory["actions"]),
                  instance_identity=instance_identity(a.instance), trajectory=trajectory,
                  trajectory_sha256=sha256_file(a.traj), native_replay=native)
    write_json_atomic(a.output/"replay_audit.json", result)
    print(json.dumps(result), flush=True)
    return 0 if result["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
