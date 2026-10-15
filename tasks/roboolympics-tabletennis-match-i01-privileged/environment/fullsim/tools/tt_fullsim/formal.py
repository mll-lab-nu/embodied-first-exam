"""Native frozen-core formal program evaluation; no bespoke world scheduler.

Production invocation requires a root-owned, private trusted source tree and runs
submitted code as nobody in a separate process, inside a no-network verifier.
--unsafe-local is a functional-only development mode, never a production verdict.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from core.realtime import RealtimeService
from core.sport import MatchConfig, Refused
from tools.tt_fullsim.runner import Program, child_env
from tools.tt_fullsim.session import FROZEN, ROOT, plain, plugin


class NoRenderSport:
    workers = ()

    def __init__(self, sport):
        self.sport = sport

    def __getattr__(self, name):
        return getattr(self.sport, name)


class FullSimService(RealtimeService):
    """Original clock/act/ready/referee/replay; explicit full-state observation adapter."""

    def observation(self, seat, query=None, since=None):
        obs = super().observation(seat, query, since)
        r = self.m.R
        obs["truth"] = plain(
            {
                **r.s.state(),
                "opponent_x": r.opp_x(),
                "opponent_parameters": r.lv,
                "leg": r.leg,
                "qpos": r.s.d.qpos,
                "qvel": r.s.d.qvel,
                "servo": r.s.servo.state(),
            }
        )
        return obs

    def camera_job(self, seat, query=None):
        return None, {}

    def draw(self, seat, job):
        return None


def end_uid_processes(uid, rounds=50):
    """Kill every process of the policy's user that is still alive (a double fork or setsid leaves the program's
    process group), until none is left; raises if one survives. Nothing is graded before this returns."""
    import signal

    for _ in range(rounds):
        alive = []
        for d in Path("/proc").iterdir():
            if not d.name.isdigit():
                continue
            try:
                if d.stat().st_uid == uid:
                    alive.append(int(d.name))
            except OSError:
                continue
        if not alive:
            return
        for pid in alive:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        time.sleep(0.05)
    raise RuntimeError(f"processes of uid {uid} survive")


def sanitize(source, destination):
    """Copy bounded regular files only. Never follow an agent-controlled link."""
    if not source.is_dir() or source.is_symlink():
        raise ValueError("submit a real policy/ directory containing program.py")
    total = count = 0
    destination.mkdir(mode=0o755)
    for p in sorted(source.rglob("*")):
        mode = p.lstat().st_mode
        target = destination / p.relative_to(source)
        if stat.S_ISDIR(mode):
            target.mkdir(mode=0o755, exist_ok=True)
            continue
        if not stat.S_ISREG(mode) or p.is_symlink():
            raise ValueError("policy contains a symlink, device, FIFO or socket")
        count += 1
        total += p.stat().st_size
        if count > 512 or total > 32 * 1024**2:
            raise ValueError("policy exceeds 512 files or 32 MiB")
        # Files are copied, not imported/executed by the trusted evaluator.
        with p.open("rb") as src, target.open("xb") as dst:
            shutil.copyfileobj(src, dst)
        target.chmod(0o644)
    if not (destination / "program.py").is_file():
        raise ValueError("missing policy/program.py")


def evaluate(policy, out, *, level, seed=22, slowdown=10, wall_limit=1800, unsafe_local=False, dev_root=None):
    if level not in (1, 2, 3, 4) or isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 100000:
        raise ValueError("opponent level 1-4 and a public seed below 100000 required")
    if not unsafe_local and os.geteuid() != 0:
        raise PermissionError("formal evaluation requires verifier root; use --unsafe-local only for local smoke")
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    out.chmod(0o700)
    dev_root = Path(dev_root or ROOT).resolve()
    if not unsafe_local:
        if ROOT.stat().st_uid != 0 or ROOT.stat().st_mode & 0o077:
            raise PermissionError("trusted source root must be root-owned with mode 0700")
        if dev_root == ROOT:
            raise PermissionError("the unprivileged program must use the separate public development tree")
    os.environ.update(
        PLAYER_MODE_A="unmetered",
        RCB_ACT_RULE="program",
        RCB_BROADCAST="0",
        RCB_RENDER_VIDEO="0",
        READY_TIMEOUT_S="300",
        START_TIMEOUT_S="30",
        RO_REPLAY_TIMEOUT_S="600",
        MUJOCO_GL="disable",
    )
    started = time.monotonic()
    program = service = None
    reason = error = None
    refusals = calls = 0
    public = Path(tempfile.mkdtemp(prefix="tt-policy-"))
    public.chmod(0o755)
    try:
        sanitize(Path(policy).absolute(), public / "policy")
        scratch = public / "scratch"
        scratch.mkdir(mode=0o700)
        if not unsafe_local:
            os.chown(scratch, 65534, 65534)
        cfg = MatchConfig(
            "tabletennis",
            "match",
            ("A",),
            seed,
            first="A",
            slowdown=slowdown,
            level=level,
            action_level="high",
            play="program",
        )
        service = FullSimService(
            NoRenderSport(plugin().SPORT),
            str(ROOT / "sports/tabletennis/plugin.py"),
            cfg,
            out / "match",
            clock_s=wall_limit,
        )
        service.write_final()
        loop = threading.Thread(target=service.loop, daemon=True)
        loop.start()
        _, spec = service.spec("A")
        spec.update(cfg=cfg.to_json(), frozen_commit=FROZEN)
        program = Program(
            public / "policy/program.py",
            out,
            {"spec": plain(spec), "setting": "fullsim-program/1"},
            worker_root=dev_root,
            identity=None if unsafe_local else 65534,
            workdir=scratch,
        )
        service.ready("A", {"why": "submitted program loaded", "plan": "closed-loop policy"})
        next_at = 0
        decisions = (out / "decisions.jsonl").open("w")
        while service.phase != "over":
            if time.monotonic() - started >= wall_limit:
                reason = "policy_wall_timeout"
                break
            if service.phase == "running" and service.m.k < next_at:
                time.sleep(0.002)
                continue
            code, observed = service.observe("A", {})
            if code != 200:
                if service.phase == "over":
                    break
                raise RuntimeError(f"trusted observe failed: {code}")
            st = observed["now"]
            truth = st.pop("truth")
            unit = service.m.unit()
            view = {
                "state": {
                    **st,
                    "service_phase": st["phase"],
                    "phase": {"review": "unit_over", "running": "playing", "over": "finished"}.get(
                        st["phase"], st["phase"]
                    ),
                },
                "truth": truth,
                "scores": service.m.scores(),
                "observation": observed["observation"],
            }
            deadline = time.monotonic() + 5
            program.send(view, timeout=5)
            calls += 1
            message = None
            while message is None and service.phase != "over":
                message = program.poll()
                if time.monotonic() > deadline:
                    raise TimeoutError("program call exceeded 5s")
                time.sleep(0.001)
            if service.phase == "over":
                break
            if not isinstance(message, dict) or set(message) != {"command"}:
                raise ValueError("one command response per observation required")
            cmd = message["command"]
            if unit != service.m.unit():
                decisions.write(json.dumps({"seen": st["step"], "dropped": "unit_over"}) + "\n")
                continue
            if cmd is not None:
                if not isinstance(cmd, dict):
                    raise TypeError("command must be object or null")
                if cmd.get("type") == "ready":
                    code, reply = service.ready("A", {"why": "program review", "plan": "continue same policy"})
                else:
                    try:
                        code, reply = service.act("A", cmd)
                    except Refused as exc:
                        code, reply = exc.code, {"error": str(exc)}
                refusals += int(code != 200)
                decisions.write(
                    json.dumps(plain({"seen": st["step"], "command": cmd, "code": code, "reply": reply})) + "\n"
                )
            next_at = service.m.k + 5
        decisions.close()
    except Exception as exc:  # noqa: BLE001 -- untrusted program failures become an explicit zero, not a forged win
        reason, error = "policy_error", f"{type(exc).__name__}: {exc}"
    finally:
        if program is not None:
            program.close()
        if not unsafe_local:
            end_uid_processes(65534)
        if service is not None and service.phase != "over":
            service.collect()
        if service is not None:
            # Wait under the service's lock: its finalize thread sets `finalized` and rewrites final.json (the replay's
            # verdict) in one critical section, so reading the flag without the lock could read the old final.json.
            deadline = time.monotonic() + 650
            with service.cond:
                while not service.finalized and time.monotonic() < deadline:
                    service.cond.wait(timeout=1.0)
        shutil.rmtree(public)
    result = {
        "success": 0,
        "valid": 0,
        "deterministic": 0,
        "infra_error": 0,
        "policy_error": int(error is not None),
        "calls": calls,
        "refused": refusals,
        "level": level,
        "seed": seed,
        "slowdown": slowdown,
        "replays": 0,
        "isolation_checked": int(not unsafe_local),
    }
    diagnostics = {
        "reason": reason,
        "error": error,
        "frozen_commit": FROZEN,
        "timing": "original core.realtime.RealtimeService; full-state/no-render adapter",
        "wall_s": time.monotonic() - started,
        "unsafe_local": unsafe_local,
    }
    try:
        if service is not None:
            final = json.loads((out / "match/final.json").read_text())
            if not final.get("graded_ready"):
                raise ValueError("the service's final.json is not graded yet (replay unfinished)")
            # Original service already replayed once in a fresh process. Do a second fresh journal replay.
            second = subprocess.run(
                [sys.executable, "-m", "core.episode", str(ROOT / "sports/tabletennis/plugin.py"), str(out / "match")],
                cwd=ROOT,
                env=child_env(),
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
            )
            rep = json.loads((out / "match/replay_check.json").read_text()) if second.returncode == 0 else {}
            equal = bool(
                final["deterministic"]
                and rep.get("state_sha") == final["state_sha"]
                and rep.get("scores") == final["scores"]
                and rep.get("k") == final["steps"]
                and rep.get("winner") == final["match_winner"]
                and rep.get("commands_sha") == final["commands_sha"]
            )
            valid = bool(
                final["valid_trial"] and final["reason"] == "match_over" and equal and not error and not reason
            )
            result.update(
                success=int(valid and final["match_winner"] == "A"),
                valid=int(valid),
                deterministic=int(equal),
                infra_error=int(bool(final["errors"]) or second.returncode != 0),
                replays=2,
                points_for=final["scores"]["A"],
                points_against=final["scores"]["opponent"],
                steps=final["steps"],
                late_max_s=final["sim_lag"]["late_max_s"],
            )
            diagnostics.update(
                final_reason=final["reason"],
                source_sha=final["source_sha"],
                continuous=final.get("continuous"),
                replay_stderr=second.stderr[-2000:],
            )
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        result.update(success=0, valid=0, infra_error=1)
        diagnostics["verification_error"] = f"{type(exc).__name__}: {exc}"
    (out / "reward.txt").write_text(str(result["success"]) + "\n")
    (out / "reward.json").write_text(json.dumps(result, indent=2))
    (out / "diagnostics.json").write_text(json.dumps(diagnostics, indent=2))
    return result


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--policy", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--level", type=int, choices=(1, 2, 3, 4), required=True)
    p.add_argument("--seed", type=int, default=22)
    p.add_argument("--dev-root", type=Path)
    p.add_argument("--wall-limit", type=float, default=1800)
    p.add_argument("--slowdown", type=float, default=10)
    p.add_argument("--unsafe-local", action="store_true")
    args = p.parse_args()
    print(
        json.dumps(
            evaluate(
                args.policy,
                args.out,
                level=args.level,
                seed=args.seed,
                dev_root=args.dev_root,
                wall_limit=args.wall_limit,
                slowdown=args.slowdown,
                unsafe_local=args.unsafe_local,
            )
        )
    )


if __name__ == "__main__":
    main()
