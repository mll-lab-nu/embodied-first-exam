#!/usr/bin/env python3
"""Unit test of the RoboOlympics standard adapter's live grading (scripts/roboolympics/shared/standard/server.py; board
0151: the live referee's call is the verdict, no grading replay), on a stub rcb_rfo.Episode: numpy only, no simulator,
no image (unlike this directory's referee tests, which run in the simulator image).
  1. build() refuses an image whose world does not start at the frozen instance's state hash: InstanceMismatch, which
     the shared layer turns into instance_mismatch, infra_error = 1, before the agent is served;
  2. start_sha is the instance's recorded t = 0 hash (the layer also checks every reset against it);
  3. the adapter has no verify() (nothing replays the episode to grade it);
  4. live_verdict() records the live referee's call (referee.json, final.json `referee`) and adds no rule (no "success"
     key: the live success stands as the referee called it), and none of its keys is one the service writes itself.
    python3 scripts/roboolympics/tests/test_live_adapter.py"""
import json, os, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SHARED = os.path.join(HERE, "..", "shared")
sys.path[:0] = [os.path.join(SHARED, "standard"), SHARED]
sys.dont_write_bytecode = True
import rcb_rfo  # noqa: E402


class FakeRef:
    events = [{"t": 1.0, "ev": "stage", "name": "reach"}]


class FakeWorld:
    ref = FakeRef()


class FakeEpisode:
    T0 = "sha-t0"

    def __init__(self, instance):
        self.instance, self.t0_sha, self.world = instance, FakeEpisode.T0, FakeWorld()
        self.control_dt, self.horizon, self.cameras, self.proprio_layout, self.raw_dim = 0.01, 100, ("venue",), ["q0"], 3
        self.family = instance["family"]

    def instance_check(self, instance):
        want = instance.get("t0", {}).get("state_sha")
        return {"ok": want is None or want == self.t0_sha, "exact": want == self.t0_sha}

    def verdict(self):
        return {"success": True, "done": True, "failed": None, "stages": ["reach", "score"], "stages_total": 2,
                "progress": 1.0, "metrics": {"distance_m": 1.5}, "steps": 42, "time_s": 0.42}

    def outcome(self):
        return "success"


rcb_rfo.Episode = FakeEpisode
INSTANCE = {"family": "sprint", "seed": 0, "t0": {"state_sha": "sha-t0", "cameras": {}, "robot": {}},
            "texts": {"sentence": "Run.", "rules": "Run fast."}}
with tempfile.TemporaryDirectory() as td:
    os.environ["RCB_DATA"] = td
    path = os.path.join(td, "instance.json")
    json.dump(INSTANCE, open(path, "w"))
    os.environ["RCB_INSTANCE"] = path
    import server  # noqa: E402
    import rcb_service  # noqa: E402
    errs = []
    sim = server.build()
    if sim.start_sha != "sha-t0":
        errs.append(f"start_sha {sim.start_sha!r}")
    if hasattr(sim, "verify"):
        errs.append("the adapter still has verify(): a grading replay")
    import numpy as np
    out = sim.live_verdict(np.zeros((42, 3)), True)
    if "success" in out or set(out) & rcb_service.RESERVED:
        errs.append(f"live_verdict keys {sorted(out)}")
    ref = json.load(open(os.path.join(td, "referee.json")))
    if ref.get("outcome") != "success" or ref.get("executed_rows") != 42 or out["referee"]["stages_reached"] != 2:
        errs.append(f"referee record {ref} / {out}")
    json.dump(dict(INSTANCE, t0={"state_sha": "another", "cameras": {}, "robot": {}}), open(path, "w"))
    try:
        server.build()
        errs.append("build() accepted a world that does not start at the frozen instance")
    except rcb_service.InstanceMismatch:
        pass
for e in errs:
    print("FAIL", e)
print(f"{'FAIL' if errs else 'ok'} roboolympics live adapter: 4 checks, {len(errs)} failed")
sys.exit(1 if errs else 0)
