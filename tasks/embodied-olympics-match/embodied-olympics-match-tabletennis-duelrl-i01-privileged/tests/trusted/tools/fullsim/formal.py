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
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from core.realtime import RealtimeService
from core.sport import Refused
from tools.fullsim.adapter import load
from tools.fullsim.program import Program, end_uid_processes, sanitize
from tools.fullsim.session import FROZEN, ROOT, match_config, plain, plugin, plugin_path


class NoRenderSport:
    """The sport without its render workers (no cameras here); its other workers (a planner, e.g. badminton's stroke
    plans) run as in the twin's service."""

    def __init__(self, sport):
        self.sport = sport
        self.workers = tuple(w for w in getattr(sport, "workers", ()) if w != "render")

    def __getattr__(self, name):
        return getattr(self.sport, name)


class FullSimService(RealtimeService):
    """Original clock/act/ready/referee/replay; explicit full-state observation adapter (the sport's truth hook)."""

    truth = None  # set per instance: the adapter's truth(match)

    def observation(self, seat, query=None, since=None):
        obs = super().observation(seat, query, since)
        obs["truth"] = plain(self.truth(self.m))
        return obs

    def camera_job(self, seat, query=None):
        return None, {}

    def draw(self, seat, job):
        return None


def commands_of(cmd, limit):
    """A program's answer to one view: None, one command (a dict) or a list of at most `limit` commands; `ready` only
    alone."""
    if cmd is None:
        return []
    cmds = cmd if isinstance(cmd, list) else [cmd]
    if len(cmds) > limit:
        raise ValueError(f"at most {limit} command(s) per view")
    if any(not isinstance(c, dict) for c in cmds):
        raise TypeError("a command must be an object (or a list of objects, or null)")
    if len(cmds) > 1 and any(c.get("type") == "ready" for c in cmds):
        raise ValueError("ready comes alone")
    return cmds


def brief(reply):
    """A reply as decisions.jsonl keeps it: without the full world state (`now`, with the truth) the service attaches,
    only its step (a whole soccer match would otherwise write ~150 MB)."""
    if isinstance(reply, dict) and isinstance(reply.get("now"), dict):
        return {**{k: v for k, v in reply.items() if k != "now"}, "now_step": reply["now"].get("step")}
    return reply


