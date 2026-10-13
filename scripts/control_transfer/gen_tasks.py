#!/usr/bin/env python3
"""Self-contained native Harbor task generation; trusted code never copied into the agent."""

import ast, hashlib, json, os, shutil, sys, tempfile
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


def copy_legacy_package(task, where, private, family):
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


# Explicit agent-visible files: new evaluator helpers must never become public
# merely because someone added a Python file beside the nominal trainer.
PUBLIC_MODULES = {
    "neural-fly": ("fly.py",),
    "g1": ("g1.py", "g1_training.py"),
    "anycar": ("anycar.py", "anycar_nominal.py"),
    "go2": ("go2.py", "go2_data.py", "go2_nominal.py", "go2_train.py"),
}
G1_PUBLIC = set()


def copy_package(task, where, private, family):
    if family not in PUBLIC_MODULES:
        return copy_legacy_package(task, where, private, family)
    for path in (
        "scripts/__init__.py",
        "scripts/control_transfer/__init__.py",
        "scripts/control_transfer/components/__init__.py",
    ):
        put(task, where + "/" + path, "")
    names = ("__init__.py", "client.py", "weights.py", *PUBLIC_MODULES[family])
    for name in names:
        source = SRC / "control_public" / name
        for prefix in ("control_public/", "scripts/control_transfer/control_public/"):
            put(task, where + "/" + prefix + name, source.read_text())
    packages = {"neural-fly": [], "g1": ["sim2realbench"], "anycar": ["anycarbench"], "go2": ["quadrupedbench"]}[family]
    for package in packages:
        for source in sorted((SRC / "components" / package).rglob("*")):
            if not source.is_file() or source.is_symlink():
                continue
            relative = source.relative_to(SRC / "components" / package).as_posix()
            if source.suffix not in (".py", ".json") and source.name not in (
                "LICENSE.anycar",
                "LICENSE.f1db",
                "NOTICE",
            ):
                continue
            if (
                private
                and family == "go2"
                and source.name in ("reference.py", "search_reference.py", "validate_cpu.py")
            ):
                continue
            if not private:
                if family == "g1" and relative not in G1_PUBLIC:
                    continue
                if family == "anycar" and relative not in (
                    "__init__.py",
                    "model.py",
                    "tracks.py",
                    "circuits.json",
                    "LICENSE.anycar",
                    "LICENSE.f1db",
                    "NOTICE",
                ):
                    continue
                if family == "go2":
                    continue
            content = source.read_text()
            if not private and source.name in ("contract.py", "assets.py"):
                tree = ast.parse(content)
                tree.body = [
                    n
                    for n in tree.body
                    if not (
                        isinstance(n, ast.Assign)
                        and any(
                            isinstance(t, ast.Name) and t.id in ("REFERENCE", "PROMPT", "POLICY") for t in n.targets
                        )
                        or isinstance(n, ast.FunctionDef)
                        and n.name in ("describe", "tools")
                    )
                ]
                content = ast.unparse(tree) + "\n"
            for prefix in ("", "scripts/control_transfer/components/"):
                put(task, where + "/" + prefix + package + "/" + relative, content)
    if packages:
        put(task, where + "/control_assets.py", (SRC / "components/control_assets.py").read_text())
    if private:
        names = ("__init__.py", "adapter.py", "session.py", "service.py", "verify.py", "collect.py", "cpu_runtime.py")
        family_files = {
            "neural-fly": ("fly.py",),
            "g1": (),
            "anycar": ("anycar.py", "anycar_spec.py"),
            "go2": ("go2.py", "go2_spec.py"),
        }
        for name in (*names, *family_files[family]):
            put(task, where + "/scripts/control_transfer/trusted/" + name, (SRC / "trusted" / name).read_text())
        for name in ("anycar_spec.py",):
            if family == "anycar" and (SRC / name).exists():
                put(task, where + "/scripts/control_transfer/" + name, (SRC / name).read_text())
    if family == "neural-fly" and (SRC / "neuralfly_nominal.py").exists():
        for name in ("neuralfly_nominal.py", "neuralfly_video.py", "neuralfly_constants.py"):
            content = (SRC / name).read_text()
            put(task, where + "/scripts/control_transfer/" + name, content)
            put(task, where + "/" + name, content)
        if not private:
            put(task, where + "/nominal_fly.py", (SRC / "neuralfly_nominal.py").read_text())


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
    native_full = name in ("neural-fly", "anycar", "go2-attitude")
    oracle = "full" if native_full else "none"
    if native_full:
        reference_note = "Scripted reference and native Harbor no-submission checks pass on both development instances with resource enforcement and exact CPU replay. These are integration references, not LLM scores."
    elif instance.get("task_variant") == "circuit-sector/1":
        reference_note = "Development-only circuit-sector variant. Local nominal-controller sector smoke covers all 78 historical venues plus zigzag, but full multi-round/held-out native Harbor acceptance is not established for these circuit tasks. No verified full oracle or LLM score is claimed."
    elif family == "g1":
        reference_note = "No full oracle. The local trained reference passes 17 of 24 held-out cases; both plants remain incompletely solved. Native GPU training validation remains outstanding. Human review required."
    else:
        reference_note = "Development-only: the fixed numeric reference candidate does not solve the held-out bank. Native replay and no-submission checks validate infrastructure, not solvability. Human review required."
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
oracle = "{oracle}"
oracle_evidence = "{reference_note}"
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
    if family == "g1":
        training = "Train the public terrain curriculum with `python -m control_public.g1_training --upstream /opt/control-assets/unitree_rl_mjlab --out /app/output/trained --gpu 0`. You may edit training code. Submit the exported `policy.npz` using `client.artifact(path)`. The fixed actor architecture and PD wrapper are the deployment ABI. Record actual training steps, logs and hardware."
    if family == "go2":
        training += f" Run `python -m control_public.go2_train --assets /opt/control-assets/go2 --task {name[4:]} --out /app/output/nominal` for local nominal rollouts. The controller ABI and editable training helpers are in `control_public.go2`."
    if family == "anycar":
        training += " Run `python -m scripts.control_transfer.control_public.anycar_nominal --out /app/output/nominal` for local nominal rollouts. The public controller ABI is in `control_public.anycar`."
    if instance.get("task_variant") == "circuit-sector/1":
        training += f" Use `--track {public['track_id']}` to train on this task's public route, and `--full-lap` for nominal full-lap practice. Deployment evaluates 24-second sectors; full-lap practice does not change that horizon."
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
{reference_note}

