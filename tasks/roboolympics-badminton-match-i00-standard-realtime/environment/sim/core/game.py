#!/usr/bin/env python3
"""game - your seat in the match (the same commands for every sport; the actions are the sport's, see `game spec`).

  game spec                  the sport: actions (types, fields, ranges), cameras, units, rules, timing
  game status                the current state, no images
  game start                 you are ready (preparation over); the match begins when every seat has started
  game wait [SECONDS]        turn-based: block until it is your turn; real time: let the world run SECONDS (<= 1)
  game observe [QUERY_JSON]  the state and the camera images (saved as PNG under /app/output/views/)
  game act ACTION_JSON       one action, e.g. game act '{"type": "throw", ...}' (if the sport shows the result
                             in images, they are saved like observe's, as reply_*.png)
  game ready "WHY" "PLAN"    your review (after each of your actions, turn-based; at each review, real time)
  game say "TEXT"            team formats: a message to your teammates (never shown to the other side)
Sport shortcuts (generated from the sport's declaration):
@@SHORTCUTS@@"""
import base64
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request

COMMANDS = json.loads('@@COMMANDS@@')       # shortcut -> [action type, field, field, ...]
VIEWS = "/app/output/views"
BASE = os.environ.get("SIM_URL", "http://sim:8000") + "/" + os.environ.get("SEAT", "A")


def call(ep, body=None):
    req = urllib.request.Request(BASE + "/" + ep, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            out = json.load(e)
        except ValueError:
            out = {"error": str(e)}
        out["http_status"] = e.code
        return out


def save(b64, name):
    os.makedirs(VIEWS, exist_ok=True)
    fd, p = tempfile.mkstemp(dir=VIEWS, prefix=name + "_", suffix=".png")
    with os.fdopen(fd, "wb") as f:
        f.write(base64.b64decode(b64))
    return p


def show(o):
    ob = o.get("observation")
    if isinstance(ob, dict) and ob.get("image_png_b64"):
        ob["image_file"] = save(ob.pop("image_png_b64"), "reply" if ob.get("of") else "obs")
    for k in [k for k in o if k.endswith("_image_b64")]:
        if o[k]:
            o[k[:-4] + "_file"] = save(o.pop(k), k[:-10])
        else:
            o.pop(k)
    print(json.dumps(o, indent=1))


def main(a):
    turn = call("spec").get("protocol", "").startswith("eai-standard-turn") if a[:1] == ["wait"] else None
    if a == ["spec"]:
        show(call("spec"))
    elif a == ["status"]:
        show(call("status"))
    elif a == ["start"]:
        show(call("start", {}))
    elif a[:1] == ["wait"] and len(a) <= 2:
        if turn:
            while True:
                o = call("wait", {"timeout_s": 60})
                st = o.get("state") or {}
                if "error" in o or st.get("done") or st.get("your_turn"):
                    break
            show(o)
        else:
            show(call("wait", {"dt": float(a[1]) if len(a) == 2 else 0.1}))
    elif a[:1] == ["observe"] and len(a) <= 2:
        show(call("observe", {"query": json.loads(a[1])} if len(a) == 2 else {}))
    elif a[:1] == ["act"] and len(a) == 2:
        show(call("act", json.loads(a[1])))
    elif a[:1] == ["ready"] and len(a) == 3:
        show(call("ready", {"why": a[1], "plan": a[2]}))
    elif a[:1] == ["say"] and len(a) == 2:
        show(call("say", {"text": a[1]}))
    elif a and a[0] in COMMANDS and len(a) == len(COMMANDS[a[0]]):
        kind, *names = COMMANDS[a[0]]
        try:
            body = {"type": kind, **{n: float(x) for n, x in zip(names, a[1:])}}
        except ValueError:
            sys.exit(__doc__)
        show(call("act", body))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
