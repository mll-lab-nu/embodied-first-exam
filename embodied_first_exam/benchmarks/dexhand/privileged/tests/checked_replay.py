"""The verifier's replay: the family's replay.py, run in this fresh process, with the frozen start checked.

Every Session the replay builds (and every Session.reset() after the build) must be at the frozen instance's start
state for its hand: Session.state_sha() equal to instance.json `start_state_sha[<hand>]`, recorded from a fresh build.
A scene that starts anywhere else is no replay of this task (PROTOCOL H.4, `instance_mismatch`, an infrastructure
failure, never the agent's 0): this process writes that verdict to replay.py's --out file and exits 0 without
running a row. Arguments are replay.py's.
"""

from __future__ import annotations

import json
from pathlib import Path
import runpy
import sys

HERE = Path(__file__).resolve().parent


class InstanceMismatch(Exception):
    pass


def reference(hand: str) -> str:
    """instance.json's start-state hash for this hand ("" when it records none: a mismatch too)."""
    try:
        record = json.loads((HERE / "instance.json").read_text()).get("start_state_sha")
    except (OSError, ValueError, AttributeError):
        record = None
    value = record.get(hand) if isinstance(record, dict) else None
    return value if isinstance(value, str) else ""


def check(session) -> None:
    hand = str(getattr(session, "hand", "sharpa") or "sharpa")
    got, want = session.state_sha(), reference(hand)
    if got != want:
        raise InstanceMismatch(json.dumps({"hand": hand, "start_sha": got, "instance_start_sha": want}))


def install() -> None:
    """Wrap runtime.Session (the family's own) so that its build and each later reset are checked."""
    sys.path.insert(0, str(HERE))
    import runtime

    cls = runtime.Session
    build, reset = cls.__init__, cls.reset

    def checked_init(self, *args, **kwargs):
        build(self, *args, **kwargs)
        check(self)
        self._rcb_built = True

    def checked_reset(self, *args, **kwargs):
        out = reset(self, *args, **kwargs)
        if getattr(self, "_rcb_built", False):   # the reset inside the build is checked once the build is done
            check(self)
        return out

    cls.__init__, cls.reset = checked_init, checked_reset


def main() -> int:
    argv = sys.argv[1:]
    out = argv[argv.index("--out") + 1] if "--out" in argv and argv.index("--out") + 1 < len(argv) else None
    install()
    sys.argv = [str(HERE / "replay.py"), *argv]
    try:
        runpy.run_path(str(HERE / "replay.py"), run_name="__main__")
    except InstanceMismatch as exc:
        detail = json.loads(str(exc))
        verdict = {"success": False, "instance_mismatch": 1, "bad_trajectory": 0, "state_sha": "", "video": False,
                   "reason": "instance_mismatch", **detail,
                   "error": f"the scene started at {detail['start_sha']}, the frozen instance records "
                            f"{detail['instance_start_sha'] or 'no start state for this hand'}"}
        if out:
            Path(out).write_text(json.dumps(verdict, sort_keys=True))
        print(f"[checked_replay] instance_mismatch: {verdict['error']}", file=sys.stderr, flush=True)
        return 0
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
