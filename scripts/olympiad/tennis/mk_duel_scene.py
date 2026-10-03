"""Make the two-robot tennis scene (duel/scene_extra/tn_duel.xml) from the single-player scene.

Robot A is the single-player robot (base on rails at y < 0, facing +y). Robot B is a copy of its whole body tree with
every name suffixed `_b`, attached to a frame turned 180 degrees about z: its joint values (rails and arm) mean the
same in B's own frame, (x, y, z) -> (-x, -y, z), as A's in the world frame. The ball stays a mocap body drawn only;
MuJoCo contacts stay disabled (the ball and its racket hits are integrated by tn.py / duel.py).

    python3 scripts/olympiad/tennis/mk_duel_scene.py        (rewrites duel/scene_extra/tn_duel.xml)
"""
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
src = (HERE.parent / "shared/tennis/sim/scene/tn_scene.xml").read_text()

i = src.index('    <body name="base" pos="0 0 0">')
j = src.index("  </worldbody>")
robot = src[i:j]
robot_b = re.sub(r'name="([^"]+)"', r'name="\1_b"', robot)
robot_b = robot_b.replace('<body name="base_b" pos="0 0 0">', '<body name="base_b" pos="0 0 0" quat="0 0 0 1">', 1)
robot_b = robot_b.replace('rgba="0.85 0.2 0.15 1"', 'rgba="0.15 0.35 0.85 1"')      # B's racket frame: blue
a = src.index("  <actuator>")
b = src.index("  </actuator>")
acts = src[a + len("  <actuator>\n"):b]
acts_b = re.sub(r'name="([^"]+)"', r'name="\1_b"', acts)
acts_b = re.sub(r'joint="([^"]+)"', r'joint="\1_b"', acts_b)
out = src[:j] + robot_b + src[j:b] + acts_b + src[b:]
out = out.replace('<mujoco model="rcb_tennis">', '<mujoco model="rcb_tennis_duel">', 1)
out = out.replace("<!--\n  Robot tennis scene", "<!--\n  Two-robot tennis scene (duel; made by scripts/olympiad/tennis/mk_duel_scene.py from tn_scene.xml).\n  Robot B (all names suffixed _b, blue racket frame) mirrors robot A: (x, y, z) -> (-x, -y, z).\n  Robot tennis scene", 1)
(HERE / "duel/scene_extra/tn_duel.xml").write_text(out)
print("wrote", HERE / "duel/scene_extra/tn_duel.xml")
