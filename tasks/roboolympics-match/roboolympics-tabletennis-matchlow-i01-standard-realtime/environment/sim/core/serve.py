"""Entry point of a generated task's sim service: python3 -m core.serve (cwd = the directory holding core/).

Environment: RO_PLUGIN (path of the sport's plugin.py), RO_SPORT, RO_FORMAT, RO_SEATS (e.g. "A,B"), RO_SIDES (e.g.
"A=home,B=home,C=away,D=away"; default: every seat its own side), RO_SEED, RO_SEED_SALT
(a hidden official seed's salt, core 0.2.14: recorded in final.json seed_proof for the verifier), RO_FIRST, RO_SLOWDOWN (realtime), RO_LEVEL
(single), RO_PARAMS (JSON), RO_RENDERER (the players' image renderer), RCB_ACTION_LEVEL, RCB_PLAY, RCB_DATA,
SEAT_HOSTS, RO_BUILTIN_SEATS (core 0.2.31: seats played by a built-in player inside this process, core/builtin_seat.py;
the HTTP layer does not serve them). The runner's own names (DUEL_SEED, FIRST_PLAYER, ...) are mapped onto these by the
task's compose file.
"""
from __future__ import annotations

import json
import os
import signal
import threading
from pathlib import Path

from . import builtin_seat
from .episode import load_plugin
from .http import make_server
from .realtime import RealtimeService
from .sport import MatchConfig
from .turn import TurnService


def config_from_env() -> MatchConfig:
    e = os.environ.get
    level, slow = e("RO_LEVEL"), e("RO_SLOWDOWN")
    sides = dict(x.split("=", 1) for x in e("RO_SIDES", "").split(",") if "=" in x) or None
    return MatchConfig(sport=e("RO_SPORT", ""), format=e("RO_FORMAT", "duel"),
                       seats=tuple(e("RO_SEATS", "A,B").split(",")), seed=int(e("RO_SEED", "1")),
                       first=e("RO_FIRST") or None, slowdown=float(slow) if slow else None,
                       level=int(level) if level else None, action_level=e("RCB_ACTION_LEVEL", "high"),
                       play=e("RCB_PLAY", "program"), params=json.loads(e("RO_PARAMS", "{}")), sides=sides,
                       renderer=e("RO_RENDERER") or None)


def main():
    plugin = os.path.abspath(os.environ["RO_PLUGIN"])
    sport = load_plugin(plugin)
    cfg = config_from_env()
    if cfg.action_level not in ("high", "low") or cfg.play not in ("program", "direct"):
        raise ValueError("RCB_ACTION_LEVEL must be high or low, RCB_PLAY program or direct")
    data = Path(os.environ.get("RCB_DATA", "/data"))
    svc = (RealtimeService if sport.protocol == "realtime" else TurnService)(sport, plugin, cfg, data)
    hosts = dict(x.split("=", 1) for x in os.environ.get("SEAT_HOSTS", "").split(",") if "=" in x)
    signal.signal(signal.SIGUSR1, lambda *a: threading.Thread(target=svc.collect, daemon=True).start())
    svc.write_final()
    (data / "server.pid").write_text(str(os.getpid()))
    threading.Thread(target=svc.loop, daemon=True).start()
    builtin = builtin_seat.parse(os.environ.get("RO_BUILTIN_SEATS"))
    if set(builtin) - set(cfg.seats) or set(builtin) == set(cfg.seats):
        raise ValueError(f"RO_BUILTIN_SEATS {sorted(builtin)}: seats of {list(cfg.seats)}, and not all of them")
    builtin_seat.start(svc, plugin, builtin)
    print(f"{sport.name} {cfg.format} service ready ({svc.protocol_id})", flush=True)
    http_seats = tuple(s for s in cfg.seats if s not in builtin)      # a built-in seat is never served over HTTP
    make_server(svc, http_seats, hosts, int(os.environ.get("RCB_PORT", "8000"))).serve_forever()


if __name__ == "__main__":
    main()
