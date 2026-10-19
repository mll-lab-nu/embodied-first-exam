"""Run a submitted program against a fresh frozen match, then replay trusted logs.

No hostile-code containment is claimed: same-uid processes share filesystem access.
The reference source must remain clean; sandbox objects never enter the formal world.
"""

from __future__ import annotations

import argparse
import json
import os
import select
import signal
import subprocess
import sys
import time
from pathlib import Path

from .session import FINISHED, FROZEN, ROOT, UNIT_OVER, Refused, Session, plain, plugin

PROTECTED = ("core", "sports/tabletennis", "bodies", "skilleval", "renderers")


def check_frozen():
    known = subprocess.run(["git", "cat-file", "-e", FROZEN + "^{commit}"], cwd=ROOT, capture_output=True, check=False)
    if known.returncode:  # a shallow checkout (CI) does not hold the pinned commit: nothing to compare with
        print(f"tt_fullsim: frozen commit {FROZEN[:12]} not in this checkout; source check skipped", file=sys.stderr)
        return
    result = subprocess.run(["git", "diff", "--quiet", FROZEN, "--", *PROTECTED], cwd=ROOT, check=False)
    if result.returncode:
        raise RuntimeError("frozen simulation source differs from the pinned revision; use a clean formal checkout")
    # -I removes ambient PYTHONPATH; same-user filesystem attacks still require containers.


def child_env():
    keys = ("PATH", "LANG", "LC_ALL", "LD_LIBRARY_PATH")
    env = {k: os.environ[k] for k in keys if k in os.environ}
    env.update(
        MUJOCO_GL="disable",
        OPENBLAS_NUM_THREADS="1",
        OMP_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
        PYTHONDONTWRITEBYTECODE="1",
    )
    return env


