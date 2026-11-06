#!/usr/bin/env python3
"""ADVISORY hook: AM-Bench's standard collect hook (embodied_first_exam/benchmarks/ambench/sim/finalize.sh) compares the
post-hoc film with the live episode and never lets it change the verdict (tasks/ambench/README.md, Grading). Runs the
hook against stubs (no Isaac, no GPU): the shared `rcb_limited.py end` stub, a `film` stub that prints a given result,
a recorded live episode; checks final.json for a matching film, a film in other last bits (kept, marked), a film with
another outcome (dropped) and a failed film. Run by ci_checks/run_all.sh with the task directories in scope: it runs
once when one of them is an AM-Bench task (or when none is given)."""
import json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HOOK = ROOT / "embodied_first_exam/benchmarks/ambench/sim/finalize.sh"
LIVE = {"success": True, "control_steps": 1027, "live_sha": "a" * 64, "steps": 9, "calls": 9, "reason": "success",
        "n_actions": 1027, "task": "PressButton-Am-FAHexa-Abs-PID-Direct-v0", "sim_startups": 1}
TOOL = '''import json, os, sys
def count_gpu_faults(line):
    return 0
if __name__ == "__main__" and sys.argv[1:2] == ["film"]:
    a = sys.argv; video = a[a.index("--video") + 1]
    res = json.loads(os.environ["STUB_FILM"])
    if res is None:
        sys.exit(1)
    open(video, "wb").write(b"mp4"); open(video[:-4] + ".last.png", "wb").write(b"png")
    print(json.dumps({"task": "x", "film": res, "video": video}))
'''


def run(film) -> tuple[dict, Path]:
    tmp = Path(tempfile.mkdtemp(prefix="amb-finalize-"))
    srv, data, bin_ = tmp / "srv", tmp / "data", tmp / "bin"
    for d in (srv, data, bin_):
        d.mkdir()
    (srv / "rcb_limited.py").write_text("import sys\nsys.exit(0)\n")   # `end`: the service dumped the episode
    (srv / "rcb_ambench.py").write_text(TOOL)
    (bin_ / "python").symlink_to(sys.executable)
    (data / "episode.json").write_text(json.dumps(LIVE))
    (data / "startups.jsonl").write_text('{"pid": 1}\n')
    (data / "server.log").write_text("[rcb] the episode's physics starts\n")
    (data / "trajectory.npz").write_bytes(b"rows")
    env = {**os.environ, "PATH": f"{bin_}:{os.environ.get('PATH', '')}", "RCB_SRV": str(srv), "RCB_DATA": str(data),
           "RCB_TOOL": str(srv / "rcb_ambench.py"), "RCB_INSTANCE": str(srv / "instance.json"),
           "RCB_COLLECT_TIMEOUT_S": "4800", "STUB_FILM": json.dumps(film)}
    p = subprocess.run(["sh", str(HOOK)], env=env, capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        raise AssertionError(f"finalize.sh exited {p.returncode}: {p.stderr[-500:]}")
    return json.loads((data / "final.json").read_text()), data


def main(argv) -> int:
    if argv and not any("tasks/ambench/" in a or a.rstrip("/").split("/")[-1].startswith("ambench-") for a in argv):
        return 0
    same = {"success": True, "control_steps": 1027, "state_sha": "a" * 64, "end_reason": "success", "executed_rows": 1027}
    cases = [
        ("film = live", same, dict(video=True, video_matches_live=True, video_outcome_matches_live=True), True),
        ("other last bits", {**same, "state_sha": "b" * 64},
         dict(video=True, video_matches_live=False, video_outcome_matches_live=True), True),
        ("other outcome", {**same, "success": False, "control_steps": 2399, "end_reason": "episode_timeout"},
         dict(video=False, video_matches_live=False, video_outcome_matches_live=False), False),
        ("other step", {**same, "control_steps": 1028},
         dict(video=False, video_matches_live=False, video_outcome_matches_live=False), False),
        ("film failed", None, dict(video=False), False),
    ]
    bad = 0
    for name, film, want, kept in cases:
        fin, data = run(film)
        got = {k: fin.get(k) for k in want}
        problems = []
        if got != want:
            problems.append(f"{got} != {want}")
        if fin.get("success") is not True or fin.get("live_success") is not True or fin.get("infra_error"):
            problems.append(f"the verdict changed: success {fin.get('success')}, infra_error {fin.get('infra_error')}")
        if (data / "replay.mp4").exists() != kept:
            problems.append(f"replay.mp4 {'missing' if kept else 'kept'}")
        if name == "other last bits" and not fin.get("video_note"):
            problems.append("no video_note")
        if not kept and not fin.get("video_error"):
            problems.append("no video_error")
        shutil.rmtree(data.parent, ignore_errors=True)
        if problems:
            bad += 1
            print(f"FAIL advisory-finalize-video ({name}): " + "; ".join(problems))
    if not bad:
        print(f"ok advisory-finalize-video: {len(cases)} cases (the film is compared with the live episode, the verdict never changes)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
