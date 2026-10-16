"""iSpatialGym's frozen instance on the CPU, no simulator: every committed instance restores upstream's TRO exactly
(mk_tasks.split_instance's inverse, rcb_ispatialgym.restore_goal), holds no target, role name or host path, and the
start-only BDDL problem states no goal (shared/neutral_bddl.py).   python3 scripts/ispatialgym/tests/test_instance.py"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "shared"))
import rcb_ispatialgym as RI  # noqa: E402

ROLE = re.compile(r'"(?:target|targets|partner|distractors|source|destination|obstacles)_[a-z]+(?:_[a-z]+)*_[a-z]{6}_\d+"')
GOAL_KEYS = ("pose_targets", "articulation_targets", "attachment_targets", "goal_observation", "task_variant", "groups")


def test_instances() -> None:
    for d in sorted((HERE / "instances").iterdir()):
        start = json.loads((d / "instance.json").read_text())
        goal = json.loads((d / "goal.json").read_text())
        tro, meta = RI.restore_goal(start, goal)                  # raises unless the sha256 of upstream's TRO comes back
        assert any(tro["ispatialgym"].get(k) for k in ("pose_targets", "articulation_targets", "groups")), d.name
        text = (d / "instance.json").read_text()
        assert not any(f'"{k}"' in text for k in GOAL_KEYS), f"{d.name}: a goal field in instance.json"
        assert not ROLE.search(text), f"{d.name}: a role name in instance.json"
        assert "/vision/" not in text, f"{d.name}: an upstream host path in instance.json"
        assert start["template_meta"]["problem"] == "task-0" and meta["problem"] != "task-0", d.name
        broken = json.loads(json.dumps(goal)); broken["tro_ispatialgym"]["instance_id"] = "x"
        try:
            RI.restore_goal(start, broken)
        except RuntimeError:
            pass
        else:
            raise AssertionError(f"{d.name}: a wrong goal.json restored")


def test_neutral_bddl() -> None:
    problem = """(define (problem p-0)
    (:domain ispatialgym)
    (:variant p-inside_small_scale-a-b-table)
    ; the target ends inside the partner
    (:objects a.n.01_1 - a.n.01  b.n.01_1 b.n.01_2 - b.n.01  table.n.01_1 - table.n.01  floor.n.01_1 - floor.n.01  agent.n.01_1 - agent.n.01)
    (:groups b.n.01_1 b.n.01_2 - distractors_group.n.01_1)
    (:init (ontop a.n.01_1 table.n.01_1) (ontop distractors_group.n.01_1 table.n.01_1) (not (inside a.n.01_1 b.n.01_1)) (ontop agent.n.01_1 floor.n.01_1))
    (:goal (and (inside ?a.n.01_1 ?b.n.01_1) (not (grasped ?agent.n.01_1 ?a.n.01_1))))
    (:measure (pose_reached ?a.n.01_1)))"""
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "problem0.bddl"; src.write_text(problem)
        subprocess.run([sys.executable, str(HERE / "shared/neutral_bddl.py"), str(src), td], check=True)
        out = (Path(td) / "task/problem0.bddl").read_text()
    for gone in ("variant", "inside", "target", "grasped", "measure", "pose_reached", "distractors", ";"):
        assert gone not in out, f"neutral BDDL keeps {gone!r}"
    assert "(ontop a.n.01_1 table.n.01_1)" in out and "(ontop ?agent.n.01_1 ?floor.n.01_1)" in out


if __name__ == "__main__":
    test_instances(); test_neutral_bddl()
    print("ok: iSpatialGym instances restore upstream's TRO and hold no answer; the start-only BDDL states no goal")
