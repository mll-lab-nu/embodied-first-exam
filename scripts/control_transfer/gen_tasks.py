#!/usr/bin/env python3
"""Self-contained native Harbor task generation; trusted code never copied into the agent."""

import ast, json, os, shutil, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from scripts.control_transfer.specs import FAMILIES, spec
from task_conventions import normalize, cutoff_sec
from scripts.quadrotor_landing.gen_tasks import BASE, HOSTS, put, snapshot

IMAGE = "ghcr.io/mll-lab-nu/eai-control-transfer:0.1.0"
EMBODIMENTS = {"neural-fly": "drone", "g1": "humanoid", "anycar": "racing-car", "go2": "quadruped"}
ROBOTS = {"neural-fly": "neural-fly-partial", "g1": "unitree-g1", "anycar": "anycar", "go2": "unitree-go2"}


def copy_package(task, where, private, family):
    for p in ["scripts/__init__.py", "scripts/control_transfer/__init__.py"]:
        put(task, where + "/" + p, "")
    for p in sorted((SRC / "control_public").glob("*.py")):
        put(task, where + "/scripts/control_transfer/control_public/" + p.name, p.read_text())
    # A top-level alias avoids a namespace collision with the upstream G1 training scripts package.
    for p in sorted((SRC / "control_public").glob("*.py")):
        put(task, where + "/control_public/" + p.name, p.read_text())
    packages = {
        "neural-fly": [],
        "spacecraft": ["nonlinearbench"],
        "yam": ["manipulationbench"],
        "linearbot": ["locomanipbench"],
        "g1": ["sim2realbench"],
    }[family]
    for package in packages:
        for p in sorted((SRC / "components" / package).rglob("*")):
            if p.suffix not in (".py", ".json"):
                continue
            if not private and p.name in ("deploy.py",):
                continue
            text = p.read_text()
            if not private and p.name == "contract.py":
                tree = ast.parse(text)
                nodes = [
                    n
                    for n in tree.body
                    if not (
                        isinstance(n, ast.Assign)
                        and any(isinstance(t, ast.Name) and t.id in ("REFERENCE", "PROMPT") for t in n.targets)
                    )
                ]
                nodes = [n for n in nodes if not (isinstance(n, ast.FunctionDef) and n.name in ("describe", "tools"))]
                text = ast.unparse(ast.Module(body=nodes, type_ignores=[])) + "\n"
            if not private and p.name == "simulation.py":
                # Public nominal training copy: cannot instantiate deployment parameter draws.
                if package == "nonlinearbench":
                    tree = ast.parse(text)
                    for n in tree.body:
                        if isinstance(n, ast.FunctionDef) and n.name == "parameters":
                            n.body = ast.parse(
                                "return {'mass':10.,'inertia':[.55,.65,.5],'radius':6971100.,'force_scale':[1.]*3,'torque_scale':[1.]*3,'misalignment':[0.]*3,'lag':.15,'delay':0,'force_bias':[0.]*3,'torque_bias':[0.]*3}"
                            ).body
                    text = ast.unparse(tree) + "\n"
                elif package == "manipulationbench":
                    text = text.replace("nominal=False", "nominal=True")
            put(task, where + "/" + str(p.relative_to(SRC / "components")), text)
    if packages:
        put(task, where + "/control_assets.py", (SRC / "components/control_assets.py").read_text())
    if private:
        for p in sorted((SRC / "trusted").glob("*.py")):
            put(task, where + "/scripts/control_transfer/trusted/" + p.name, p.read_text())


