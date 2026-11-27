"""The sim service's entry point with the match extension of eai-standard/3.0 (docs/protocol/standard_mode.md Part 5):

    python3 -m eai_std.serve            (cwd = the directory holding core/ and eai_std/; core/serve.py's environment)

EAI_STD_CLOCK = realtime (default; the realtime match, core/realtime.py, as core/launch.py runs it) | lockstep (the
standard twin, core/lockstep.py) | turn (a turn-based sport, sport.protocol "turn": core/serve.py builds core/turn.py; the
setting only names it).
The match service is built and run by the core's own entry point (core/serve.py main, or core/lockstep.py main), unchanged;
this module only wraps the HTTP server that entry point makes: one port, two APIs.

  /<SEAT>/<call>       the core's seat API (the `game` command), untouched
  /spec /status /observe /submit, /start /ready /say /team    eai-standard/3.0 + the match extension (eai_std/adapter.py)

Every seat must be unmetered (PLAYER_MODE_<seat> = unmetered) or built-in (RO_BUILTIN_SEATS), as core/lockstep.py requires:
this entry starts no metering proxy (core/launch.py would start one only for a metered seat)."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from . import rcb1
from .adapter import MAX_REQUEST_BYTES, Adapter, BadRequest

STD_GET = {"spec", "status", "team"}
STD_POST = {"observe", "submit", "start", "ready", "say", "team"}
NOT_OFFERED = {"finish", "reset", "kinematics"}


def install(srv, svc, seats, hosts):
    """Give the core's server (core/http.py make_server) the standard endpoints, with the same seat check and the same
    per-seat request budget (4 open, 20 per second) as the seat API."""
    from core import http as core_http
    adapter = Adapter(svc)
    seat = adapter.seat
    Base = srv.RequestHandlerClass

    class Handler(Base):
        def dispatch(self, post):
            adapter.first_request()
            path = self.path.partition("?")[0]
            bits = path.strip("/").split("/")
            if len(bits) == 2:                                   # /<SEAT>/<call>: the core's own API
                return super().dispatch(post)
            ep = bits[0] if len(bits) == 1 else ""
            if ep in NOT_OFFERED or ep not in (STD_POST if post else STD_GET):
                self.drain()
                return self.send(404, {"error": f"unknown endpoint /{ep}"
                                       + (" (not offered in a match: its rules end the episode)" if ep == "finish" else "")})
            if not core_http.seat_allowed(seat, self.client_address[0], hosts):
                self.drain()
                return self.send(403, {"error": "seat not authorized"})
            if not self.server.admit(seat):
                return self.too_many()
            try:
                self.std(ep, post)
            finally:
                self.server.release(seat)

        def drain(self):
            try:
                n = int(self.headers.get("Content-Length", "0"))
                if 0 < n <= 65536:
                    self.rfile.read(n)
            except (ValueError, OSError):
                pass

        def send_rcb1(self, code, meta, parts):
            raw = rcb1.encode(meta, parts)
            self.send_response(code)
            self.send_header("Content-Type", "application/x-rcb1")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            try:
                self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def body(self) -> tuple[bytes, str]:
            try:
                n = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                raise BadRequest("bad Content-Length")
            if n < 0:
                raise BadRequest("negative Content-Length")
            if n > MAX_REQUEST_BYTES:
                raise BadRequest(f"request too large (at most {MAX_REQUEST_BYTES} bytes)", 413)
            self.connection.settimeout(60)
            return (self.rfile.read(n) if n else b""), self.headers.get("Content-Type", "")

        def fields(self, raw, ctype) -> dict:
            if ctype.startswith("application/x-rcb1"):
                try:
                    meta, _parts = rcb1.decode(raw)
                except Exception:  # noqa: BLE001
                    raise BadRequest("malformed RCB1 body")
                return meta if isinstance(meta, dict) else {}
            try:
                out = json.loads(raw or b"{}")
            except ValueError:
                raise BadRequest("malformed JSON body")
            if not isinstance(out, dict):
                raise BadRequest("a JSON object is required")
            return out

        def std(self, ep, post):
            rcb_req = False
            try:
                if not post:
                    if ep == "spec":
                        return self.send(200, adapter.spec())
                    if ep == "status":
                        return self.send(200, adapter.status())
                    since = 0
                    for key, val in [p.partition("=")[::2] for p in self.path.partition("?")[2].split("&") if p]:
                        if key == "since":
                            if not val.isdigit() or len(val) > 12:
                                raise BadRequest("since must be a non-negative integer")
                            since = int(val)
                    code, out = adapter.ext("team", {"since": since})
                    return self.send(code, out)
                raw, ctype = self.body()
                rcb_req = ctype.startswith("application/x-rcb1")
                if ep == "submit":
                    req = adapter.build_rows(adapter.parse_submit(raw, ctype))
                    code, meta, parts = adapter.submit(req)
                    return self.send_rcb1(code, meta, parts) if code == 200 else self.send(code, meta)
                hdr = self.fields(raw, ctype)
                if ep == "observe":
                    code, meta, parts = adapter.observe(hdr)
                    return self.send_rcb1(code, meta, parts) if code == 200 else self.send(code, meta)
                code, out = adapter.ext(ep, hdr)
                if rcb_req:
                    return self.send_rcb1(code, {**out.pop("meta"), "reply": out}, [])
                return self.send(code, out)
            except BadRequest as exc:
                err = {"error": str(exc)}
                if exc.code == 409:
                    err.update(done=True, reason=svc.reason, match_over=True)
                adapter.log(ev="refused", ep=ep, code=exc.code, error=str(exc)[:300])
                return self.send(exc.code, err)
            except Exception as exc:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                adapter.log(ev="error", ep=ep, error=f"{type(exc).__name__}: {str(exc)[:300]}")
                return self.send(500, {"error": "technical failure (eai_std)"})

    srv.RequestHandlerClass = Handler
    srv.eai_std = adapter
    print(f"eai_std: {adapter.protocol} on the same port, seat {seat}, clock {adapter.clock}", flush=True)
    return adapter


def main():
    import core.serve as core_serve
    seats = os.environ.get("RO_SEATS", "A,B").split(",")
    builtin = {x.split("=", 1)[0].strip() for x in os.environ.get("RO_BUILTIN_SEATS", "").split(",") if "=" in x}
    metered = [s for s in seats if s not in builtin
               and os.environ.get(f"PLAYER_MODE_{s}", os.environ.get("RCB_PLAYER_MODE", "model")) != "unmetered"]
    if metered:
        raise SystemExit(f"eai_std.serve: seats {metered} are metered; this entry starts no metering proxy")
    data = Path(os.environ.get("RCB_DATA", "/data"))
    data.mkdir(exist_ok=True)
    for s in seats:                                       # core/launch.py's files (no proxy writes them)
        open(data / f"think_calls_{s}.jsonl", "a").close()
    orig = core_serve.make_server

    def make_server(svc, seats_, hosts, port=8000):
        srv = orig(svc, seats_, hosts, port)
        install(srv, svc, seats_, hosts)
        return srv
    core_serve.make_server = make_server
    clock = os.environ.get("EAI_STD_CLOCK", "realtime")
    if clock == "lockstep":
        from core import lockstep
        lockstep.main()
    elif clock in ("realtime", "turn"):
        core_serve.main()
    else:
        raise SystemExit(f"EAI_STD_CLOCK must be realtime, lockstep or turn, not {clock!r}")


if __name__ == "__main__":
    main()
