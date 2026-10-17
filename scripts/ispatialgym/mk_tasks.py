"""iSpatialGym task generator (docs/benchmarks/ispatialgym.md): subset.toml -> tasks/ispatialgym-<task>-i00-standard.

  python3 scripts/ispatialgym/mk_tasks.py instances --data <ispatialgym-eval-data> --bddl <iSpatialGym>/ispatialgym/assets/bddl
      split each picked instance of upstream's eval dataset into instances/<task>/instance.json (the frozen START, shared
      byte for byte by both twins and the privileged agent) and goal.json (what scores it: only on the scoring side),
      plus goal.png and upstream.json; the BDDL problem is not copied (iSpatialGym's own file, in the image):
      upstream.json records its sha256, which the tooling checks at load
  python3 scripts/ispatialgym/mk_tasks.py render       write every task directory from templates/, shared/ and instances/
  python3 scripts/ispatialgym/mk_tasks.py --check      render into a temporary tree and diff it with tasks/
The facts of each instance (instances/<task>/facts.json: start-state hash, step budget, tolerances, the hold episode, two
fresh replays) are measured in the image on a GPU: shared/rcb_ispatialgym.py freeze (README of this benchmark's doc).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from string import Template

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SUBSET = tomllib.loads((HERE / "subset.toml").read_text())
TRO_SUFFIX = "-tro_state.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tasks() -> list[dict]:
    return [{**SUBSET["defaults"], **t} for t in SUBSET["task"]]


ROLE = re.compile(r"^(?:target|targets|partner|distractors|source|destination|obstacles|board)_(.+)$")
META_START = ("scene", "load_room_instances", "scene_variant", "task_rooms")      # the template_meta keys run_isg's loader reads
TRO_START = ("schema_version", "scene", "object_bindings", "robot_state", "constraints", "grasps")   # what rebuilds the start
SCENE_START = ("model", "floor", "load_room_instances", "task_rooms", "scene_variant")


def _canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def split_instance(template: dict, meta: dict, tro: dict) -> tuple[dict, dict]:
    """(instance.json, goal.json) of one upstream instance (LEAKAGE §3: lifted by diffing against the real removal).
    instance.json is the start only, with the scene's objects named without upstream's role prefix (target_*, partner_*,
    ...: renaming moves the settled start of 3 of the 12 by at most 5e-5, measured; every copy is the renamed one) and template.json's sampler path (it names the subtask) dropped;
    goal.json holds every key taken out of upstream's TRO and template_meta, and the restored TRO's sha256."""
    names = {v if isinstance(v, str) else v.get("scene_object_name") for v in tro["ispatialgym"]["object_bindings"].values()}
    ren = {n: ROLE.match(n).group(1) for n in sorted(n for n in names if n and ROLE.match(n))}
    text = lambda o: json.dumps(o)  # noqa: E731
    for old, new in ren.items():
        if re.search(rf'"{re.escape(new)}"', text(template)):
            raise SystemExit(f"renaming {old} -> {new} collides with a scene object")
    def rename(o):
        t = text(o)
        for old, new in ren.items():
            t = re.sub(rf"(?<![A-Za-z0-9_]){re.escape(old)}(?![A-Za-z0-9_])", new, t)
        return json.loads(t)
    template, meta, tro = rename(template), rename(meta), rename(tro)
    template["init_info"]["args"]["scene_file"] = None              # upstream's sampler path; the loader passes its own
    if "/vision/" in text(template):
        raise SystemExit("an upstream host path is left in template.json")
    isg = tro["ispatialgym"]
    start_isg = {k: isg[k] for k in TRO_START if k in isg}
    start_isg["scene"] = {k: v for k, v in isg["scene"].items() if k in SCENE_START}
    start_isg.update(activity="task", activity_definition_id=0, instance_id="instance")
    start_tro = {**{k: tro[k] for k in sorted(k for k in tro if k != "ispatialgym")}, "ispatialgym": start_isg}
    start = {"template": template, "template_meta": {"problem": "task-0", **{k: meta[k] for k in META_START if k in meta}},
             "tro": start_tro, "held_articulations": sorted(isg.get("articulation_targets") or {})}
    goal = {"tro_ispatialgym": {k: v for k, v in isg.items() if k not in TRO_START or k == "schema_version"},
            "tro_scene": {k: v for k, v in isg["scene"].items() if k not in SCENE_START},
            "template_meta": {k: v for k, v in meta.items() if k not in META_START},
            "tro_sha256": hashlib.sha256(_canonical(tro)).hexdigest()}
    back = json.loads(json.dumps(start_tro)); back["ispatialgym"].update(goal["tro_ispatialgym"])
    back["ispatialgym"]["scene"] = {**back["ispatialgym"]["scene"], **goal["tro_scene"]}
    assert _canonical(back) == _canonical(tro), "instance.json + goal.json do not restore upstream's TRO"
    assert {**start["template_meta"], **goal["template_meta"]} == meta, "instance.json + goal.json do not restore template_meta"
    return start, goal


def cmd_instances(a) -> None:
    """Copy the picked instance of every task out of upstream's eval dataset (instance 0 of its subtask)."""
    data = Path(a.data) / "ispatialgym-eval-instances"
    index = [json.loads(line) for line in (data / "metadata/instances.jsonl").read_text().splitlines() if line.strip()]
    episodes = {(e["subtask"], e["instance"]): e for e in
                (json.loads(line) for line in (data / "metadata/episodes.jsonl").read_text().splitlines() if line.strip())}
    for t in tasks():
        rec = next(r for r in index if r["subtask"] == t["subtask"] and r["instance"] == t["instance"])
        files = {k: data / v for k, v in rec["files"].items()}
        out = HERE / "instances" / t["task"]
        if out.exists():
            shutil.rmtree(out)
        out.mkdir(parents=True)
        activity, did = rec["problem"].rsplit("-", 1)
        iid = files["tro_state"].name[: -len(TRO_SUFFIX)]
        start, goal = split_instance(*(json.loads(files[k].read_text()) for k in ("template", "template_meta", "tro_state")))
        (out / "instance.json").write_text(json.dumps(start, indent=1) + "\n")
        (out / "goal.json").write_text(json.dumps(goal, indent=1) + "\n")
        shutil.copy(files["goal_rgb"], out / "goal.png")
        ep = episodes[(t["subtask"], t["instance"])]
        upstream = {"task_family": rec["task_family"], "task": rec["task"], "subtask": rec["subtask"], "instance": rec["instance"],
                    "scene": rec["scene"], "problem": rec["problem"], "activity": activity, "definition_id": int(did),
                    "instance_id": iid, "max_steps": rec["max_steps"], "demo_length": ep["length"],
                    "bddl_problem_sha256": sha256(Path(a.bddl) / "activity_definitions" / activity / f"problem{did}.bddl"),
                    "files_sha256": {k: sha256(v) for k, v in files.items() if k != "oracle"}}
        (out / "upstream.json").write_text(json.dumps(upstream, indent=1) + "\n")
        print(f"{t['task']}: {rec['subtask']} #{rec['instance']} ({rec['scene']}, {rec['problem']}, demo {ep['length']} steps)")


