"""The skill in the loop, in process (skilleval/inloop.py, sport.toml [modes.low.inloop]; no wall clock: every call is
synchronous and takes no game time, timing "free"): the in-loop oracle (builtin_players.SkillReference: our
camera-only reference player's decisions sent as `hit` calls) plays a low-level match whose hits are lowered by a skill
directory (default: lowlevel/reference, our toolkit-only hit) in the skilleval sandbox; step() every 2 control steps;
every call logged with the skill files' sha256 and its wall time. Then the episode is replayed in a fresh process
(core.episode) without the skill and the digests compared. The match service's version (the skill's compute counts,
the skill in its own container) is tools/live.py on the generated low task.

  python3 sports/tabletennis/lowlevel/inloop_pilot.py OUT [--skill DIR] [--level 1] [--seed 101] [--no-images]

(sport image + the seat's SciPy, i.e. tools/skill_eval.py eval_image; repo root; the toolkit at /opt/robot as in the
seat). OUT/result.json: score, the per-call summary (hit / step: n, errors, wall p50 / p95 / max), the replay check;
OUT/inloop/inloop_A.jsonl: every call.
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--skill", default=str(HERE / "reference"))
    ap.add_argument("--level", type=int, default=1)
    ap.add_argument("--seed", type=int, default=101)
    ap.add_argument("--no-images", action="store_true")
    a = ap.parse_args()
    out = Path(a.out)
    (out / "inloop").mkdir(parents=True, exist_ok=True)
    (out / "inloop" / "inloop_A.jsonl").unlink(missing_ok=True)
    os.environ.update(RCB_SKILL_INLOOP_A=a.skill, RCB_SKILL_INLOOP_LOG=str(out / "inloop"),
                      RCB_SKILL_INLOOP_TIMING="free")
    for p in (str(REPO), str(SPORT)):
        sys.path.insert(0, p)
    from core import local
    from core.episode import load_plugin
    from core.sport import MatchConfig
    plugin = str(SPORT / "plugin.py")
    sport = load_plugin(plugin)
    import builtin_players as bp
    cfg = MatchConfig(sport="tabletennis", format="match", seats=("A",), seed=a.seed, level=a.level,
                      action_level="low")
    player = bp.SkillReference(local.seat_spec(sport, cfg, "A", plugin=plugin), "A", a.seed)
    t0 = time.time()
    r = local.play(sport, cfg, {"A": player}, data=out / "ep", render=not a.no_images, plugin=plugin)
    wall = time.time() - t0
    layer = sport.action_layer("low")
    res = {"scores": r["scores"], "winner": r["winner"], "k": r["k"], "digest": r["digest"], "wall_s": round(wall, 1),
           "sent": player.sent, "refused": r["rejected"], "inloop": layer.summary()["A"], "failures": layer.failures[:10]}
    env = {k: v for k, v in os.environ.items() if not k.startswith("RCB_SKILL_INLOOP")}
    t1 = time.time()
    p = subprocess.run([sys.executable, "-m", "core.episode", plugin, str(out / "ep")], cwd=str(REPO), env=env,
                       capture_output=True, text=True)
    chk = json.loads((out / "ep" / "replay_check.json").read_text()) if (out / "ep" / "replay_check.json").exists() else {}
    res["replay"] = {"rc": p.returncode, "state_sha_equal": chk.get("state_sha") == r["digest"],
                     "scores_equal": chk.get("scores") == r["scores"], "wall_s": round(time.time() - t1, 1),
                     "stderr": p.stderr[-400:]}
    layer.close()
    (out / "result.json").write_text(json.dumps(res, indent=1, default=float))
    print(json.dumps(res, default=float))


if __name__ == "__main__":
    main()
