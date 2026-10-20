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
import tempfile
import threading
import time
from pathlib import Path

from core.realtime import RealtimeService
from core.sport import MatchConfig, Refused
from tools.tt_fullsim.runner import Program
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


def _alive_of(uid):
    """PIDs of `uid`'s live processes (zombies excluded: they hold nothing and only their parent can reap them)."""
    alive = []
    for d in Path("/proc").iterdir():
        if not d.name.isdigit():
            continue
        try:
            if d.stat().st_uid != uid:
                continue
            if (d / "stat").read_text().rsplit(")", 1)[1].split()[0] == "Z":
                continue
        except (OSError, IndexError):
            continue
        alive.append(int(d.name))
    return alive


def end_uid_processes(uid, rounds=50, min_s=30.0):
    """End every process of the policy's user (a double fork or setsid leaves the program's process group): a child
    that drops to `uid` sends kill(-1, SIGKILL), which reaches every process of that user at once (a fork loop cannot
    outrun it; RLIMIT_NPROC bounds it anyway), round after round until none is left. Returns True when none is left,
    False when one survives at least `rounds` rounds and `min_s` seconds (a killed process can take a while to exit on
    a loaded host): the caller grades the program 0, never infra (#282 review); never raises."""
    import signal

    t_end, n = time.monotonic() + min_s, 0
    while n < rounds or time.monotonic() < t_end:
        n += 1
        if not _alive_of(uid):
            return True
        try:
            pid = os.fork()
        except OSError:  # no process slot for the killer this round: try again
            time.sleep(0.05)
            continue
        if pid == 0:  # the killer: as `uid`, kill(-1) signals exactly that user's processes (and not itself)
            try:
                os.setgroups([])
                os.setgid(uid)
                os.setuid(uid)
                os.kill(-1, signal.SIGKILL)
            except OSError:
                pass
            os._exit(0)
        try:
            os.waitpid(pid, 0)
        except ChildProcessError:  # already reaped (SIGCHLD ignored)
            pass
        time.sleep(0.05)
    return not _alive_of(uid)


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


def agent_sim_error(final: dict) -> bool:
    """#282 review (docs/protocol/running.md "Infrastructure failures", as in the standard-realtime twins): simulator
    errors of the control step itself (every errors[] entry where "world_step") after the program's first applied
    command are the program's result (a 0), never infrastructure; any other error of the trusted record stays infra."""
    # (#282 review round 4) the "replay" entry the service adds when its fresh-process replay of the journal fails (it
    # re-runs a failing command, not the failing step) and a "continuous_score" one follow from the program's error and
    # do not make it infrastructure (the rule for the live twins: a world_step error after the first command)
    errs = [e for e in (final.get("errors") or [])
            if not (isinstance(e, dict) and e.get("where") in ("replay", "continuous_score"))]
    applied = int(((final.get("seats") or {}).get("A") or {}).get("applied") or 0)
    return bool(errs) and applied > 0 and all(isinstance(e, dict) and e.get("where") == "world_step" for e in errs)


class _ProgramSimError(Exception):
    """agent_sim_error(final): graded before the replay check (the replay cannot agree with a match that ended in it)."""


def evaluate(policy, out, *, level, seed=22, slowdown=10, wall_limit=7200, unsafe_local=False, dev_root=None):
    """wall_limit: the formal match's wall-clock bound, the standard-realtime twin's own cutoff (its agent session,
    RCB_WALL_CLOCK_S): the match ends as there (match over; at the bound it is unfinished and not won)."""
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
    isolated = True
    trusted_failure = None
    scratch_ready = False
    stage = "program"   # sanitize: the submission's own files
    public = Path(tempfile.mkdtemp(prefix="tt-policy-"))
    public.chmod(0o755)
    try:
        sanitize(Path(policy).absolute(), public / "policy")
        scratch = public / "scratch"
        scratch.mkdir(mode=0o700)
        scratch_ready = True
        if not unsafe_local:
            os.chown(scratch, 65534, 65534)
        stage = "trusted"   # #282 review round 4: what fails from here to the program's load is infra
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
        stage = "program"
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
            stage = "trusted"
            code, observed = service.observe("A", {})
            if code != 200:
                if service.phase == "over":
                    break
                trusted_failure = f"trusted observe failed: {code}"   # the service's own failure: infra, not the program's
                raise RuntimeError(trusted_failure)
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
            stage = "program"
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
        if trusted_failure is None and (stage == "trusted" or (program is None and isinstance(exc, OSError)
                                                                and stage == "program" and scratch_ready)):
            # the service or its observation, or the program's process could not be started (the trusted
            # interpreter and its tree: a submission cannot make Popen fail), not the program
            trusted_failure = f"{type(exc).__name__}: {exc}"
    finally:
        if program is not None:
            try:
                program.close()
            except Exception:  # noqa: BLE001 -- the sweep below ends whatever is left
                pass
        if not unsafe_local:
            isolated = end_uid_processes(65534)
        if service is not None and service.phase != "over":
            service.collect()
        if service is not None:
            # Wait under the service's lock: its finalize thread sets `finalized` and rewrites final.json (the replay's
            # verdict) in one critical section, so reading the flag without the lock could read the old final.json.
            deadline = time.monotonic() + 650
            with service.cond:
                while not service.finalized and time.monotonic() < deadline:
                    service.cond.wait(timeout=1.0)
        try:
            shutil.rmtree(public, ignore_errors=True)
        except Exception:  # noqa: BLE001 -- e.g. RecursionError
            pass
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
        "isolation_failed": int(not isolated),
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
            if agent_sim_error(final):
                raise _ProgramSimError
            # One replay (#282 decision 4): the original service replayed the journal in a fresh process for its
            # verdict (final.json "deterministic", replay_check.json); its record must agree with the live match.
            rep = json.loads((out / "match/replay_check.json").read_text())
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
                and isolated
            )
            result.update(
                success=int(valid and final["match_winner"] == "A"),
                valid=int(valid),
                deterministic=int(equal),
                # the trusted record's own errors are infra unless they are the program's (agent_sim_error); a
                # replay that disagrees with the live match is the simulator's (the program cannot reach it): infra
                infra_error=int((bool(final["errors"]) and not agent_sim_error(final)) or not equal
                                or trusted_failure is not None),
                replays=1,
                points_for=final["scores"]["A"],
                points_against=final["scores"]["opponent"],
                steps=final["steps"],
                late_max_s=final["sim_lag"]["late_max_s"],
            )
            diagnostics.update(
                final_reason=final["reason"],
                source_sha=final["source_sha"],
                continuous=final.get("continuous"),
            )
    except _ProgramSimError:   # a simulator error of the control step after the program's first command: its 0
        result.update(success=0, valid=1, infra_error=int(trusted_failure is not None), replays=1)
        diagnostics.update(final_reason=final.get("reason"), agent_sim_error=1)
    except Exception as exc:  # noqa: BLE001 -- a verification failure is an infra error, never a crash
        result.update(success=0, valid=0, infra_error=1)
        diagnostics["verification_error"] = f"{type(exc).__name__}: {exc}"
    if trusted_failure is not None:   # the trusted side failed (also before the service came up): infra
        result.update(success=0, valid=0, infra_error=1)
        diagnostics["trusted_failure"] = trusted_failure
    if not isolated:   # the program's processes outlived the sweep (RLIMIT_NPROC, kill(-1) rounds): its 0, not a retry
        result.update(success=0, valid=0)
        diagnostics["isolation"] = "processes of the policy's user (nobody) survived kill(-1)"
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
    p.add_argument("--wall-limit", type=float, default=7200)
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