def agent_hosts() -> list[str]:
    """The hosts every task's agent may reach: scripts/set_agent_egress.py's HOSTS (read, not imported: it acts on import)."""
    import ast
    tree = ast.parse((ROOT / "scripts/set_agent_egress.py").read_text())
    return next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "HOSTS" for t in n.targets))


MODES = ("standard", "privileged")
SCORING = ("instance.json", "goal.json", "facts.json", "upstream.json")      # the scoring side's files (sim/, tests/)
# the success rule's text is one (templates/goal_rule.md, PROTOCOL Appendix H.7); only who is judged, and how, differs
GOAL_RULE = {
    "standard": {"who": "the episode", "who_cap": "The episode",
                 "checks": "The sim service judges the episode while it runs.",
                 "hold_how": "Simulated time passes\nonly while you submit rows or watch: first send a row with the base "
                             "command at 0 (the base keeps its last\ncommand until the next row), then submit rows that hold "
                             "still, or watch with `r.get_obs(seconds=...)`, which holds\nthe last command."},
    "privileged": {"who": "a replay", "who_cap": "A replay",
                   "checks": "The grader judges each replay of your trajectory (`## What you hand in`).",
                   "hold_how": "A replay stops at\nyour last row, so end your trajectory with at least $settle_steps rows of "
                               "the robot standing still (for example\n`s.hold_action()` rows once the base has stopped)."},
}


