"""The HTTP layer of an ablation: core/http.py's server and handler unchanged (seat check, budget, body rules), plus
- the two-part paths of the ablation's endpoints: /<seat>/state/entities, /<seat>/state/query and, without the seat,
  /state/entities, /state/query, /finish, /reset, /save_state, /load_state (the only seat served over HTTP);
- RCB_HIDE_SUCCESS: every reply but /spec passes through the sport's hide() before it is sent;
- RCB_STATE_OPS: GET /over (a core from 0.5 on: whether the result is final) is false while a lost match is held for
  a reset or a load."""
from __future__ import annotations

from . import HIDE, OPS
from . import sports

EXTRA = {"state/entities": "state_entities", "state/query": "state_query", "finish": "finish", "reset": "reset",
         "save_state": "save_state", "load_state": "load_state"}


def patch(server, svc, seats):
    base = server.RequestHandlerClass
    http_seats = [s for s in seats]
    hide = sports.hider(svc) if HIDE else None

    class Handler(base):
        def dispatch(self, post):
            path, sep, qs = self.path.partition("?")
            bits = path.strip("/").split("/")
            if OPS and not post and bits == ["over"]:
                return self.send(200, {"over": getattr(svc, "phase", None) == "over" and not svc.abl.held})
            if len(bits) == 3 and bits[0] in http_seats and "/".join(bits[1:]) in EXTRA:
                path = f"/{bits[0]}/{EXTRA['/'.join(bits[1:])]}"
            elif "/".join(bits) in EXTRA and len(http_seats) == 1:
                path = f"/{http_seats[0]}/{EXTRA['/'.join(bits)]}"
            self.path = path + sep + qs
            self.abl_ep = path.strip("/").split("/")[-1]
            return super().dispatch(post)

        def send(self, code, value):
            if hide is not None and getattr(self, "abl_ep", "") != "spec" and isinstance(value, dict):
                value = hide(value)
            return super().send(code, value)

    server.RequestHandlerClass = Handler
    return server
