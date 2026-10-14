"""The skill in the loop, in-process (skilleval/inloop.py; docs/construction_zh.md "技能在环"): our reference player's
competition program (builtin_players.Reference, its high-level decisions; truth perception by default, the camera with
--camera) plays a low-level match whose `act` calls are lowered by a skill directory (default: lowlevel/reference, our
toolkit-only act) running in the skilleval sandbox; step() every 2 control steps; every call logged with the skill
files' sha256 and its wall time. Then the episode is replayed in a fresh process (core.episode) and the digests
compared.

  python3 sports/badminton/lowlevel/inloop_pilot.py OUT [--skill DIR] [--level 1] [--seed 101] [--camera]

(sport image, repo root, the toolkit at /opt/robot as in the seat). OUT/result.json: score, the per-call summary
(act / step: n, errors, wall p50 / p95 / max), the replay check; OUT/inloop/inloop_A.jsonl: every call.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPORT = HERE.parent
REPO = SPORT.parents[1]


class ActProgram:
    """The reference's decisions sent as skill calls: act as is (lowered by the player's own skill at the step it
    arrives: the in-loop level has no act lead, so the reference plans with lead 0), toss as is."""

    def __init__(self, spec, seat, seed=0, camera=False):
        sys.path.insert(0, str(HERE))
        import evaluator as E
        self.E = E
        spec = dict(spec, action_level="high", act=dict(spec.get("act") or {}, lead_steps=0))
        self.ref = E.BP.Reference(spec, seat, seed) if camera else E.TruthReference(spec, seat, seed)
        self.camera = camera
        self.sent = {"act": 0, "toss": 0, "other": 0}
        self.m = None

    def act(self, view):
        if not self.camera:
            view = self.ref.view(self.m, "A", {"step": view["state"]["step"]})
        a = self.ref.act(view)
        if not a:
            return None
        self.sent[a["type"] if a["type"] in self.sent else "other"] += 1
        return a


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--skill", default=str(HERE / "reference"))
    ap.add_argument("--level", type=int, default=1)
    ap.add_argument("--seed", type=int, default=101)
    ap.add_argument("--camera", action="store_true")
    a = ap.parse_args()
    out = Path(a.out)
    (out / "inloop").mkdir(parents=True, exist_ok=True)
    (out / "inloop" / "inloop_A.jsonl").unlink(missing_ok=True)
    os.environ["RCB_SKILL_INLOOP"] = a.skill
    os.environ["RCB_SKILL_INLOOP_LOG"] = str(out / "inloop")
    for p in (str(REPO), str(SPORT)):
        sys.path.insert(0, p)
    from core import local
    from core.episode import load_plugin
    from core.sport import MatchConfig
    plugin = str(SPORT / "plugin.py")
    sport = load_plugin(plugin)
    cfg = MatchConfig(sport="badminton", format="match-wallclock", seats=("A",), seed=a.seed, level=a.level,
                      action_level="low", slowdown=20)
    player = ActProgram(local.seat_spec(sport, cfg, "A", plugin=plugin), "A", a.seed, a.camera)
    build = sport.build

    def build_keep(c):                                    # the truth view reads the live match
        m = build(c)
        player.m = m
        return m
    sport.build = build_keep
    t0 = time.time()
    r = local.play(sport, cfg, {"A": player}, data=out / "ep", render=a.camera, plugin=plugin)
    wall = time.time() - t0
    layer = sport.action_layer("low")
    loop = layer.loops["A"]
    res = {"scores": r["scores"], "winner": r["winner"], "k": r["k"], "digest": r["digest"], "wall_s": round(wall, 1),
           "sent": player.sent, "refused": r["rejected"], "inloop": loop.summary(), "failures": layer.failures[:10],
           "returns": r["final_fields"].get("returns"), "our_legs": r["final_fields"].get("our_legs")}
    env = {k: v for k, v in os.environ.items() if not k.startswith("RCB_SKILL_INLOOP")}
    t1 = time.time()
    p = subprocess.run([sys.executable, "-m", "core.episode", plugin, str(out / "ep")], cwd=str(REPO), env=env,
                       capture_output=True, text=True)
    chk = json.loads((out / "ep" / "replay_check.json").read_text()) if (out / "ep" / "replay_check.json").exists() else {}
    res["replay"] = {"rc": p.returncode, "state_sha_equal": chk.get("state_sha") == r["digest"],
                     "scores_equal": chk.get("scores") == r["scores"], "wall_s": round(time.time() - t1, 1),
                     "stderr": p.stderr[-400:]}
    loop.close()
    (out / "result.json").write_text(json.dumps(res, indent=1, default=float))
    print(json.dumps(res, default=float))


if __name__ == "__main__":
    main()
