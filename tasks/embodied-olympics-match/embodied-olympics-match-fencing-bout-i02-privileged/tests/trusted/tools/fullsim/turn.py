"""The turn-based twins' layer over the generic full-simulator setting (tools/fullsim): the twin is a turn sport on the
core's TurnService (protocol eai-standard-turn/1.0: one action per turn, a review after each action that does not end
the match, a chess clock per seat). tools/fullsim/formal.py plays a realtime service; this task's own file plays the
twin's own TurnService instead and keeps everything else of formal.evaluate (the sanitized submission, the program as
nobody in its own process, the public development copy, the one fresh-process replay, the verdict). Nothing of
tools/fullsim/formal.py, session.py or the sport changes.

- `evaluate(...)`: the formal bout. The program is called once per decision the service asks of seat A: on its turn
  (`state.phase` "playing": one action) and at each review after its action (`state.phase` "unit_over": `{"type":
  "ready"}`). The twin's chess clock (CLOCK_S, the adapter's CLOCK_S) runs while the program computes on its turn,
  as in the twin; out of time loses the bout. Each exchange is limited as in formal.evaluate (5 s).
- `TurnSession`: tools.fullsim.session.Session for a turn sport: `act(command)` plays the decision at once (a turn sport
  has no world steps between decisions); `step()` and `ready()` are not needed.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
import threading
import time
from pathlib import Path

from core.sport import Refused
from core.turn import TurnService
from tools.fullsim.adapter import load
from tools.fullsim.formal import NoRenderSport, _ProgramSimError, agent_sim_error, brief, commands_of
from tools.fullsim.program import Program, end_uid_processes, sanitize
from tools.fullsim.session import FROZEN, ROOT, Session, match_config, plain, plugin, plugin_path

EXCHANGE_S = 5  # each exchange with the program (formal.evaluate's limit)


class FullSimTurnService(TurnService):
    """The twin's TurnService; explicit full-state observation adapter (the sport's truth hook), no images."""

    truth = None  # set per instance: the adapter's truth(match)

    def observation(self, seat, query=None, since=None):
        obs = super().observation(seat, query, since)
        obs["truth"] = plain(self.truth(self.m))
        return obs

    def camera_job(self, seat, query=None):
        return None, {}

    def draw(self, seat, job):
        return None

    def reply_job(self, seat, cmd, info):
        return None


def call(service, ep, body):
    """A seat-A call as over HTTP (the service's guarded handler: its lock, its clock accounting, final.json)."""
    try:
        return service.routes(True)[ep]("A", dict(body))
    except Refused as exc:
        return exc.code, {"error": str(exc)}


def evaluate(policy, out, *, sport, level, seed, slowdown=None, wall_limit=None, unsafe_local=False, dev_root=None):
    ad = load(sport)
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
        CLOCK_S=str(ad.CLOCK_S),
        RO_REPLAY_TIMEOUT_S=str(ad.REPLAY_TIMEOUT_S),
        MUJOCO_GL="disable",
    )
    started = time.monotonic()
    program = service = None
    reason = error = None
    leftover = False
    trusted_failure = None
    scratch_ready = False
    stage = "program"
    refusals = calls = 0
    public = Path(tempfile.mkdtemp(prefix="turn-policy-"))
    public.chmod(0o755)
    try:
        sanitize(Path(policy).absolute(), public / "policy")
        scratch = public / "scratch"
        scratch.mkdir(mode=0o700)
        scratch_ready = True
        if not unsafe_local:
            os.chown(scratch, 65534, 65534)
        stage = "trusted"
        cfg = match_config(ad, level, seed)
        service = FullSimTurnService(NoRenderSport(plugin(ad.SPORT).SPORT), str(plugin_path(ad.SPORT)), cfg,
                                     out / "match")
        service.truth = ad.truth
        service.write_final()
        threading.Thread(target=service.loop, daemon=True).start()
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
            cpu_s=int(wall_limit) + 30,
        )
        stage = "trusted"
        code, reply = call(service, "start", {})
        if code != 200:
            trusted_failure = f"trusted start failed: {code} {reply}"
            raise RuntimeError(trusted_failure)
        decisions = (out / "decisions.jsonl").open("w")
        while service.phase != "over":
            if time.monotonic() - started >= wall_limit:
                reason = "policy_wall_timeout"
                break
            stage = "trusted"
            code, observed = call(service, "observe", {})
            if code != 200:
                if service.phase == "over":
                    break
                trusted_failure = f"trusted observe failed: {code}"
                raise RuntimeError(trusted_failure)
            st = observed["state"]
            truth = st.pop("truth")
            if not st.get("your_turn"):  # a single side is always on turn while the bout runs
                call(service, "wait", {"timeout_s": 1})
                continue
            view = {
                "state": {**st, "service_phase": st["phase"], "phase": "unit_over" if st.get("awaiting_review") else "playing"},
                "truth": truth,
                "scores": service.m.scores(),
                "observation": observed.get("observation") or {},
            }
            deadline = time.monotonic() + EXCHANGE_S
            stage = "program"
            program.send(view, timeout=EXCHANGE_S)
            calls += 1
            message = None
            while message is None and service.phase != "over":
                message = program.poll()
                if time.monotonic() > deadline:
                    raise TimeoutError(f"program call exceeded {EXCHANGE_S}s")
                time.sleep(0.001)
            if service.phase == "over":
                break
            if not isinstance(message, dict) or set(message) != {"command"}:
                raise ValueError("one command response per observation required")
            cmds = commands_of(message["command"], ad.MAX_COMMANDS)
            if not cmds:
                time.sleep(0.01)  # nothing this time: the seat's chess clock runs on
                continue
            for cmd in cmds:
                if cmd.get("type") == "ready":
                    code, reply = call(service, "ready", {"why": "program review", "plan": "continue same policy"})
                else:
                    code, reply = call(service, "act", cmd)
                refusals += int(code != 200)
                decisions.write(json.dumps(plain({"seen": st.get("phrase"), "command": cmd, "code": code,
                                                  "reply": brief(reply)})) + "\n")
        decisions.close()
    except Exception as exc:  # noqa: BLE001 -- untrusted program failures become an explicit zero, not a forged win
        reason, error = "policy_error", f"{type(exc).__name__}: {exc}"
        if trusted_failure is None and (stage == "trusted" or (program is None and isinstance(exc, OSError)
                                                                and stage == "program" and scratch_ready)):
            trusted_failure = f"{type(exc).__name__}: {exc}"
    finally:
        if program is not None:
            try:
                program.close()
            except Exception:  # noqa: BLE001
                pass
        if not unsafe_local:
            leftover = not end_uid_processes(65534)
        if service is not None and service.phase != "over":
            service.collect()
        if service is not None:
            deadline = time.monotonic() + ad.REPLAY_TIMEOUT_S + 50
            with service.cond:
                while not service.finalized and time.monotonic() < deadline:
                    service.cond.wait(timeout=1.0)
        try:
            shutil.rmtree(public, ignore_errors=True)
        except Exception:  # noqa: BLE001
            pass
    result = {
        "success": 0, "valid": 0, "deterministic": 0, "infra_error": 0, "policy_error": int(error is not None),
        "calls": calls, "refused": refusals, "level": level, "seed": seed, "replays": 0,
        "isolation_checked": int(not unsafe_local), "processes_left": int(leftover),
    }
    diagnostics = {
        "sport": ad.SPORT, "reason": reason, "error": error, "frozen_commit": FROZEN,
        "timing": "original core.turn.TurnService (chess clock CLOCK_S); full-state/no-render adapter",
        "wall_s": time.monotonic() - started, "unsafe_local": unsafe_local,
    }
    final = {}
    try:
        if service is not None:
            final = json.loads((out / "match/final.json").read_text())
            if not final.get("graded_ready"):
                raise ValueError("the service's final.json is not graded yet (replay unfinished)")
            if agent_sim_error(final):
                raise _ProgramSimError
            rep = json.loads((out / "match/replay_check.json").read_text())
            equal = bool(
                final["deterministic"]
                and rep.get("state_sha") == final["state_sha"]
                and rep.get("scores") == final["scores"]
                and rep.get("k") == final["steps"]
                and rep.get("winner") == final["match_winner"]
                and rep.get("commands_sha") == final["commands_sha"]
            )
            valid = bool(final["valid_trial"] and final["reason"] == "match_over" and equal and not error and not reason)
            other = next((s for s in final["scores"] if s != "A"), None)   # the scripted side (fencing: B)
            result.update(
                success=int(valid and final["match_winner"] == "A"),
                valid=int(valid),
                deterministic=int(equal),
                infra_error=int((bool(final["errors"]) and not agent_sim_error(final)) or not equal
                                or trusted_failure is not None),
                replays=1,
                points_for=final["scores"]["A"],
                points_against=final["scores"].get(other) if other else None,
                steps=final["steps"],
            )
            diagnostics.update(final_reason=final["reason"], source_sha=final["source_sha"],
                               continuous=final.get("continuous"), clock_used_s=final.get("clock_used_s"))
    except _ProgramSimError:
        result.update(success=0, valid=1, infra_error=int(trusted_failure is not None), replays=1)
        diagnostics.update(final_reason=final.get("reason"), agent_sim_error=1)
    except Exception as exc:  # noqa: BLE001 -- a verification failure is an infra error, never a crash
        result.update(success=0, valid=0, infra_error=1)
        diagnostics["verification_error"] = f"{type(exc).__name__}: {exc}"
    if trusted_failure is not None:
        result.update(success=0, valid=0, infra_error=1)
        diagnostics["trusted_failure"] = trusted_failure
    if leftover:
        result.update(success=0, valid=0)
        diagnostics["verification_error"] = "processes of the program's user survived kill(-1)"
    (out / "reward.txt").write_text(str(result["success"]) + "\n")
    (out / "reward.json").write_text(json.dumps(result, indent=2))
    (out / "diagnostics.json").write_text(json.dumps(diagnostics, indent=2))
    return result


class TurnSession(Session):
    """A development bout of a turn sport: act(command) plays your decision (and the scripted side's answer) at once."""

    def step(self, n=1):
        raise ValueError("a turn sport has no world steps between decisions: act() plays the next decision")

    def ready(self):
        return None  # the turn service's review after each action is a formality here


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--sport", required=True)
    p.add_argument("--policy", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--level", type=int, required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--dev-root", type=Path)
    p.add_argument("--wall-limit", type=float, help="default: the adapter's MATCH_WALL_S")
    p.add_argument("--unsafe-local", action="store_true")
    a = p.parse_args()
    print(json.dumps(evaluate(a.policy, a.out, sport=a.sport, level=a.level, seed=a.seed, dev_root=a.dev_root,
                              wall_limit=a.wall_limit, unsafe_local=a.unsafe_local)))


if __name__ == "__main__":  # the developer self-test: python -m tools.fullsim.turn (tools.fullsim.formal's arguments)
    main()