def submit(service, cmds):
    """The commands of one view, as a player would send them over HTTP: `ready` alone; several actions (one per
    entity, MAX_COMMANDS) concurrently, so that all of them can take effect at the same control-step boundary (the
    service keeps one act in flight per seat and entity). Returns (code, reply) per command, in the list's order."""

    def one(cmd):
        if cmd.get("type") == "ready":
            return service.ready("A", {"why": "program review", "plan": "continue same policy"})
        try:
            return service.act("A", cmd)
        except Refused as exc:
            return exc.code, {"error": str(exc)}

    if len(cmds) <= 1:
        return [one(c) for c in cmds]
    results = [None] * len(cmds)

    def run(i):
        try:
            results[i] = one(cmds[i])
        except Exception as exc:  # noqa: BLE001 -- re-raised below, in the caller's thread
            results[i] = exc

    threads = [threading.Thread(target=run, args=(i,), daemon=True) for i in range(len(cmds))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    for r in results:
        if isinstance(r, Exception):
            raise r
    return results


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


def evaluate(policy, out, *, sport, level, seed, slowdown=None, wall_limit=None, unsafe_local=False, dev_root=None):
    ad = load(sport)
    slowdown = ad.SLOWDOWN if slowdown is None else slowdown
    wall_limit = ad.MATCH_WALL_S if wall_limit is None else wall_limit
    if level not in ad.LEVELS or isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 100000:
        raise ValueError(f"opponent level {tuple(ad.LEVELS)} and a public seed below 100000 required")
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
        READY_TIMEOUT_S=str(ad.READY_TIMEOUT_S),
        START_TIMEOUT_S="30",
        RO_REPLAY_TIMEOUT_S=str(ad.REPLAY_TIMEOUT_S),
        MUJOCO_GL="disable",
    )
    started = time.monotonic()
    program = service = None
    reason = error = None
    leftover = False
    trusted_failure = None
    scratch_ready = False
    stage = "program"   # sanitize: the submission's own files
    refusals = calls = 0
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
        cfg = match_config(ad, level, seed, slowdown)
        service = FullSimService(
            NoRenderSport(plugin(ad.SPORT).SPORT),
            str(plugin_path(ad.SPORT)),
            cfg,
            out / "match",
            clock_s=wall_limit,
        )
        service.truth = ad.truth
        service.write_final()
        loop = threading.Thread(target=service.loop, daemon=True)
        loop.start()
        _, spec = service.spec("A")
        spec.update(cfg=cfg.to_json(), frozen_commit=FROZEN)
        stage = "program"
        program = Program(
            public / "policy/program.py",
            out,
            {"spec": plain(spec), "setting": "fullsim-program/1", "max_commands": ad.MAX_COMMANDS},
            worker_root=dev_root,
            identity=None if unsafe_local else 65534,
            workdir=scratch,
            cpu_s=int(wall_limit) + 30,  # RLIMIT_CPU: the match cutoff (+ load)
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
            cmds = commands_of(message["command"], ad.MAX_COMMANDS)
            if unit != service.m.unit():
                decisions.write(json.dumps({"seen": st["step"], "dropped": "unit_over"}) + "\n")
                continue
            for cmd, (code, reply) in zip(cmds, submit(service, cmds)):
                refusals += int(code != 200)
                decisions.write(
                    json.dumps(plain({"seen": st["step"], "command": cmd, "code": code, "reply": brief(reply)})) + "\n"
                )
            next_at = service.m.k + ad.EVERY
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
            leftover = not end_uid_processes(65534)  # a survivor: the program's 0 (it evaded the sweep), never a crash
        if service is not None and service.phase != "over":
            service.collect()
        if service is not None:
            # Wait under the service's lock: its finalize thread sets `finalized` and rewrites final.json (the replay's
            # verdict) in one critical section, so reading the flag without the lock could read the old final.json.
            deadline = time.monotonic() + ad.REPLAY_TIMEOUT_S + 50
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
        "processes_left": int(leftover),
    }
    diagnostics = {
        "sport": ad.SPORT,  # reward.json holds numbers only (Harbor parses every value)
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
            # One replay (#282 review, decision 4): the original service's own fresh-process replay of the journal,
            # which wrote replay_check.json and the verdict in final.json; both must agree with the live match.
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
    if leftover:   # the program's processes outlived the sweep (RLIMIT_NPROC, kill(-1) rounds): its 0, not a retry
        result.update(success=0, valid=0)
        diagnostics["verification_error"] = "processes of the program's user survived kill(-1)"
    (out / "reward.txt").write_text(str(result["success"]) + "\n")
    (out / "reward.json").write_text(json.dumps(result, indent=2))
    (out / "diagnostics.json").write_text(json.dumps(diagnostics, indent=2))
    return result


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--sport", required=True, help="the adapter: tools/fullsim/sports/<sport>.py")
    p.add_argument("--policy", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--level", type=int, required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--dev-root", type=Path)
    p.add_argument("--wall-limit", type=float, help="default: the adapter's MATCH_WALL_S")
    p.add_argument("--slowdown", type=float, help="default: the adapter's SLOWDOWN (the twin's)")
    p.add_argument("--unsafe-local", action="store_true")
    args = p.parse_args()
    result = evaluate(
        args.policy,
        args.out,
        sport=args.sport,
        level=args.level,
        seed=args.seed,
        dev_root=args.dev_root,
        wall_limit=args.wall_limit,
        slowdown=args.slowdown,
        unsafe_local=args.unsafe_local,
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
