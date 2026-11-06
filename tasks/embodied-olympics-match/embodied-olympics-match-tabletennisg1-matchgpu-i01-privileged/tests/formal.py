#!/usr/bin/env python3
"""The privileged twin's formal match (Embodied First Exam), run by tests/test.sh as root in the separate
no-network verifier: /app/output/policy/program.py plays seat A of a fresh, unmodified match of the frozen instance
(tests/match_instance.json) on the trusted simulator (/opt/trusted/sim, root only) with the sport's in-process runner
(tools/g1tt_priv/match.py: core/local.py), the program in its own process as `nobody` (tools/g1tt_priv/isolate.py,
worker.py from the public copy /opt/dev). Then the core's fresh-process replay of the episode must agree with the live
match, and the spectator video is drawn (after the verdict; never part of it). Writes /logs/verifier/reward.json."""
import json
import os
import pwd
import shutil
import subprocess
import sys
import time
from pathlib import Path

TRUSTED = Path("/opt/trusted")
SIM = TRUSTED / "sim"
OUT = Path("/logs/verifier")
DATA = OUT / "match"
POLICY_SRC, POLICY = Path("/app/output/policy"), Path("/tmp/g1tt_policy")
MAX_FILES, MAX_BYTES = 512, 32 << 20
inst = json.loads(Path("/tests/match_instance.json").read_text())
os.environ["G1TT_SIM"] = str(SIM)
sys.path.insert(0, str(SIM / "tools"))
from g1tt_priv import match as M  # noqa: E402
from g1tt_priv.isolate import Isolated  # noqa: E402

reward = {"success": 0, "valid_trial": 1, "technical_failure": 0, "grader_error": 0, "infra_error": 0,
          "deliverable": 0, "match_over": 0, "A_won": 0, "A_points": 0, "opponent_points": 0,
          "opponent_level": int(inst["level"]), "seed": int(inst["seed"]), "replay_ok": 0, "video_rendered": 0,
          "privileged": 1, "realtime": 0}


def write(note=None):
    if note:                                           # reward.json holds numbers only (Harbor's parser): the note apart
        (OUT / "note.txt").write_text(str(note)[:500] + "\n")
    for name in ("reward.json", "reward.txt"):
        p = OUT / name
        if p.exists() or p.is_symlink():
            p.unlink()
    (OUT / "reward.json").write_text(json.dumps(reward, indent=1, default=float))
    (OUT / "reward.txt").write_text(str(int(reward["success"])))


def copy_policy() -> str | None:
    """A plain copy of the deliverable (regular files only, within the limits), root-owned, readable by all."""
    if not (POLICY_SRC / "program.py").is_file() or POLICY_SRC.is_symlink():
        return "no /app/output/policy/program.py"
    files, size = [], 0
    for root, dirs, names in os.walk(POLICY_SRC, followlinks=False):
        for n in dirs + names:
            p = Path(root) / n
            if p.is_symlink() or not (p.is_dir() or p.is_file()):
                return f"{p}: not a regular file or directory"
        for n in names:
            files.append(Path(root) / n)
            size += (Path(root) / n).stat().st_size
    if len(files) > MAX_FILES or size > MAX_BYTES:
        return f"the policy folder holds {len(files)} files, {size} bytes (at most {MAX_FILES}, {MAX_BYTES})"
    shutil.rmtree(POLICY, ignore_errors=True)
    shutil.copytree(POLICY_SRC, POLICY, symlinks=False)
    for root, dirs, names in os.walk(POLICY):
        os.chown(root, 0, 0)
        os.chmod(root, 0o755)
        for n in names:
            os.chown(Path(root) / n, 0, 0)
            os.chmod(Path(root) / n, 0o644)
    return None


def nobody_pids(uid: int) -> list[int]:
    out = []
    for d in Path("/proc").iterdir():
        if d.name.isdigit():
            try:
                if d.stat().st_uid == uid:
                    out.append(int(d.name))
            except OSError:
                pass
    return out


