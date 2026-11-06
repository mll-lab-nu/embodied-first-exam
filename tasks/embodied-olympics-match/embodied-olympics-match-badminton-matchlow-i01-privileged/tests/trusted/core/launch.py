"""Trusted launcher of a task's sim container: one metering proxy per seat (the unchanged think_proxy.py of players/
metering, copied by the generator to metering/think_proxy.py next to core/; seat i on port 18090 + i; model
credentials stay in this container) and the match service (core.serve).

A seat in player mode "unmetered" (PLAYER_MODE_<seat>, core 0.2.27) gets no proxy: its runner meters the model.

Per-seat settings of a seat's proxy (the runner sets them; the compose file passes them through):
  RO_SEAT_SELECT_<seat> = "VAR=SOURCE,..."   VAR takes SOURCE's value (e.g. a second account's credential)
  RO_SEAT_ENV_<VAR>_<seat> = value          a non-empty value replaces VAR (e.g. the route of OpenAI-style calls)
After the mapping a proxy keeps no RO_SEAT_SELECT_* / RO_SEAT_ENV_* and no other seat's per-seat variable (<VAR>_<other
seat> for every per-seat VAR, PLAYER_MODE_<other seat>): a seat's proxy never holds another seat's credentials. A seat
on route "chatgpt" (THINK_OPENAI_ROUTE: a ChatGPT subscription) keeps only the credentials given to it alone (non-empty
RO_SEAT_ENV_<VAR>_<seat>); every task-wide credential (e.g. the OpenRouter or Azure key) is dropped from its proxy.
A credential is a per-seat VAR that is not a THINK_* setting.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SEATS = os.environ.get("RO_SEATS", "A,B").split(",")
DATA = os.environ.get("RCB_DATA", "/data")
PROXY = ROOT.parent / os.environ.get("RO_METER_PROXY", "metering/think_proxy.py")


def seat_env(seat: str, env: dict, seats=None) -> dict:
    """The environment of `seat`'s metering proxy."""
    seats = seats or SEATS
    env = dict(env)
    env["THINK_CLIENT_HOST"] = "seat_" + seat.lower() if len(seats) > 1 else env.get("THINK_CLIENT_HOST", "player")
    env["THINK_USAGE_FILE"] = f"{DATA}/think_usage_{seat}.json"
    env["THINK_CALLS_FILE"] = f"{DATA}/think_calls_{seat}.jsonl"
    for pair in filter(None, env.get(f"RO_SEAT_SELECT_{seat}", "").split(",")):
        var, _, src = pair.partition("=")
        if var and src in env:
            env[var] = env[src]
    own = set()                                             # the VARs given to this seat alone
    for key in [k for k in env if k.endswith("_" + seat) and k.startswith("RO_SEAT_ENV_")]:
        if env[key]:
            own.add(key[len("RO_SEAT_ENV_"):-len(seat) - 1])
            env[key[len("RO_SEAT_ENV_"):-len(seat) - 1]] = env[key]
    per_seat = {"PLAYER_MODE"}                              # every VAR set per seat (any seat's RO_SEAT_ENV_<VAR>_<s>)
    for s in seats:
        per_seat |= {k[len("RO_SEAT_ENV_"):-len(s) - 1] for k in env
                     if k.startswith("RO_SEAT_ENV_") and k.endswith("_" + s) and len(k) > len("RO_SEAT_ENV_") + len(s) + 1}
    others = [s for s in seats if s != seat]
    for k in list(env):
        if k.startswith(("RO_SEAT_ENV_", "RO_SEAT_SELECT_")) or any(k == f"{v}_{o}" for o in others for v in per_seat):
            del env[k]
    if env.get("THINK_OPENAI_ROUTE", "").strip().lower() == "chatgpt":   # a subscription seat: its own credentials only
        for k in per_seat - own:
            if not k.startswith("THINK_") and k != "PLAYER_MODE":
                env.pop(k, None)
    return env


def seat_mode(seat: str, env=None) -> str:
    """The seat's player mode, as core.seats.Seat reads it."""
    env = os.environ if env is None else env
    return env.get(f"PLAYER_MODE_{seat}", env.get("RCB_PLAYER_MODE", "model"))


def main():
    if len(sys.argv) > 1:                       # one seat's proxy
        seat = sys.argv[1]
        env = seat_env(seat, dict(os.environ))
        os.execve(sys.executable, [sys.executable, str(PROXY), str(18090 + SEATS.index(seat))], env)
    Path(DATA).mkdir(exist_ok=True)
    for s in SEATS:
        open(f"{DATA}/think_calls_{s}.jsonl", "a").close()
    procs = []
    try:
        builtin = {x.split("=", 1)[0].strip() for x in os.environ.get("RO_BUILTIN_SEATS", "").split(",") if "=" in x}
        metered = [s for s in SEATS if seat_mode(s) != "unmetered" and s not in builtin]   # core 0.2.31: no proxy for
        # a built-in seat (core/builtin_seat.py: no model plays it)
        if PROXY.exists():
            for s in metered:                   # an unmetered seat (core 0.2.27) gets no proxy
                procs.append(subprocess.Popen([sys.executable, __file__, s]))
        elif metered:
            print(f"no metering proxy at {PROXY}: model seats cannot play", file=sys.stderr, flush=True)
        procs.append(subprocess.Popen([sys.executable, "-m", "core.serve"], cwd=ROOT.parent))
        while all(p.poll() is None for p in procs):
            time.sleep(.5)
        raise RuntimeError("a required service exited")
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()
        for p in procs:
            try:
                p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                p.kill()


if __name__ == "__main__":
    main()
