#!/usr/bin/env python3
"""Unit test of scripts/ikea_mujoco/shared/grade.py's crash handling, without MuJoCo: grade.py runs next to a fake
rcb_ikea.py whose `replay` either succeeds or kills itself with SIGSEGV, chosen per replay index.
    python3 scripts/ikea_mujoco/tests/test_grade.py"""
import json, os, pathlib, shutil, subprocess, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
GRADE = HERE.parent / "shared/grade.py"
FAKE = r'''
import json, os, signal, sys
SCENES_ROOT = os.environ["FAKE_SCENES"]
class InvalidTrajectory(ValueError): pass
def scene_files(d): return {"scene.py": "x"}
def load_trajectory(path, nu, timestep=None, max_rows=None): return [[0.0] * nu]
if __name__ == "__main__":
    a = sys.argv[1:]
    out = a[a.index("--out") + 1]
    k = int(out.rsplit("_", 1)[1].split(".")[0])
    if os.environ["FAKE_CRASH"][k] == "1":
        os.kill(os.getpid(), signal.SIGSEGV)
    if os.environ["FAKE_CRASH"][k] == "9":
        os.kill(os.getpid(), signal.SIGKILL)
    if os.environ["FAKE_CRASH"][k] == "t":
        os.kill(os.getpid(), signal.SIGTERM)
    if os.environ["FAKE_CRASH"][k] == "b":
        os.kill(os.getpid(), signal.SIGBUS)
    if os.environ["FAKE_CRASH"][k] == "2":    # the scene's code raised on the rows (rcb_ikea.py replay records it)
        json.dump({"initial_state_sha": "s0", "success": False, "replay_exception": "ValueError: math domain error",
                   "rows": 1, "state_sha": "e"}, open(out, "w"))
        sys.exit(0)
    if os.environ["FAKE_CRASH"][k] == "3":    # another initial state on this host
        json.dump({"initial_state_sha": "other", "success": True, "state_sha": "e", "settled_sha": "f", "rows": 1}, open(out, "w"))
        sys.exit(0)
    json.dump({"initial_state_sha": "s0", "success": True, "state_sha": "e", "settled_sha": "f", "rows": 1,
               "settled": {"goal": True, "released": True, "at_rest": True}, "goal": True, "released": True,
               "at_rest": True, "terminal": {}}, open(out, "w"))
'''


def run(crash: str) -> dict:
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        shutil.copyfile(GRADE, td / "grade.py")
        (td / "rcb_ikea.py").write_text(FAKE)
        (td / "scenes/t").mkdir(parents=True)
        (td / "traj.npz").write_bytes(b"x")
        (td / "binding.json").write_text(json.dumps({"scene_files": {"scene.py": "x"}, "nu": 2, "timestep": 0.001,
                                                     "initial_state_sha256": "s0"}))
        log = td / "logs"
        env = dict(os.environ, FAKE_SCENES=str(td / "scenes"), FAKE_CRASH=crash, RCB_VERIFIER_LOG_DIR=str(log))
        subprocess.run([sys.executable, str(td / "grade.py"), "--task", "t", "--binding", str(td / "binding.json"),
                        "--traj", str(td / "traj.npz")], env=env, check=True, capture_output=True)
        return json.loads((log / "reward.json").read_text())


def main() -> int:
    ok = run("00")
    assert ok["success"] == 1 and ok["grader_error"] == 0 and ok["deterministic"] == 1, ok
    for crash, det in (("10", 0), ("01", 0), ("11", 1)):
        r = run(crash)
        assert r["success"] == 0 and r["sim_breakdown"] == 1 and r["replay_crash"] == 1, (crash, r)
        assert r["grader_error"] == 0 and r["infra_error"] == 0 and r["deterministic"] == det, (crash, r)
        assert r["replays_crashed"] == crash.count("1") and r["replay_signal"] == 11, (crash, r)
    for crash, det in (("22", 1), ("02", 0)):     # an exception in the scene's code: the agent's 0, no free retry
        r = run(crash)
        assert r["success"] == 0 and r["sim_breakdown"] == 1 and r["replay_exception"] == 1, (crash, r)
        assert r["grader_error"] == 0 and r["infra_error"] == 0 and r["deterministic"] == det, (crash, r)
    for crash in ("90", "91", "t0"):              # SIGKILL (OOM killer) / SIGTERM, also next to a SIGSEGV: infrastructure
        r = run(crash)
        assert r["success"] == 0 and r["infra_error"] == 1 and r["replay_killed"] == 1, (crash, r)
    r = run("1b")                                 # two different crash signals: a breakdown, not deterministic
    assert r["sim_breakdown"] == 1 and r["infra_error"] == 0 and r["deterministic"] == 0, r
    r = run("33")                                 # the host builds another initial state: infrastructure
    assert r["success"] == 0 and r["infra_error"] == 1 and r["instance_mismatch"] == 1, r
    print("test_grade: ok (no crash, one of two, the other one, both; scene exceptions; instance mismatch)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