def render(task, name, index):
    instance = spec(name, index)
    family = instance["family"]
    instance["evaluation_requirements"] = {
        "physics": "mujoco-cpu",
        "mujoco_version": "3.5.0",
        "policy_inference": "numpy-cpu",
        "render_backend": "osmesa",
        "gpu_devices": [],
        "device_isolation_verified": True,
    }
    gpu = family in ("linearbot", "g1")
    seconds = cutoff_sec("Control Transfer", "standard")
    if family == "neural-fly":
        instance.update(
            private_asset="/opt/private-fly/forces.npz",
            private_asset_sha256="551eeb0d8e2c75e157c087f1ab2f5e40e68400a84fdf0882ed719ddfcfd8108a",
        )
    for folder in ("environment/sim", "tests"):
        put(task, folder + "/instance.json", json.dumps(instance, sort_keys=True, indent=2) + "\n")
    copy_package(task, "environment/public", False, family)
    copy_package(task, "environment/sim", True, family)
    put(task, "environment/public/task-spec.json", json.dumps(instance["public"], indent=2) + "\n")
    put(
        task,
        "environment/Dockerfile",
        f"""FROM {IMAGE}-{"train" if gpu else "nominal"}
WORKDIR /app
COPY public/ /app/
ENV PYTHONPATH=/app OPENBLAS_NUM_THREADS=1 MUJOCO_GL=osmesa
RUN mkdir -p /app/output
""",
    )
    reservation = (
        """    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
"""
        if gpu
        else ""
    )
    put(
        task,
        "environment/docker-compose.yaml",
        f'''services:
  main:
    depends_on:
      sim:
        condition: service_healthy
{reservation}  sim:
    image: {IMAGE}
    volumes:
      - ./sim:/srv:ro
    working_dir: /srv
    command: python -m scripts.control_transfer.trusted.service
    environment:
      PYTHONPATH: /srv
      MUJOCO_GL: osmesa
      CUDA_VISIBLE_DEVICES: ""
      NVIDIA_VISIBLE_DEVICES: void
      LIBGL_ALWAYS_SOFTWARE: "1"
      ROBOENGINEER_ENFORCE_CPU_ISOLATION: "1"
      RCB_INSTANCE: /srv/instance.json
      RCB_WALL_CLOCK_S: "{seconds}"
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]
      interval: 5s
      timeout: 3s
      start_period: 60s
      retries: 3
''',
    )
    put(
        task,
        "task.toml",
        f'''schema_version = "1.3"
artifacts = [{{ source = "/data/", service = "sim" }}, "/app/output/"]
[task]
name = "robot-coding-bench/{task.name}"
description = "{instance["public"]["goal"]}"
authors = [{{name = "Robotic Engineering Bench contributors"}}]
keywords = ["robotics", "policy", "adaptation", "mujoco"]
[metadata]
author_name = "Robotic Engineering Bench contributors"
author_org = "Robotic Engineering Bench"
collection = "roboEngineer"
embodiment = "{EMBODIMENTS[family]}"
task_type = "policy"
simulator = "mujoco"
robot = "{ROBOTS[family]}"
family = "control-transfer/{name}"
mode = "standard"
protocol = "eai-policy/1.1"
oracle = "none"
oracle_evidence = "Implementation validation is separate from a successful reference. Native Harbor oracle/nop validation and reference calibration pending."
instance_seed = {index}
expert_time_estimate_hours = 4.0
[verifier]
timeout_sec = 1800.0
environment_mode = "separate"
network_mode = "no-network"
[[verifier.collect]]
service = "sim"
command = "python -m scripts.control_transfer.trusted.collect"
timeout_sec = 1800
[agent]
timeout_sec = {seconds}.0
network_mode = "allowlist"
allowed_hosts = {json.dumps(HOSTS)}
[environment]
build_timeout_sec = 2400.0
cpus = {8 if gpu else 2}
memory_mb = {24576 if gpu else 6144}
[verifier.environment]
build_timeout_sec = 600.0
''',
    )
    public = instance["public"]
    training = (
        """Train in your local nominal model. Linearbot: `python -m locomanipbench.imitation_train --robot linearbot --out /app/output/initial --device cuda:0`, then `CONTROL_INITIAL_POLICY=/app/output/initial/policy.npz python -m locomanipbench.train --robot linearbot --out /app/output/trained --device cuda:0`. G1: `python -m sim2realbench.g1.train --out /app/output/trained --gpu 0`. You may edit training code. Submit the exported `policy.npz` using `client.artifact(path)`. The fixed actor shape/activation and PD wrapper are the deployment ABI; editing them locally does not change evaluation. Record actual training steps and hardware."""
        if gpu
        else """Use the public nominal model and write fitting/optimization code locally. Submit the documented numeric controller parameters. This track evaluates adaptation within a fixed controller ABI; it does not deploy arbitrary controller Python."""
    )
    if family == "neural-fly":
        training += " The reference and controller are in `control_public.fly`; a public nominal simulator is provided in `nominal_fly.py`."
    put(
        task,
        "instruction.md",
        f"""# {name}

{public["goal"]}

## Train, deploy, inspect and revise
{training}

Use `from control_public.client import Client, artifact`; `Client().describe()` provides the public defaults and bounds. Call `deploy(policy, diagnosis)` for up to three rounds. Each round reuses the same {public["adaptation_cases"]} development cases. Diagnose failures from the returned video frames and noisy telemetry, then revise. Preserve code, training logs, policies and exact feedback under `/app/output/`. The client saves the exact response and image bytes. A diagnosis should briefly state the observed failure, proposed change and expected effect.

`seal(round_id, summary)` selects a completed round. No held-out feedback is returned. At agent exit the evaluator uses the sealed round or the latest round completed before cutoff; no eligible round scores zero. Hidden simulation runs in a separate container and accepts data-only policies. Network endpoint: `http://127.0.0.1:8000`. No reset or privileged-state endpoint exists.

## Verification and score
{public["score"]}
The selected policy is tested on {public["held_out_cases"]} disjoint cases in two fresh processes. Binary success requires all cases to pass; `final_reward` reports the continuous mean score. Evaluation dynamics, seeds, true state, contacts and grades are never returned during adaptation.

## Modeling limitations
{public["limitations"]}
""",
    )
    put(
        task,
        "README.md",
        f"""# {task.name}

{public["goal"]}

## Difficulty
Infer transfer failures from video and noisy sensors across bounded adaptation rounds.

## Reference solution
No verified full oracle yet. Reference implementation checks are not model scores.

## Verification
Frozen development and held-out banks, data-only deployment, fresh-process state hashes, separate no-network verifier. All numeric scores and physical outcomes are operator-only until submission closes.

## Details
{public["limitations"]}
""",
    )
    put(task, "tests/grade.py", (SRC / "trusted/verify.py").read_text())
    put(task, "tests/test.sh", "#!/bin/bash\nmkdir -p /logs/verifier\npython /tests/grade.py\n", True)
    put(
        task,
        "tests/Dockerfile",
        f"FROM {BASE}\nCOPY grade.py test.sh instance.json /tests/\nRUN chmod +x /tests/test.sh\n",
    )
    put(
        task,
        "solution/solve.sh",
        "#!/bin/bash\n# No verified oracle: this task is explicitly oracle=none.\nexit 0\n",
        True,
    )
    if family == "neural-fly":
        s = (SRC / "trusted/fly.py").read_text().replace("from ..control_public.fly", "from control_public.fly")
        s = s.replace(
            "    weights = None\n    if asset:",
            "    asset = None  # Public simulator has nominal dynamics only.\n    weights = None\n    if asset:",
        )
        put(task, "environment/public/nominal_fly.py", s)
    if family == "spacecraft":
        from nonlinearbench.contract import REFERENCE

        solve = (
            "from control_public.client import Client\nc=Client()\npolicy="
            + repr(REFERENCE)
            + "\nfor i in range(3):\n r=c.deploy(policy, 'Reference nonlinear controller; fixed repeated policy for integration validation.')\nc.seal(r['round_id'],'Reference integration run.')\n"
        )
        put(task, "solution/reference.py", solve)
        put(task, "solution/solve.sh", "#!/bin/bash\nset -euo pipefail\ncd /app\npython /solution/reference.py\n", True)
    normalize(task)


def main():
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["render", "check"])
    a = p.parse_args()
    os.umask(0o022)
    bad = []
    for name in FAMILIES:
        for i in range(2):
            ident = f"control-transfer-{name}-i{i:02d}-standard"
            target = ROOT / "tasks" / ident
            with tempfile.TemporaryDirectory() as t:
                task = Path(t) / ident
                render(task, name, i)
                if a.action == "render":
                    if target.exists():
                        shutil.rmtree(target)
                    shutil.copytree(task, target)
                elif not target.exists() or snapshot(task) != snapshot(target):
                    bad.append(ident)
    if bad:
        raise SystemExit("Generated tasks differ: " + ", ".join(bad))
    print(f"control transfer: {2 * len(FAMILIES)} tasks " + a.action)


if __name__ == "__main__":
    main()
