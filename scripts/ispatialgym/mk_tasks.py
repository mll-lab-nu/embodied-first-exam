"""iSpatialGym task generator (docs/benchmarks/ispatialgym.md): subset.toml -> tasks/ispatialgym-<task>-i00-standard.

  python3 scripts/ispatialgym/mk_tasks.py instances --data <ispatialgym-eval-data> --bddl <iSpatialGym>/ispatialgym/assets/bddl
      copy each picked instance from upstream into instances/<task>/, in the layout run_isg loads a sampler output from
      (template.json, template_meta.json, activity_definitions/, instances/<id>-tro_state.json) + goal.png
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
        (out / "instances").mkdir(parents=True)
        activity, did = rec["problem"].rsplit("-", 1)
        shutil.copy(files["template"], out / "template.json")
        shutil.copy(files["template_meta"], out / "template_meta.json")
        shutil.copytree(Path(a.bddl) / "activity_definitions" / activity, out / "activity_definitions" / activity)
        iid = files["tro_state"].name[: -len(TRO_SUFFIX)]
        shutil.copy(files["tro_state"], out / "instances" / files["tro_state"].name)
        shutil.copy(files["goal_rgb"], out / "goal.png")
        ep = episodes[(t["subtask"], t["instance"])]
        upstream = {"task_family": rec["task_family"], "task": rec["task"], "subtask": rec["subtask"], "instance": rec["instance"],
                    "scene": rec["scene"], "problem": rec["problem"], "activity": activity, "definition_id": int(did),
                    "instance_id": iid, "demo_length": ep["length"],
                    "files_sha256": {k: sha256(v) for k, v in files.items() if k != "oracle"}}
        (out / "upstream.json").write_text(json.dumps(upstream, indent=1) + "\n")
        print(f"{t['task']}: {rec['subtask']} #{rec['instance']} ({rec['scene']}, {rec['problem']}, demo {ep['length']} steps)")


def agent_hosts() -> list[str]:
    """The hosts every task's agent may reach: scripts/set_agent_egress.py's HOSTS (read, not imported: it acts on import)."""
    import ast
    tree = ast.parse((ROOT / "scripts/set_agent_egress.py").read_text())
    return next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "HOSTS" for t in n.targets))


def task_dir_name(t: dict) -> str:
    return f"ispatialgym-{t['task'].replace('_', '-')}-i00-standard"


def _num(v: float) -> str:
    return f"{v:.3g}"


def targets_text(task: str, facts: dict) -> str:
    """The measured targets of the instance as the instruction states them: what kind of pose, never which object."""
    tro = json.loads(next((HERE / "instances" / task / "instances").glob("*" + TRO_SUFFIX)).read_text())["ispatialgym"]
    pose_t = tro.get("pose_targets") or {}
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
    d = out / task_dir_name(t)
    if d.exists():
        shutil.rmtree(d)
    (d / "environment/sim").mkdir(parents=True); (d / "tests").mkdir()
    tpl = HERE / "templates"
    hold_step_s = facts["hold"]["step_s"]
    loads = [int(x) for x in facts["load_s"]]
    collect_s = int(3600 + 2 * (1500 + facts["max_steps"] * hold_step_s * 1.5) + 600)
    v = {"name": d.name, "task": t["task"], "subtask": t["subtask"], "family": t["family"], "family_kw": t["family"].replace("_", "-"),
         "expert_hours": t.get("expert_hours", 1.0), "max_steps": facts["max_steps"], "max_steps_s": f"{facts['max_steps'] / 30:.1f}",
         "max_steps_reason": "failed: the episode's control steps ran out", "collect_s": collect_s,
         "steps_per_s": f"{1.0 / hold_step_s:.0f}", "load_range": f"{min(loads)}-{max(loads)}", "targets": targets_text(t["task"], facts),
         "scene": up["scene"], "description": t["description"], "start_sha": facts["start_sha"],
         "image_version": (ROOT / "images/ispatialgym/VERSION").read_text().strip(),
         "allowed_hosts": ", ".join(f'"{h}"' for h in agent_hosts())}
    sub = lambda name: Template((tpl / name).read_text()).substitute(v)  # noqa: E731
    (d / "task.toml").write_text(sub("task.toml"))
    (d / "instruction.md").write_text(sub("instruction.md"))
    (d / "README.md").write_text(sub("README.md"))
    (d / "environment/docker-compose.yaml").write_text(sub("docker-compose.yaml"))
    shutil.copy(tpl / "Dockerfile.environment", d / "environment/Dockerfile")
    shutil.copy(tpl / "Dockerfile.tests", d / "tests/Dockerfile")
    shutil.copy(tpl / "test.sh", d / "tests/test.sh")
    shutil.copy(HERE / "shared/grade.py", d / "tests/grade.py")
    std = ROOT / "scripts/eai_standard"
    for f in ("rcb_client.py", "rcb1.py", "client-requirements.txt"):
        shutil.copy(std / f, d / "environment" / f)
    for f in ("rcb_limited.py", "rcb1.py", "run.sh"):
        shutil.copy(std / f, d / "environment/sim" / f)
    for f in ("server.py", "finalize.sh", "rcb_ispatialgym.py"):
        shutil.copy(HERE / "shared" / f, d / "environment/sim" / f)
    shutil.copy(inst / "goal.png", d / "environment/goal.png")
    shutil.copytree(inst, d / "environment/sim/instance", ignore=shutil.ignore_patterns("goal.png"))
    (d / "environment/sim/instance/task_text.txt").write_text(
        "Make the scene look like the goal image /app/goal.png, the head camera's view once the task is done; the robot "
        "itself does not have to match it.\n")
    sys.path.insert(0, str(ROOT / "scripts"))
    import task_conventions as tc
    tc.normalize(d)


def cmd_render(a, out: Path | None = None) -> None:
    out = out or ROOT / "tasks"
    for t in tasks():
        render_task(t, out)
    print(f"rendered {len(tasks())} tasks into {out}")


def cmd_check(a) -> None:
    with tempfile.TemporaryDirectory() as td:
        cmd_render(a, Path(td))
        bad = []
        for t in tasks():
            n = task_dir_name(t)
            new, old = Path(td) / n, ROOT / "tasks" / n
            files = {p.relative_to(new) for p in new.rglob("*") if p.is_file()} | \
                    ({p.relative_to(old) for p in old.rglob("*") if p.is_file()} if old.exists() else set())
            bad += [f"{n}/{f}" for f in sorted(files) if not (new / f).is_file() or not (old / f).is_file()
                    or (new / f).read_bytes() != (old / f).read_bytes()]
        extra = sorted(p.name for p in (ROOT / "tasks").glob("ispatialgym-*") if p.name not in {task_dir_name(t) for t in tasks()})
        if bad or extra:
            raise SystemExit("tasks/ differs from what mk_tasks.py renders: " + ", ".join((bad + extra)[:20]))
    print(f"ok: {len(tasks())} iSpatialGym tasks are what mk_tasks.py renders")


def _docker(task: str, args: str, out: Path) -> str:
    """One fresh process of the tooling in the image, on the GPU, with the licensed dataset mounted as the tasks mount it."""
    data = os.environ["RCB_BEHAVIOR_DATA"]
    image = f"ghcr.io/mll-lab-nu/eai-ispatialgym:{(ROOT / 'images/ispatialgym/VERSION').read_text().strip()}"
    cmd = (f"docker run --rm --gpus all --shm-size 8g -v {data}:/bdata:ro -v {HERE / 'instances' / task}:/srv/instance:ro "
           f"-v {HERE / 'shared'}:/srv/tool:ro -v {out}:/out -v rcb-isg-measure-{task}:/cache --entrypoint python {image} "
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
    s.add_argument("--data", required=True, help="a checkout of kmy17518/ispatialgym-eval-data at subset.toml's upstream_data")
    s.add_argument("--bddl", required=True, help="ispatialgym/assets/bddl of iSpatialGym at subset.toml's upstream")
    s = sub.add_parser("measure", help="facts.json of one task (needs the image, a GPU and $RCB_BEHAVIOR_DATA)")
    s.add_argument("--task", required=True)
    s.add_argument("--probe", type=int, default=300, help="rows of the determinism probe")
    s.add_argument("--work", default="/tmp/rcb-isg-measure", help="where the processes' logs and the probe go")
    a = p.parse_args()
    {"instances": cmd_instances, "measure": cmd_measure, "render": cmd_render}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
