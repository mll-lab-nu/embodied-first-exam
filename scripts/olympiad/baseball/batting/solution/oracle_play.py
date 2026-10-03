"""Harbor oracle for baseball batting (program play): a scripted camera-only batter (bat_player.py) that plays the
game live through the same HTTP endpoints the `game` command calls. It uses only the camera images, the spec (camera
poses and intrinsics, the pitcher's arsenal) and the documented ball and swing-rig models; no simulator state.

    python3 oracle_play.py            (SIM_URL, default http://sim:8000)
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bat_player as BP  # noqa: E402

OUT = os.environ.get("RCB_OUT", "/app/output")
os.makedirs(OUT, exist_ok=True)
LOG = open(os.path.join(OUT, "oracle_log.jsonl"), "w")


def base():
    for b in [os.environ.get("SIM_URL"), "http://sim:8000", "http://127.0.0.1:8000"]:
        if not b:
            continue
        for _ in range(90):
            try:
                urllib.request.urlopen(b + "/spec", timeout=3)
                return b
            except urllib.error.HTTPError:
                return b
            except Exception:  # noqa: BLE001
                time.sleep(1)
    sys.exit("game service unreachable")


BASE = base()


def call(path, body=None):
    req = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        return json.load(urllib.request.urlopen(req, timeout=900))
    except urllib.error.HTTPError as e:
        return json.load(e)


def note(**kw):
    LOG.write(json.dumps(kw, default=float) + "\n"); LOG.flush()


class Api:
    def observe(self):
        r = call("/observe", {})
        return r, r.get("observation")

    def act(self, body):
        return call("/act", body)

    def wait(self, dt):
        return call("/wait", {"dt": dt})


spec = call("/spec")
PERIOD = float(spec["timing"]["wall_s_per_control_step"])
SPINS = [[a["spin_rad_s"] * x for x in a["spin_axis"]] for a in spec["match"]["pitcher"]["arsenal"].values()]
B = BP.Batter(spec["cameras"])
api = Api()
o = call("/start", {})
B.ingest(BP.decode(o["observation"].pop("image_png_b64")), o["observation"]["view_times"])   # windup: background
n = 0
while True:
    r = BP.bat_pitch(api, B, SPINS, PERIOD, log=note)
    n += 1
    po = r.get("pitch_over") or {}
    note(pitch_over=po)
    print(po.get("pitch"), po.get("pitch_type"), po.get("outcome"), po.get("plate_appearance_result", ""), flush=True)
    if r.get("done") or not r.get("review_prompt"):
        break
    rr = call("/ready", {"why": "reference batter: camera fit of the flight", "plan": "same policy"})
    if "now" not in rr:
        note(ready_error=rr)
        break
final = call("/status")
print("final:", json.dumps({k: final.get(k) for k in ("bases", "threshold", "pa_results", "done", "reason")}))
note(final=final)
