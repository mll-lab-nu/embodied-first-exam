"""Harbor oracle for the wall-clock tennis match: a scripted reference player that uses only the public interface (the
`observe` camera images and frame steps, the robot state in the replies, the camera poses / intrinsics of `spec` and
the documented physics), through the same HTTP endpoints the `game` command calls. No ball state, no simulator: it
detects the ball in the images, fits its flight and acts (tn_player.py). It plays against the live clock, so its
result can vary with machine load; the match it played is graded by the service's own logged replay.

    python3 oracle_play.py            (SIM_URL, default http://sim:8000; SEAT=A|B in the two-player duel)
"""
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tn_player as TP  # noqa: E402

OUT = os.environ.get("RCB_OUT", "/app/output")
os.makedirs(OUT, exist_ok=True)


def base():
    """The service URL; with SEAT set (the two-player duel) the seat's own prefix, e.g. http://sim:8000/A."""
    seat = os.environ.get("SEAT")
    for b in [os.environ.get("SIM_URL"), "http://sim:8000", "http://127.0.0.1:8000"]:
        if not b:
            continue
        if seat:
            b = b.rstrip("/") + "/" + seat
        for _ in range(90):
            try:
                urllib.request.urlopen(b + "/spec", timeout=3)
                return b
            except urllib.error.HTTPError:
                return b
            except Exception:  # noqa: BLE001
                time.sleep(1)
    sys.exit("game service unreachable")


class Client:
    def __init__(self, url):
        self.url = url
        self.spec = self.call("/spec")
        self.period = float(self.spec["timing"]["wall_s_per_control_step"])

    def call(self, path, body=None):
        req = urllib.request.Request(self.url + path, data=None if body is None else json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        for attempt in range(20):
            try:
                return json.load(urllib.request.urlopen(req, timeout=900))
            except urllib.error.HTTPError as e:
                out = json.load(e)
                if e.code == 429 and out.get("busy") and attempt < 19:
                    time.sleep(0.01)           # another act still in flight (cannot happen here: one thread)
                    continue
                return out

    def start(self):
        return self.call("/start", {})

    def ready(self):
        return self.call("/ready", {"why": "reference player: scripted", "plan": "reference player: same policy"})

    def observe(self):
        t = time.monotonic()
        o = self.call("/observe", {})
        ob = o.get("observation") or {}
        png = base64.b64decode(ob.pop("image_png_b64")) if "image_png_b64" in ob else None
        return o, png, t

    def act(self, body):
        return self.call("/act", body)

    def wait(self, dt):
        return self.call("/wait", {"dt": dt})

    def now_k(self, ob, t_sent):
        """The current step: the request's step and phase plus the real time since the request was sent."""
        return float(ob["step"]) + float(ob.get("step_phase", 0.0)) + (time.monotonic() - t_sent) / self.period


def main():
    c = Client(base())
    with open(os.path.join(OUT, "oracle_log.jsonl"), "w", buffering=1) as f:
        def log(x):
            f.write(json.dumps(x, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)) + "\n")
        stats = TP.play(c, log=log)
        final = c.call("/status")
        log({"final": final, "stats": stats})
    print("final:", json.dumps({"status": final, "stats": stats}))


if __name__ == "__main__":
    main()