def end_nobody(uid: int) -> int:
    """Kill every process of the program's user; the number still alive after (0 = clean)."""
    for _ in range(50):
        pids = nobody_pids(uid)
        if not pids:
            return 0
        for p in pids:
            try:
                os.kill(p, 9)
            except OSError:
                pass
        time.sleep(0.1)
    return len(nobody_pids(uid))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    why = copy_policy()
    if why:
        write(f"no deliverable: {why}")          # the agent's 0 (a valid trial)
        return
    reward["deliverable"] = 1
    nb = pwd.getpwnam("nobody")
    home = Path("/tmp/g1tt_nobody")
    home.mkdir(exist_ok=True)
    os.chown(home, nb.pw_uid, nb.pw_gid)
    env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": str(home), "PYTHONPATH": "/opt/dev",
           "PYTHONDONTWRITEBYTECODE": "1", "MUJOCO_GL": "osmesa", "PYOPENGL_PLATFORM": "osmesa",
           "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"}
    cmd = ["setpriv", f"--reuid={nb.pw_uid}", f"--regid={nb.pw_gid}", "--clear-groups", "--no-new-privs",
           "prlimit", "--nproc=256", "--", "python3", "/opt/dev/tools/g1tt_priv/worker.py", str(POLICY)]
    level, seed = int(inst["level"]), int(inst["seed"])
    spec = M.public_spec(level, seed)
    cfg = {"spec": spec, "seat": "A", "level": level, "seed": seed, "call_limit_s": inst["call_limit_s"],
           "budget_s": inst["budget_s"]}
    prog = Isolated(cmd, cfg, start_limit_s=float(inst.get("start_limit_s", 300)), env=env, cwd=str(home))
    prog.limit = float(inst["call_limit_s"])
    shutil.rmtree(DATA, ignore_errors=True)
    try:
        res = M.play(prog, level, seed, data=str(DATA), call_limit_s=float(inst["call_limit_s"]),
                     budget_s=float(inst["budget_s"]))
    except Exception as exc:  # noqa: BLE001  the trusted runner failed: not the program's result
        prog.close()
        end_nobody(nb.pw_uid)
        reward.update(valid_trial=0, technical_failure=1, infra_error=1)
        write(f"the match runner failed: {type(exc).__name__}: {exc}")
        return
    prog.close()
    left = end_nobody(nb.pw_uid)
    res["program"].update(failed=prog.failed, why=prog.why, stale=prog.stale, survivors=left)
    sc = res.get("scores") or {}
    reward.update(match_over=int(bool(res.get("finished"))), A_points=int(sc.get("A", 0)),
                  opponent_points=int(sc.get("opponent", 0)), steps=int(res.get("k") or 0),
                  program_calls=res["program"]["calls"], program_late=res["program"]["late"],
                  program_errors=res["program"]["errors"], program_failed=int(bool(prog.failed)),
                  program_s=res["program"]["program_s"], match_wall_s=res.get("wall_s"))
    won = bool(res.get("finished")) and res.get("winner") == "A"
    reward["A_won"] = int(won)
    # the core's fresh-process replay of the recorded episode must give the same match
    try:
        r = subprocess.run([sys.executable, "-m", "core.episode", str(SIM / "sport/plugin.py"), str(DATA)],
                           cwd=SIM, capture_output=True, text=True, timeout=float(inst.get("replay_timeout_s", 1200)),
                           env={**os.environ, **M.ENV})
        rc = json.loads((DATA / "replay_check.json").read_text()) if r.returncode == 0 else None
    except (subprocess.TimeoutExpired, OSError, ValueError):
        rc = None
    ok = rc is not None and rc.get("scores") == res.get("scores") and rc.get("winner") == res.get("winner") \
        and int(rc.get("k", -1)) == int(res.get("k", -2)) \
        and (rc.get("state_sha") is None or res.get("digest") is None or rc.get("state_sha") == res.get("digest"))
    reward["replay_ok"] = int(ok)
    (OUT / "match_result.json").write_text(json.dumps({"live": res, "replay": rc}, indent=1, default=float))
    if not ok:                                         # the platform could not reproduce its own match: void
        reward.update(valid_trial=0, technical_failure=1, infra_error=1)
        write("the fresh-process replay does not agree with the live match")
        return
    if left:                                           # a process of the program outlived the match: its 0
        write(f"{left} process(es) of the program's user survived the match")
        return
    reward["success"] = int(won)
    write()
    # the replay video, after the verdict (never part of it)
    try:
        subprocess.run([sys.executable, "-m", "core.spectator", str(SIM / "sport/plugin.py"), str(DATA)], cwd=SIM,
                       capture_output=True, timeout=float(inst.get("video_timeout_s", 1500)),
                       env={**os.environ, **M.ENV})
        vids = sorted(DATA.glob("*.mp4"))
        if vids:
            shutil.copy(vids[0], OUT / "replay.mp4")
            reward["video_rendered"] = 1
            write()
    except (subprocess.TimeoutExpired, OSError):
        pass


if __name__ == "__main__":
    main()