def task_dir_name(t: dict, mode: str = "standard") -> str:
    return f"ispatialgym-{t['task'].replace('_', '-')}-i00-{mode}"


def _num(v: float) -> str:
    return f"{v:.3g}"


def targets_text(task: str, facts: dict) -> str:
    """The measured targets of the instance as the instruction states them: what kind of pose, never which object."""
    pose_t = json.loads((HERE / "instances" / task / "goal.json").read_text())["tro_ispatialgym"].get("pose_targets") or {}
    lines = []
    for inst, t in sorted(facts["tolerances"]["targets"].items()):
        tol = t["tolerances"]
        link = str((pose_t.get(inst) or {}).get("link") or "")
        kind, frame = t["kind"], str((pose_t.get(inst) or {}).get("frame") or "")
        if kind == "joints":       # per joint, never by name: the joint's name would say which part moves
            for j, v in tol.items():
                unit = {"prismatic": "m", "revolute": "rad"}[facts["joint_types"][inst.split(":")[0]][j]]
                lines.append(f"   - one joint of an articulated object: within {_num(v)} {unit} of its pictured position")
            continue
        what = ("the head camera's pose (where the goal image was taken from)" if "Camera" in link else
                "the objects' poses relative to each other (how they are arranged together)" if kind == "group_layout" else
                "the pose of the objects as a group (where the arrangement stands)" if kind == "group_pose" else
                "one object's position in the head camera's frame (all three axes)" if "Camera" in frame else "one object's pose")
        parts = []
        if tol.get("position") is not None:
            parts.append(f"position within {_num(tol['position'])} m")
        if tol.get("orientation") is not None:
            parts.append(f"orientation within {_num(tol['orientation'])} rad ({math.degrees(tol['orientation']):.1f}°)")
        lines.append(f"   - {what}: {', '.join(parts) or 'as pictured'}")
    return "\n".join(lines)