## Verification
Frozen development and held-out banks, data-only deployment, fresh-process state hashes, separate no-network verifier. All numeric scores and physical outcomes are operator-only until submission closes.

## Details
{public["limitations"]}
""",
    )
    put(task, "tests/grade.py", (SRC / "trusted/verify.py").read_text())
    put(task, "tests/test.sh", "#!/bin/bash\nmkdir -p /logs/verifier\npython /tests/grade.py\n", True)
    # Bind Docker's layer cache to the exact frozen instance as well as the
    # build context. Equal-size files staged with equal mtimes otherwise reused
    # a stale COPY layer in the native validation host's BuildKit file sync.
    instance_bytes_sha = hashlib.sha256((task / "tests/instance.json").read_bytes()).hexdigest()
    put(
        task,
        "tests/Dockerfile",
        f"FROM {BASE}\n"
        f'LABEL roboengineer.instance_sha256="{instance_bytes_sha}"\n'
        "COPY grade.py test.sh instance.json /tests/\n"
        f"RUN echo '{instance_bytes_sha}  /tests/instance.json' | sha256sum -c - && chmod +x /tests/test.sh\n",
    )
    put(
        task,
        "solution/solve.sh",
        "#!/bin/bash\n# No verified oracle: this task is explicitly oracle=none.\nexit 0\n",
        True,
    )
    if family == "neural-fly":
        put(task, "solution/neuralfly_reference.py", (SRC / "neuralfly_reference.py").read_text())
        put(
            task,
            "solution/solve.sh",
            "#!/bin/bash\nset -euo pipefail\ncd /app\npython /solution/neuralfly_reference.py --out /app/output/reference\n",
            True,
        )
    if family == "anycar":
        reference = (
            (SRC / "trusted/anycar_reference.py")
            .read_text()
            .replace("from ..control_public.anycar", "from control_public.anycar")
        )
        reference += (
            "\nif __name__ == '__main__':\n"
            "    from control_public.client import Client\n"
            "    from control_public.anycar import DEFAULT\n"
            "    client = Client()\n"
            "    client.describe()\n"
            "    iterate(client, DEFAULT, '/app/output/reference')\n"
        )
        put(task, "solution/reference.py", reference)
        put(task, "solution/solve.sh", "#!/bin/bash\nset -euo pipefail\ncd /app\npython /solution/reference.py\n", True)
    if family == "go2":
        from scripts.control_transfer.components.quadrupedbench.reference import policy

        candidate = policy(name[4:])
        solve = (
            "from control_public.client import Client\nc = Client()\nc.describe()\npolicy = "
            + repr(candidate)
            + "\nfor i in range(3):\n    r = c.deploy(policy, 'Fixed scripted reference candidate; repeated for lifecycle validation.')\n"
            + "c.seal(r['round_id'], 'Reference candidate; full success is not assumed.')\n"
        )
        put(task, "solution/reference.py", solve)
        put(task, "solution/solve.sh", "#!/bin/bash\nset -euo pipefail\ncd /app\npython /solution/reference.py\n", True)
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
    # normalize adds the resource-limit grader and rewrites test.sh. Bind every
    # copied input after that step, before Docker evaluates either COPY layer.
    inputs = {
        name: hashlib.sha256((task / "tests" / name).read_bytes()).hexdigest()
        for name in ("grade.py", "test.sh", "instance.json", "rcb_limits.py", "rcb_limits.json")
    }
    payload_sha = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()
    dockerfile = task / "tests/Dockerfile"
    lines = dockerfile.read_text().splitlines()
    lines.insert(1, f'LABEL roboengineer.verifier_inputs_sha256="{payload_sha}"')
    checks = " && ".join(f"echo '{sha}  /tests/{name}' | sha256sum -c -" for name, sha in inputs.items())
    # Copy the checked inputs together. Keep normalize's monitor COPY last so
    # another normalization is a no-op; its duplicate files have identical bytes.
    lines = [
        line.replace(
            "COPY grade.py test.sh instance.json /tests/",
            "COPY grade.py test.sh instance.json rcb_limits.py rcb_limits.json /tests/",
        )
        for line in lines
    ]
    lines.insert(next(i for i, line in enumerate(lines) if line.startswith("# resource limits:")), "RUN " + checks)
    dockerfile.write_text("\n".join(lines) + "\n")


def main():
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["render", "check", "list-circuits"])
    selection = p.add_mutually_exclusive_group()
    selection.add_argument(
        "--circuit", action="append", help="Opt-in circuit layout or venue alias; repeat to select several"
    )
    selection.add_argument(
        "--all-circuits",
        action="store_true",
        help="Opt-in all 159 runnable historical layouts plus zigzag (320 self-contained tasks)",
    )
    p.add_argument(
        "--output-root", type=Path, default=ROOT / "tasks", help="Task directory parent; defaults to repository tasks/"
    )
    a = p.parse_args()
    if a.action == "list-circuits":
        from scripts.control_transfer.components.anycarbench.tracks import track_ids

        print(json.dumps(track_ids(), indent=2))
        return
    if a.circuit or a.all_circuits:
        from scripts.control_transfer.components.anycarbench.tracks import resolve_track, track_ids

        try:
            circuits = track_ids() if a.all_circuits else sorted({resolve_track(name) for name in a.circuit})
        except ValueError as error:
            p.error(str(error))
        names = ["anycar-circuit-v1-" + name for name in circuits]
    else:
        names = list(FAMILIES)
        # Optional tasks, if materialized, are still covered by the default check.
        names += sorted(
            {
                path.name.removeprefix("control-transfer-").removesuffix("-standard").rsplit("-i", 1)[0]
                for path in a.output_root.glob("control-transfer-anycar-circuit-v1-*-i??-standard")
                if path.is_dir()
            }
        )
    os.umask(0o022)
    bad = []
    for name in names:
        for i in range(2):
            ident = f"control-transfer-{name}-i{i:02d}-standard"
            target = a.output_root / ident
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
    print(f"control transfer: {2 * len(names)} tasks " + a.action)


if __name__ == "__main__":
    main()