class Program:
    def __init__(self, path, output, initial, *, worker_root=None, identity=None, workdir=None):
        self.stderr = (output / "policy.stderr").open("wb")
        self.p = subprocess.Popen(
            [sys.executable, "-I", str((worker_root or ROOT) / "tools/tt_fullsim/worker.py"), str(path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.stderr,
            cwd=workdir or output,
            user=identity,
            group=identity,
            extra_groups=[] if identity is not None else None,
            start_new_session=True,
            env=child_env(),
            bufsize=0,
        )
        self.buf = b""
        try:
            deadline = time.monotonic() + 30
            self.send(initial)
            while time.monotonic() < deadline:
                message = self.poll()
                if message is not None:
                    if message != {"ready": True}:
                        raise RuntimeError("invalid program startup response")
                    return
                time.sleep(0.002)
            raise TimeoutError("program load exceeded 30s")
        except BaseException:
            self.close()
            raise

    def send(self, obj, timeout=5):
        payload = (json.dumps(obj, allow_nan=False) + "\n").encode()
        if len(payload) > 1024 * 1024:
            raise ValueError("policy view exceeds 1 MiB")
        fd = self.p.stdin.fileno()
        os.set_blocking(fd, False)
        deadline = time.monotonic() + timeout
        offset = 0
        while offset < len(payload):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("program did not read its input within the call deadline")
            if self.p.poll() is not None:
                raise BrokenPipeError("program exited before consuming input")
            if not select.select([], [fd], [], min(remaining, 0.05))[1]:
                continue
            try:
                offset += os.write(fd, payload[offset:])
            except BlockingIOError:
                continue

    def poll(self):
        if select.select([self.p.stdout], [], [], 0)[0]:
            data = os.read(self.p.stdout.fileno(), 65536)
            if not data:
                raise RuntimeError(f"program exited ({self.p.poll()}); see policy.stderr")
            self.buf += data
        if len(self.buf) > 1024 * 1024:
            raise ValueError("program response exceeds 1 MiB")
        if b"\n" in self.buf:
            line, self.buf = self.buf.split(b"\n", 1)
            return json.loads(line, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
        if self.p.poll() is not None:
            raise RuntimeError(f"program exited ({self.p.returncode}); see policy.stderr")
        return None

    def close(self):
        # start_new_session gives this exact child PID its own process group.
        # Signal it even if the main policy exited, so forked helpers cannot linger.
        try:
            os.killpg(self.p.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            self.p.wait(timeout=3)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(self.p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            self.p.wait()
        try:
            os.killpg(self.p.pid, signal.SIGKILL)  # helpers may ignore TERM after the main process exits
        except ProcessLookupError:
            pass
        self.p.stdin.close()
        self.p.stdout.close()
        self.stderr.close()


def replay(directory):
    check_frozen()
    from core.episode import read_rows
    from core.episode import replay as core_replay
    from core.spec import load

    path = ROOT / "sports/tabletennis/plugin.py"
    result = core_replay(plugin().SPORT, read_rows(directory / "episode.jsonl"), decl=load(path))
    (directory / "replay_check.json").write_text(json.dumps(plain(result), indent=2))
    return result


def run(args):
    check_frozen()
    output = Path(args.out).resolve()
    output.mkdir(parents=True, exist_ok=False)
    session = Session(args.level, args.seed, log_dir=output)
    initial = session.state()
    program = None
    reason = "step_cap"
    error = None
    calls = rejected = dropped = stalls = 0
    max_lag = 0.0
    pending = None
    next_request = 0
    step_wall = 0.01 * args.slowdown
    launched = started = time.monotonic()
    next_tick = started + step_wall
    review_since = None
    decisions = (output / "decisions.jsonl").open("w")
    try:
        program = Program(Path(args.program).resolve(), output, {"spec": session.spec(), "setting": args.timing})
        started = time.monotonic()  # preparation time is separately reported, clock starts after program load
        next_tick = started + step_wall
        while session.match.phase().state != FINISHED and session.match.k < args.max_steps:
            now = time.monotonic()
            if now - launched > args.wall_limit:
                reason = "wall_timeout"
                break
            phase = session.match.phase().state
            if phase == UNIT_OVER:
                review_since = now if review_since is None else review_since
                if now - review_since > 300:
                    reason = "review_timeout"
                    break
            else:
                review_since = None
            if pending is None and (session.match.k >= next_request or phase == UNIT_OVER):
                program.send(session.state())
                pending = (now, session.match.unit(), session.match.k)
                calls += 1
            message = program.poll()
            if message is not None:
                if pending is None or not isinstance(message, dict) or set(message) != {"command"}:
                    raise ValueError("one command response required per observation")
                received, unit, seen = pending
                pending = None
                command = message["command"]
                before = session.match.k
                row = {
                    "seen_step": seen,
                    "effect_step": before,
                    "command": command,
                    "decision_wall_s": time.monotonic() - received,
                }
                if unit != session.match.unit():
                    dropped += 1
                    row["dropped"] = "unit ended while deciding"
                elif command is not None:
                    try:
                        if not isinstance(command, dict):
                            raise TypeError("command must be an object or null")
                        if command.get("type") == "ready":
                            session.ready()
                            review_since = None
                        else:
                            session.act(command)
                        row["accepted"] = True
                    except (Refused, ValueError, TypeError, KeyError) as exc:
                        rejected += 1
                        row["rejected"] = str(exc)
                decisions.write(json.dumps(row) + "\n")
                next_request = session.match.k + args.every
            if pending and now - pending[0] > args.call_timeout:
                raise TimeoutError("program decision exceeded call timeout")
            if session.match.phase().state == UNIT_OVER:
                next_tick = time.monotonic() + step_wall  # review freezes the world under original sport rules
            elif args.timing == "step":
                if pending is None:
                    session.step(args.every)
            elif time.monotonic() >= next_tick:
                lag = time.monotonic() - next_tick
                max_lag = max(max_lag, lag)
                # As in realtime infrastructure, expose stalls rather than simulating an unbounded burst.
                if lag > 0.5:
                    stalls += 1
                    next_tick = time.monotonic()
                session.step()
                next_tick += step_wall
            time.sleep(0.001 if args.timing == "wallclock" or pending else 0)
        else:
            if session.match.phase().state == FINISHED:
                reason = "match_over"
    except Exception as exc:  # noqa: BLE001 -- submitted programs must leave an auditable verdict
        error = f"{type(exc).__name__}: {exc}"
        reason = "program_error"
    finally:
        if program:
            program.close()
        decisions.close()
        session.finish_log(reason)
    live = session.state()
    (output / "live.json").write_text(json.dumps(live, indent=2))
    finished_at = time.monotonic()
    # The replay subprocess imports fresh frozen code and consumes only the runner-owned journal.
    result = subprocess.run(
        [sys.executable, "-m", "tools.tt_fullsim.runner", "replay", str(output)],
        cwd=ROOT,
        env=child_env(),
        capture_output=True,
        check=False,
        text=True,
        timeout=600,
    )
    replayed = json.loads((output / "replay_check.json").read_text()) if result.returncode == 0 else None
    deterministic = bool(
        replayed
        and replayed["state_sha"] == live["state_sha"]
        and replayed["scores"] == live["scores"]
        and replayed["k"] == session.match.k
    )
    completed = reason == "match_over" and live["finished"]
    summary = {
        "setting": "fullsim-program-pilot/0.1",
        "timing": args.timing,
        "slowdown": args.slowdown,
        "frozen_commit": FROZEN,
        "cfg": session.cfg.to_json(),
        "reason": reason,
        "error": error,
        "initial_state_sha": initial["state_sha"],
        "final_state_sha": live["state_sha"],
        "scores": live["scores"],
        "steps": session.match.k,
        "calls": calls,
        "rejected": rejected,
        "dropped": dropped,
        "wall_s": time.monotonic() - launched,
        "program_load_wall_s": started - launched,
        "match_clock_wall_s": finished_at - started,
        "replay_wall_s": time.monotonic() - finished_at,
        "stalls": stalls,
        "max_lag_s": max_lag,
        "deterministic": deterministic,
        "valid": bool(completed and deterministic and error is None),
        "success": bool(completed and deterministic and error is None and replayed["winner"] == "A"),
        "replay_error": result.stderr[-2000:] if result.returncode else None,
        "isolation": "fresh world + separate program/replay processes; NOT hostile-code containment",
        "instance_source": {(2, 22): "First Exam TT i01", (3, 12): "First Exam TT i02"}.get(
            (args.level, args.seed), "public development instance on the frozen sport; not a First Exam task"
        ),
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary))
    return summary


def main():
    if hasattr(os, "sched_getaffinity"):
        os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:4])
    parser = argparse.ArgumentParser(__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    rp = commands.add_parser("replay")
    rp.add_argument("directory", type=Path)
    runp = commands.add_parser("run")
    runp.add_argument("--program", required=True)
    runp.add_argument("--out", required=True)
    runp.add_argument("--level", type=int, choices=(1, 2, 3, 4), required=True)
    runp.add_argument("--seed", type=int, default=22)
    runp.add_argument("--timing", choices=("wallclock", "step"), default="wallclock")
    runp.add_argument("--slowdown", type=float, default=10)
    runp.add_argument("--wall-limit", type=float, default=7200)
    runp.add_argument("--call-timeout", type=float, default=5)
    runp.add_argument("--max-steps", type=int, default=200000)
    runp.add_argument("--every", type=int, default=5)
    args = parser.parse_args()
    if args.command == "replay":
        print(json.dumps(replay(args.directory)))
    else:
        if args.slowdown <= 0 or args.every < 1 or args.max_steps < 1 or args.wall_limit <= 0:
            parser.error("positive slowdown/every/max-steps/wall-limit required")
        run(args)


if __name__ == "__main__":
    main()