def render_task(t: dict, out: Path) -> None:
    inst = HERE / "instances" / t["task"]
    facts = json.loads((inst / "facts.json").read_text())
    up = json.loads((inst / "upstream.json").read_text())
    tpl = HERE / "templates"
    hold_step_s = facts["hold"]["step_s"]
    loads = [int(x) for x in facts["load_s"]]
    replay_s = int(1500 + facts["max_steps"] * hold_step_s * 1.5)          # a scene load + every step, with margin
    v = {"task": t["task"], "subtask": t["subtask"], "family": t["family"], "family_kw": t["family"].replace("_", "-"),
         "expert_hours": t.get("expert_hours", 1.0), "max_steps": facts["max_steps"], "max_steps_s": f"{facts['max_steps'] / 30:.1f}",
         "max_steps_reason": "failed: the episode's control steps ran out",
         "settle_steps": facts["settle_steps"], "settle_s": f"{facts['settle_steps'] / 30:.1f}", "collect_s": int(3600 + replay_s + 600),   # the end (<= 1 h through a resume) + a video-only render when the live video is missing
         "verifier_s": 2 * max(2400, replay_s) + 600, "replay_timeout_s": max(2400, replay_s),   # grade_privileged.py's formula
         "load_mins": "-".join(dict.fromkeys(str(max(1, round(x / 60))) for x in (min(loads), max(loads)))),   # measured, fresh processes
         "load_max": max(loads), "startup_s": max(2400, -(-2 * max(loads) // 100) * 100),
         "steps_per_s": f"{1.0 / hold_step_s:.0f}", "targets": targets_text(t["task"], facts),
         "scene": up["scene"], "description": t["description"], "start_sha": facts["start_sha"],
         "activity": up["activity"], "definition_id": up["definition_id"],
         "image_version": (ROOT / "images/ispatialgym/VERSION").read_text().strip(),
         "allowed_hosts": ", ".join(f'"{h}"' for h in agent_hosts())}
    sys.path.insert(0, str(ROOT / "scripts"))
    import task_conventions as tc
    for mode in MODES:
        d = out / task_dir_name(t, mode)
        if d.exists():
            shutil.rmtree(d)
        (d / "tests").mkdir(parents=True)
        mt = tpl / ("privileged" if mode == "privileged" else "")
        rule = Template((tpl / "goal_rule.md").read_text()).substitute(
            v, **{k: Template(x).substitute(v) for k, x in GOAL_RULE[mode].items()}).strip()
        sub = lambda name: Template((mt / name).read_text()).substitute(v, name=d.name, goal_rule=rule)  # noqa: E731
        for f in ("task.toml", "instruction.md", "README.md"):
            (d / f).write_text(sub(f))
        (d / "environment").mkdir()
        (d / "environment/docker-compose.yaml").write_text(sub("docker-compose.yaml"))
        shutil.copy(inst / "goal.png", d / "environment/goal.png")
        if mode == "standard":
            (d / "environment/sim").mkdir()
            shutil.copy(mt / "Dockerfile.environment", d / "environment/Dockerfile")
            shutil.copy(mt / "Dockerfile.tests", d / "tests/Dockerfile")
            shutil.copy(mt / "test.sh", d / "tests/test.sh")
            shutil.copy(HERE / "shared/grade.py", d / "tests/grade.py")
            std = ROOT / "scripts/eai_standard"
            for f in ("rcb_client.py", "rcb1.py", "client-requirements.txt"):
                shutil.copy(std / f, d / "environment" / f)
            for f in ("rcb_limited.py", "rcb1.py", "run.sh"):
                shutil.copy(std / f, d / "environment/sim" / f)
            for f in ("server.py", "finalize.sh", "rcb_ispatialgym.py"):
                shutil.copy(HERE / "shared" / f, d / "environment/sim" / f)
            for f in SCORING:
                shutil.copy(inst / f, d / "environment/sim" / f)
            (d / "environment/sim/task_text.txt").write_text(
                "Make the scene look like the goal image /app/goal.png, the head camera's view once the task is done; the robot "
                "itself does not have to match it.\n")
        else:
            (d / "environment/Dockerfile").write_text(sub("Dockerfile.environment"))
            (d / "tests/Dockerfile").write_text(sub("Dockerfile.tests"))
            (d / "tests/docker-compose.yaml").write_text(sub("docker-compose.tests.yaml"))
            shutil.copy(mt / "test.sh", d / "tests/test.sh")
            shutil.copy(HERE / "shared/grade_privileged.py", d / "tests/grade.py")
            shutil.copy(HERE / "shared/rcb_ispatialgym.py", d / "environment/rcb_ispatialgym.py")
            shutil.copy(HERE / "shared/rcb_ispatialgym.py", d / "tests/rcb_ispatialgym.py")
            shutil.copy(inst / "instance.json", d / "environment/instance.json")
            (d / "environment/scrub").mkdir()
            for f in ("scrub.sh", "neutral_bddl.py"):
                shutil.copy(HERE / "shared" / f, d / "environment/scrub" / f)
            for f in SCORING:
                shutil.copy(inst / f, d / "tests" / f)
    for mode in MODES:                      # once both exist: each README's Twin row names the other
        tc.normalize(out / task_dir_name(t, mode))


def cmd_render(a, out: Path | None = None) -> None:
    out = out or ROOT / "tasks"
    for t in tasks():
        render_task(t, out)
    print(f"rendered {len(tasks())} tasks x {len(MODES)} modes into {out}")


def cmd_check(a) -> None:
    with tempfile.TemporaryDirectory() as td:
        cmd_render(a, Path(td))
        bad = []
        for n in (task_dir_name(t, m) for t in tasks() for m in MODES):
            new, old = Path(td) / n, ROOT / "tasks" / n
            files = {p.relative_to(new) for p in new.rglob("*") if p.is_file()} | \
                    ({p.relative_to(old) for p in old.rglob("*") if p.is_file()} if old.exists() else set())
            bad += [f"{n}/{f}" for f in sorted(files) if not (new / f).is_file() or not (old / f).is_file()
                    or (new / f).read_bytes() != (old / f).read_bytes()]
        extra = sorted(p.name for p in (ROOT / "tasks").glob("ispatialgym-*") if p.name not in {task_dir_name(t, m) for t in tasks() for m in MODES})
        if bad or extra:
            raise SystemExit("tasks/ differs from what mk_tasks.py renders: " + ", ".join((bad + extra)[:20]))
    print(f"ok: {len(tasks())} iSpatialGym tasks are what mk_tasks.py renders")


def _docker(task: str, args: str, out: Path) -> str:
    """One fresh process of the tooling in the image, on the GPU, with the licensed dataset mounted as the tasks mount it."""
    data = os.environ["RCB_BEHAVIOR_DATA"]
    image = f"ghcr.io/mll-lab-nu/eai-ispatialgym:{(ROOT / 'images/ispatialgym/VERSION').read_text().strip()}"
    gpus = os.environ.get("RCB_ISG_GPU")            # one device of a multi-GPU host, e.g. 2 (default: all)
    gpus = f"'\"device={gpus}\"'" if gpus else "all"
    cmd = (f"docker run --rm --gpus {gpus} --shm-size 8g -v {data}:/bdata:ro -v {HERE / 'instances' / task}:/srv/instance:ro "
           f"-v {HERE / 'shared'}:/srv/tool:ro -v {out}:/out -v rcb-isg-measure-cache:/cache --entrypoint python {image} "
           f"/srv/tool/rcb_ispatialgym.py {args}")
    r = subprocess.run(["sg", "docker", "-c", cmd], capture_output=True, text=True)
    (out / "measure.log").open("a").write(f"$ {args}\n{r.stdout}\n{r.stderr[-20000:]}\n")
    return r.stdout


def _last(stdout: str, prefix: str = "") -> dict:
    lines = [ln[len(prefix):] for ln in stdout.splitlines() if ln.startswith(prefix + "{")]
    return json.loads(lines[-1]) if lines else {}


def cmd_measure(a) -> None:
    """facts.json of one task, from three fresh processes: holding still for the whole budget (must not succeed), the
    determinism probe live, and its replay (the final states must be equal)."""
    out = Path(a.work) / a.task
    out.mkdir(parents=True, exist_ok=True)
    hold = _last(_docker(a.task, "freeze --instance /srv/instance --hold", out), "FACTS ")
    probe = _last(_docker(a.task, f"freeze --instance /srv/instance --probe {a.probe} --out-traj /out/probe.npz", out), "FACTS ")
    rep = _last(_docker(a.task, "replay --instance /srv/instance --traj /out/probe.npz --video /out/probe.mp4", out))
    r0 = (rep.get("replays") or [{}])[0]
    if not (hold and probe and r0):
        raise SystemExit(f"{a.task}: a measurement process gave no result (see {out}/measure.log)")
    facts = {k: hold[k] for k in ("subtask", "start_sha", "start_poses", "max_steps", "settle_steps", "action_dim", "tolerances", "cameras",
                                  "head_camera", "joint_types")}
    facts["hold"] = {k: hold["hold"][k] for k in ("success", "steps", "reason", "symbolic_success", "geometric_success", "step_s")}
    facts["start_same"] = hold["start_sha"] == probe["start_sha"] == rep.get("start_sha")
    facts["probe"] = {"rows": a.probe, "live_sha": probe["probe"]["state_sha"], "replay_sha": r0.get("state_sha"),
                      "deterministic": probe["probe"]["state_sha"] == r0.get("state_sha")}
    facts["load_s"] = [hold["load_s"], probe["load_s"]]
    (HERE / "instances" / a.task / "facts.json").write_text(json.dumps(facts, indent=1) + "\n")
    print(f"{a.task}: start_same {facts['start_same']}, hold success {facts['hold']['success']} ({facts['hold']['steps']} steps), "
          f"deterministic {facts['probe']['deterministic']}")


def main() -> None:
    if sys.argv[1:] == ["--check"]:
        return cmd_check(None)
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("render")
    s = sub.add_parser("instances")
    s.add_argument("--data", required=True, help="upstream's eval data at subset.toml's upstream_data (the Hugging Face dataset, ispatialgym-eval-instances/)")
    s.add_argument("--bddl", required=True, help="ispatialgym/assets/bddl of iSpatialGym at subset.toml's upstream (only hashed)")
    s = sub.add_parser("measure", help="facts.json of one task (needs the image, a GPU and $RCB_BEHAVIOR_DATA)")
    s.add_argument("--task", required=True)
    s.add_argument("--probe", type=int, default=300, help="rows of the determinism probe")
    s.add_argument("--work", default="/tmp/rcb-isg-measure", help="where the processes' logs and the probe go")
    a = p.parse_args()
    {"instances": cmd_instances, "measure": cmd_measure, "render": cmd_render}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
