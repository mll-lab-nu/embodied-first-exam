"""Make the skill-in-the-loop task from the generated low-level match task (a prototype: tools/generate.py does
not know the switch yet). The simulator mounts the player's output volume read-only where only root can reach it
(/root/agent_output) and the seat's toolkit at /opt/robot (as the seat has it), runs on the evaluation image (the sim
image + the seat's SciPy, tools/skill_eval.py eval_image) and lowers every `act` with the player's
/app/output/skill/act.py (RCB_SKILL_INLOOP; skilleval/inloop.py); the per-call log is an artifact (/data/inloop_A.jsonl).

    python3 sports/badminton/lowlevel/make_inloop_task.py OUT_DIR [--image TAG]
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SRC = REPO / "tasks" / "badminton-match-wallclock-program-lowlevel-standard"
NAME = "badminton-match-wallclock-program-lowlevel-inloop"

SECTION = """
## Skill in the loop (this task)

This match is played with **your own `act` in the loop**: the simulator runs your `/app/output/skill/act.py` during
the match, in its own sandboxed process (no network, no simulator access, a private copy of your skill's files), and
lowers every act you send with it.

- Send `{"type": "act", "t": T, "pos": [x, y, z], "normal": [nx, ny, nz], "vel": [vx, vy, vz]}` (`game act` JSON) to
  strike: the simulator calls your `act(t, pos, normal, vel, *, state, spec)` at the control step where the act takes
  effect (the next step: there is no act lead at this level) and applies the joint command it returns (it must pass
  the usual low-level checks; if it raises, times out or returns an invalid command, nothing happens).
- Your skill's optional `step(*, state, spec)` is called every 20 ms (2 control steps) during the whole match; the
  command it returns is applied as well (return None to change nothing).
- **While a shuttle you may meet is in play** (coming to you, or your toss in the air) **joint commands (`traj`,
  `none`) are refused (409)**: the strokes are played through your skill. Otherwise you may send joint commands
  directly; `toss` is always allowed.
- The simulator loads your skill when the match starts and reloads it at the start of a point if its files changed
  (so you may improve it between points); every call is logged with the sha256 of the files it ran.
- `state` is the low level's observation (your robot's joints, targets and their velocity `qd_target`, the servo's
  state `servo`, the command in force, `step`, the score; no images, no shuttle coordinates); `spec` holds `joints`,
  `limits`, `toolkit`, `skill_contract`. Allowed imports: numpy, scipy, mujoco, `/opt/robot` (the same toolkit as
  yours) and your own files.
- Time: every call runs on the world's clock (the world waits for it, and the time it takes is logged); keep `act`
  well under 1 s and `step` under 50 ms.
- After the match your final `act.py` is evaluated as usual (API test and competition test).
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--image", default=None, help="the simulator image (default: tools/skill_eval.py eval_image)")
    a = ap.parse_args()
    out = Path(a.out) / NAME
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(SRC, out, symlinks=True)
    image = a.image
    if image is None:
        sys.path.insert(0, str(REPO / "tools"))
        import skill_eval
        import sportlib
        image = skill_eval.eval_image("badminton", sportlib.decl("badminton")["modes"]["low"])
    dc = out / "environment" / "docker-compose.yaml"
    t = dc.read_text()
    old_img = "    image: ghcr.io/mll-lab-nu/eai-olympiad:0.1.0\n    volumes:\n      - ./sim:/srv:ro\n"
    assert old_img in t, "unexpected compose layout"
    t = t.replace(old_img, f"    image: {image}\n    volumes:\n      - ./sim:/srv:ro\n"
                  "      - agent_output:/root/agent_output:ro\n"
                  "      - ./sim/sport/seat/robot_only.xml:/opt/robot/robot_only.xml:ro\n"
                  "      - ./sim/sport/sim/scene/assets:/opt/robot/assets:ro\n"
                  "      - ./sim/sport/seat/lib:/opt/robot/lib:ro\n"
                  "      - ./sim/sport/seat/toolkit.toml:/opt/robot/toolkit.toml:ro\n")
    old_env = '      RCB_ACTION_LEVEL: "low"\n'
    assert old_env in t
    t = t.replace(old_env, old_env + '      RCB_SKILL_INLOOP: "/root/agent_output/skill"\n'
                                     '      RCB_SKILL_INLOOP_LOG: "/data"\n')
    dc.write_text(t)
    tt = out / "task.toml"
    s = tt.read_text().replace("badminton-match-wallclock-program-lowlevel-standard", NAME)
    s = s.replace('  { source = "/data/final.json", service = "sim" },',
                  '  { source = "/data/final.json", service = "sim" },\n  { source = "/data/inloop_A.jsonl", service = "sim" },')
    tt.write_text(s)
    ins = out / "instruction.md"
    ins.write_text(ins.read_text().rstrip("\n") + "\n" + SECTION)
    print(out, image)


if __name__ == "__main__":
    main()
