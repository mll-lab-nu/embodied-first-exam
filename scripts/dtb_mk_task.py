#!/usr/bin/env python3
"""Generate DexToolBench task directories from the claw_hammer/swing_down template.

    python3 scripts/dtb_mk_task.py <category> <object> <task> [...]      # or: --all

Copies tasks/dextoolbench_hammer_claw_hammer_swing_down-privileged/ (tooling, verifier, compose files, solve.sh) to
tasks/dextoolbench_<category>_<object>_<task>/, writes that task's instance.json from the SimToolReal trajectory
(images/mujoco/rcb_mj/simtoolreal/dextoolbench/trajectories/...), and rewrites the texts. The oracle
(solution/oracle_targets.npy) is generated separately with scripts/dtb_mk_oracle.py; results/ is not copied."""
import json, pathlib, re, shutil, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent)); from task_conventions import normalize  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
TPL = ROOT / "tasks/dextoolbench_hammer_claw_hammer_swing_down-privileged"
TRAJ = ROOT / "images/mujoco/rcb_mj/simtoolreal/dextoolbench/trajectories"
MOTION = {"swing_down": "a downward hammer swing", "swing_side": "a sideways hammer swing", "draw_smile": "drawing a smiley face",
          "write_c": "writing the letter C", "wipe_smile": "wiping a smiley face", "wipe_c": "wiping the letter C",
          "sweep_forward": "a forward sweep", "sweep_right": "a sweep to the right", "serve_plate": "serving onto a plate",
          "flip_over": "flipping something over", "spin_vertical": "spinning it about a vertical axis", "spin_horizontal": "spinning it about a horizontal axis"}


def make(cat: str, obj: str, task: str) -> pathlib.Path:
    src = TRAJ / cat / obj / f"{task}.json"; t = json.load(open(src)); n = len(t["goals"])
    name = f"dextoolbench_{cat}_{obj}_{task}-privileged"; dst = ROOT / "tasks" / name
    if dst != TPL:
        if dst.exists(): shutil.rmtree(dst)
        shutil.copytree(TPL, dst, ignore=shutil.ignore_patterns("results", "__pycache__", "oracle_targets.npy"))
    human = obj.replace("_", " ")
    inst = {"benchmark": "DexToolBench (SimToolReal)", "category": cat, "object": obj, "task": task,
            "text": f"Pick up the {human} and move it through the demonstrated motion ({MOTION.get(task, task)}): bring it to each goal pose in order (the green marker shows the current goal).",
            "start_pose": t["start_pose"], "goals": t["goals"], "pose_format": "x y z qx qy qz qw (world frame, metres)"}
    for d in ("environment", "tests"): json.dump(inst, open(dst / d / "instance.json", "w"), indent=1)
    if dst == TPL: return dst
    subs = [("hammer / claw_hammer / swing_down", f"{cat} / {obj} / {task}"), ("claw_hammer / swing_down", f"{obj} / {task}"),
            ("dextoolbench_hammer_claw_hammer_swing_down-privileged", name), ("dextoolbench/hammer/claw_hammer/swing_down", f"dextoolbench/{cat}/{obj}/{task}"),
            ("the 37 demonstrated goal poses", f"the {n} demonstrated goal poses"), ("**37 goal poses in order**", f"**{n} goal poses in order**"),
            ("if all 37 goals are reached", f"if all {n} goals are reached"), ("Goals reached / 37", f"Goals reached / {n}"),
            ("all 37 goal poses", f"all {n} goal poses"), ("carries the hammer", f"carries the {human}"), ("goals / 37", f"goals / {n}")]
    t = dst / "task.toml"; t.write_text(re.sub(r"(?m)^oracle(_evidence)? = .*\n", "", t.read_text()))   # set from the measured oracle, not the template's
    for f in ("instruction.md", "task.toml", "README.md", "solution/solve.sh"):
        p = dst / f; s = p.read_text()
        for a, b in subs: s = s.replace(a, b)
        p.write_text(s)
    ins = dst / "instruction.md"; s = ins.read_text()
    s = re.sub(r"^# DexToolBench · .*$", f"# DexToolBench · {human} · {task} (MuJoCo)", s, count=1, flags=re.M)
    para = (f"A KUKA iiwa 14 arm with a 22-joint **Sharpa HA4** dexterous hand stands next to a table with a **{human}** on it.\n"
            f"**Task:** pick up the {human} and move it through the demonstrated motion ({MOTION.get(task, task)}): bring it to each\n"
            f"of the **{n} goal poses in order** (the green ghost tool shows the current goal). This is task `{cat} / {obj} /\n"
            f"{task}` of DexToolBench (SimToolReal), run here in plain MuJoCo.\n")
    s = re.sub(r"A KUKA iiwa 14 arm.*?run here in plain MuJoCo\.\n", para, s, count=1, flags=re.S)
    for a, b in (("the hammer's grasp box", "the tool's grasp box"), ("in the hammer's frame", "in the tool's frame"), ("the hammer body is `object`", "the tool body is `object`"),
                 ("moving the hammer by hand", "moving the tool by hand"), ("carry the hammer", "carry the tool")):
        s = s.replace(a, b)
    ins.write_text(s)
    rd = dst / "README.md"; r = rd.read_text()
    # the oracle result is measured later (scripts/dtb_mk_oracle.py): no goal count and no oracle level until then
    r = re.sub(r"(## Reference solution\n).*?(?=\n## )", r"\1`solution/`: SimToolReal's pretrained policy run in this exact scene (scripts/dtb_mk_oracle.py), recorded targets replayed; "
               r"goals reached: to be measured with scripts/dtb_mk_oracle.py\n", r, count=1, flags=re.S)
    r = re.sub(r" SimToolReal's pretrained policy reaches \d+/\d+ goals here\.", "", r)
    r = re.sub(r"\| port check \|.*\|\n", "", r); rd.write_text(r)
    normalize(dst)   # protocol v1.0 conventions (scripts/task_conventions.py)
    return dst


if __name__ == "__main__":
    args = sys.argv[1:]
    todo = [tuple(p.relative_to(TRAJ).with_suffix("").parts) for p in sorted(TRAJ.glob("*/*/*.json"))] if args == ["--all"] else [tuple(args[i:i + 3]) for i in range(0, len(args), 3)]
    for cat, obj, task in todo: print(make(cat, obj, task).name)
