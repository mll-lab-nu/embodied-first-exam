#!/usr/bin/env python3
"""Self-contained native Harbor task generation; trusted code never copied into the agent."""

import ast, hashlib, json, os, shutil, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from scripts.control_transfer.specs import FAMILIES, spec
from scripts.control_transfer.packaging import TASK_NAMES, TASK_ROOT, normalize, cutoff_sec, task_dir_name
from scripts.control_transfer.trusted.runtime_limits import runtime_limits, LAP_FAMILY
from scripts.quadrotor_landing.gen_tasks import BASE, HOSTS, put, snapshot

# images/control-transfer/VERSION: the nominal stage for the agent, the evaluator stage for the sim sidecar
IMAGE = "ghcr.io/mll-lab-nu/eai-control-transfer:" + (ROOT / "images/control-transfer/VERSION").read_text().strip()
SKYDIO_IMAGE = IMAGE
# The Neural Fly force surrogate (calibrate_fly.py, staged by images/control-transfer/prepare_assets.py): the evaluator
# checks the staged file against this digest (a different fit is a different benchmark definition).
FLY_ASSET_SHA256 = "8e1c148ed034b9f4c541dfaa71b70b48a652f43c7abcc381416040d7901459b9"
# PROTOCOL §2 scene dynamics: the Neural Fly wind does work on the drone; the other families have no external agent
DYNAMIC = ("neural-fly",)
EMBODIMENTS = {
    "neural-fly": "drone",
    "g1": "humanoid",
    "anycar": "racing-car",
    "go2": "quadruped",
}
ROBOTS = {
    "neural-fly": "neural-fly-partial",
    "g1": "unitree-g1",
    "anycar": "anycar",
    "go2": "unitree-go2",
}
EMBODIMENTS["anycar-drift"] = "racing-car"
ROBOTS["anycar-drift"] = "anycar"
EMBODIMENTS["anycar-drift-v3"] = "racing-car"
ROBOTS["anycar-drift-v3"] = "anycar"


# The reference runs of the shipped tasks (#329 review, board 0146): (task succeeded, held-out cases succeeded, cases,
# mean 0-100 score) per (spec family name, instance index).
EVIDENCE_RUN = "Harbor 0.23.0 oracle agent on aws:rcb-cpu3, 2026-10-18, image eai-control-transfer:0.2.0"
EVIDENCE = {
    ("neural-fly", 0): (True, 10, 10, 90.32), ("neural-fly", 1): (True, 10, 10, 94.30),
    ("neural-fly-general-v1", 0): (True, 10, 10, 87.58), ("neural-fly-general-v1", 1): (False, 8, 10, 71.61),
    ("neural-fly-general-skydio-v1", 0): (True, 10, 10, 87.58), ("neural-fly-general-skydio-v1", 1): (False, 8, 10, 71.61),
    ("neural-fly-vector-wind-v1", 0): (True, 10, 10, 90.01), ("neural-fly-vector-wind-v1", 1): (True, 10, 10, 88.41),
    ("anycar", 0): (True, 10, 10, 73.21), ("anycar", 1): (True, 10, 10, 72.87),
    ("anycar-circuit-compact-v3-monaco-6", 0): (True, 10, 10, 76.69),
    ("anycar-circuit-compact-v3-monaco-6", 1): (True, 10, 10, 76.21),
    ("anycar-circuit-compact-v3-silverstone-8", 0): (True, 10, 10, 77.05),
    ("anycar-circuit-compact-v3-silverstone-8", 1): (True, 10, 10, 76.53),
    ("anycar-drift", 0): (False, 0, 10, 0.0), ("anycar-drift", 1): (False, 0, 10, 0.0),
    ("anycar-drift-v3", 0): (False, 0, 10, 0.0), ("anycar-drift-v3", 1): (False, 1, 10, 6.86),
    ("go2-attitude", 0): (True, 10, 10, 91.06), ("go2-attitude", 1): (True, 10, 10, 91.24),
    ("go2-forward-jump", 0): (False, 0, 10, 0.0), ("go2-forward-jump", 1): (False, 0, 10, 24.50),
    ("go2-yaw-jump", 0): (False, 0, 10, 9.80), ("go2-yaw-jump", 1): (False, 0, 10, 14.70),
    ("go2-weave", 0): (False, 0, 10, 0.0), ("go2-weave", 1): (False, 0, 10, 0.0),
}


def copy_legacy_package(task, where, private, family):
    for p in ["scripts/__init__.py", "scripts/control_transfer/__init__.py"]:
        put(task, where + "/" + p, "")
    for p in sorted((SRC / "control_public").glob("*.py")):
        put(
            task,
            where + "/scripts/control_transfer/control_public/" + p.name,
            p.read_text(),
        )
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
        put(
            task,
            where + "/control_assets.py",
            (SRC / "components/control_assets.py").read_text(),
        )
    if private:
        for p in sorted((SRC / "trusted").glob("*.py")):
            put(
                task,
                where + "/scripts/control_transfer/trusted/" + p.name,
                p.read_text(),
            )


# Explicit agent-visible files: new evaluator helpers must never become public
# merely because someone added a Python file beside the nominal trainer.
PUBLIC_MODULES = {
    "neural-fly": ("fly.py",),
    "g1": ("g1.py", "g1_training.py"),
    "anycar": ("anycar.py", "anycar_nominal.py"),
    "anycar-drift": ("anycar_drift.py", "anycar_drift_nominal.py"),
    "anycar-drift-v3": ("anycar_drift_v3.py", "anycar_drift_v3_nominal.py", "anycar_drift_feedback.py"),
    "go2": ("go2.py", "go2_data.py", "go2_nominal.py", "go2_train.py"),
}
G1_PUBLIC = set()


def copy_package(task, where, private, family, visual_profile=None):
    if family not in PUBLIC_MODULES:
        return copy_legacy_package(task, where, private, family)
    for path in (
        "scripts/__init__.py",
        "scripts/control_transfer/__init__.py",
        "scripts/control_transfer/components/__init__.py",
    ):
        put(task, where + "/" + path, "")
    names = ("__init__.py", "client.py", "weights.py", *PUBLIC_MODULES[family])
    if private and family in ("anycar-drift", "anycar-drift-v3"):
        names += ("anycar.py",)  # Private shared plant/noise sampler imports this ABI.
    for name in names:
        source = SRC / "control_public" / name
        for prefix in ("control_public/", "scripts/control_transfer/control_public/"):
            put(task, where + "/" + prefix + name, source.read_text())
    packages = {
        "neural-fly": [],
        "g1": ["sim2realbench"],
        "anycar": ["anycarbench"],
        "anycar-drift": ["anycarbench"],
        "anycar-drift-v3": ["anycarbench"],
        "go2": ["quadrupedbench"],
    }[family]
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
                if family == "anycar-drift-v3" and relative not in (
                    "__init__.py", "model.py", "drift_v3.py", "LICENSE.anycar",
                ):
                    continue
                if family == "anycar-drift" and relative not in (
                    "__init__.py",
                    "model.py",
                    "drift.py",
                    "LICENSE.anycar",
                ):
                    continue
                if family == "g1" and relative not in G1_PUBLIC:
                    continue
                if family == "anycar" and relative not in (
                    "__init__.py",
                    "model.py",
                    "tracks.py",
                    "circuits.json",
                    "route_lengths.json",
                    "compact_routes.json",
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
        put(
            task,
            where + "/control_assets.py",
            (SRC / "components/control_assets.py").read_text(),
        )
    if private:
        names = (
            "__init__.py",
            "adapter.py",
            "session.py",
            "service.py",
            "verify.py",
            "collect.py",
            "cpu_runtime.py",
            "runtime_limits.py",
        )
        family_files = {
            "neural-fly": ("fly.py",),
            "g1": (),
            "anycar": ("anycar.py", "anycar_spec.py"),
            "anycar-drift": ("anycar_drift.py", "anycar.py", "anycar_spec.py"),
            "anycar-drift-v3": ("anycar_drift_v3.py", "anycar.py", "anycar_spec.py"),
            "go2": ("go2.py", "go2_spec.py"),
        }
        for name in (*names, *family_files[family]):
            put(
                task,
                where + "/scripts/control_transfer/trusted/" + name,
                (SRC / "trusted" / name).read_text(),
            )
        spec_files = {
            "anycar": ("anycar_spec.py",),
            "anycar-drift": ("anycar_spec.py", "anycar_drift_spec.py"),
            "anycar-drift-v3": ("anycar_spec.py", "anycar_drift_v3_spec.py"),
        }.get(family, ())
        for name in spec_files:
            if (SRC / name).exists():
                put(
                    task,
                    where + "/scripts/control_transfer/" + name,
                    (SRC / name).read_text(),
                )
    if family == "neural-fly" and (SRC / "neuralfly_nominal.py").exists():
        names = ("neuralfly_nominal.py", "neuralfly_video.py", "neuralfly_constants.py")
        if visual_profile == "skydio-x2/1":
            names += ("neuralfly_visual.py",)
        for name in names:
            source_name = (
                "neuralfly_video_primitive.py" if name == "neuralfly_video.py" and visual_profile is None else name
            )
            content = (SRC / source_name).read_text()
            if name == "neuralfly_visual.py":
                # Runtime packages have no asset downloader or upstream location.
                tree = ast.parse(content)
                tree.body = [
                    n
                    for n in tree.body
                    if not (isinstance(n, ast.FunctionDef) and n.name == "prepare") and not isinstance(n, ast.If)
                ]
                content = ast.unparse(tree) + "\n"
            put(task, where + "/scripts/control_transfer/" + name, content)
            put(task, where + "/" + name, content)
        if not private:
            put(
                task,
                where + "/nominal_fly.py",
                (SRC / "neuralfly_nominal.py").read_text(),
            )


def render(task, name, index):
    instance = spec(name, index)
    family = instance["family"]
    skydio = instance.get("visual_profile") == "skydio-x2/1"
    image = SKYDIO_IMAGE if skydio else IMAGE
    instance["evaluation_requirements"] = {
        "physics": "mujoco-cpu",
        "mujoco_version": "3.5.0",
        "policy_inference": "numpy-cpu",
        "render_backend": "osmesa",
        "gpu_devices": [],
        "device_isolation_verified": True,
    }
    if family == "anycar":
        instance["observation_revision"] = "anycar-dashed-cones/1"
        instance["public"]["observation_revision"] = "anycar-dashed-cones/1"
        instance["public"]["visual_feedback"] = (
            "Dashed public commanded centerline in both video panels with cosmetic orange-and-white cones and black bases; no moving target dot or privileged overlay."
        )
    lap = instance.get("task_variant") == "circuit-lap/2"
    compact = instance.get("task_variant") == "circuit-compact-lap/3"
    bounded_lap = lap or compact
    limits = runtime_limits(instance)
    base = TASK_NAMES.get(name, name)   # a family not shipped as a task (tests, development) keeps its spec name
    metadata_family = "roboengineer/" + base
    if lap:
        instance["public"].pop("image_interval_s", None)
        instance["public"].update(
            image_sampling="Up to 128 equally spread video frame indices, including first and last; full 10 Hz telemetry.",
            request_timeout_s=limits["request_seconds"],
        )
    if compact:
        instance["public"].update(
            image_sampling="31 images at fixed one-second times from 0 through 30 s; all 301 noisy 10 Hz rows.",
            request_timeout_s=limits["request_seconds"],
        )
    # The reference controller of solution/ run by Harbor's oracle agent on the shipped task (EVIDENCE below): the oracle
    # level follows what it reached on this instance (PROTOCOL §4: full = it scores 1).
    run = EVIDENCE.get((name, index))
    if run is None:   # a family not shipped as a task (tests, development): no recorded run
        oracle, reference_note = "none", "No recorded reference run (not a shipped task). Human review required."
    else:
        ok, cases, n, score = run
        oracle = "full" if ok else "partial" if cases else "none"
        reference_note = (f"{EVIDENCE_RUN}: the reference controller (solution/, three feedback rounds) succeeded on "
                          f"{cases}/{n} held-out cases, mean engineering score {score:.2f}; nop 0."
                          + ("" if ok else " No full oracle: human review (PROTOCOL §4)."
                             + (" No positive example yet." if not cases else "")))
    gpu = family in ("linearbot", "g1")
    seconds = cutoff_sec("Control Transfer", "standard")
    if lap:   # a full lap needs up to 32631 s of agent time: above the 14400 s cap (PROTOCOL §2); not shipped
        raise ValueError(f"{name}: full-lap tasks need more than the {seconds} s cutoff; use the compact laps")
    if family == "neural-fly":
        instance.update(
            private_asset="/opt/private-fly/forces.npz",
            private_asset_sha256=FLY_ASSET_SHA256,
        )
    for folder in ("environment/sim", "tests"):
        put(
            task,
            folder + "/instance.json",
            json.dumps(instance, sort_keys=True, indent=2) + "\n",
        )
    copy_package(task, "environment/public", False, family, instance.get("visual_profile"))
    copy_package(task, "environment/sim", True, family, instance.get("visual_profile"))
    put(
        task,
        "environment/public/task-spec.json",
        json.dumps(instance["public"], indent=2) + "\n",
    )
    put(
        task,
        "environment/Dockerfile",
        f"""FROM {image}-{"train" if gpu else "nominal"}
WORKDIR /app
COPY public/ /app/
ENV PYTHONPATH=/app OPENBLAS_NUM_THREADS=1 MUJOCO_GL=osmesa{f" CONTROL_DEPLOY_TIMEOUT_S={limits['request_seconds']}" if bounded_lap else ""}{" NEURALFLY_VISUAL_STYLE=skydio-x2/1" if skydio else ""}
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
    image: {image}
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
{chr(10).join(["      NEURALFLY_VISUAL_STYLE: skydio-x2/1", ""]) if skydio else ""}      RCB_WALL_CLOCK_S: "{seconds}"
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
family = "{metadata_family}"
mode = "standard"
dynamics = "{"dynamic" if family in DYNAMIC else "static"}"
protocol = "eai-policy/1.1"
oracle = "{oracle}"
oracle_evidence = "{reference_note}"
instance_seed = {index}
expert_time_estimate_hours = 4.0
[verifier]
timeout_sec = {limits["collect_seconds"] + 360 if bounded_lap else 2100}.0
environment_mode = "separate"
network_mode = "no-network"
[[verifier.collect]]
service = "main"
command = "kill -9 -1 2>/dev/null; exit 0"   # PROTOCOL H.4: nothing the agent started runs on when the sidecar finalizes
timeout_sec = 30
[[verifier.collect]]
service = "sim"
command = "python -m scripts.control_transfer.trusted.collect"
timeout_sec = {limits["collect_seconds"] + 60 if bounded_lap else 1800}
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
    if family == "anycar-drift":
        training += " Run `python -m control_public.anycar_drift_nominal --out /app/output/nominal` for local nominal rollouts. The public numeric ABI is in `control_public.anycar_drift`. Each response preserves the public course in `feedback.command`, all 161 noisy telemetry rows and all 161 video frames at 10 Hz through 16 seconds. Use the course to distinguish changes in the parking target from changes in vehicle response."
    if family == "anycar-drift-v3":
        training += " Run `python -m control_public.anycar_drift_v3_nominal --out /app/output/nominal` for local nominal rollouts. The controller entry point is `control_public.anycar_drift_v3`; ABI /3 coefficients are in `control_public.anycar_drift_feedback`, and legacy ABI /2 is also accepted. Each response preserves the public course in `feedback.command`, all 161 noisy telemetry rows and all 161 video frames at 10 Hz through 16 seconds. The course includes the public start position, target heading and fixed revision string."
    if instance.get("task_variant") == "circuit-sector/1":
        training += f" Use `--track {public['track_id']}` to train on this task's public route, and `--full-lap` for nominal full-lap practice. Deployment evaluates 24-second sectors; full-lap practice does not change that horizon."
    if lap:
        training += f" Use `--track {public['track_id']} --full-lap` for nominal training. Deployment covers a complete lap. Feedback retains every 10 Hz noisy row and up to 128 images spread over the whole recording, including the finish. Full operator videos retain 10 fps. Long episodes count against the declared time limit; preserve the complete response traces."
    if compact:
        training += f" Use `--track {public['track_id']} --compact-30s` for nominal training. The public route is a compact 45 m F1-inspired approximation, targeted at a 28 s lap with a hard 30 s episode. Every ordered gate and the finish must be crossed. Feedback includes all 301 noisy rows and 31 one-second images covering 0 through 30 s; operator videos retain all 301 frames. Smoothing and aspect widening can remove sharp turns and crossovers; the original F1 outline is not preserved."
    if family == "neural-fly":
        training += " The reference and controller are in `control_public.fly`; a public nominal simulator is provided in `nominal_fly.py`."
    if skydio:
        training += " This observation revision uses Skydio X2 appearance at 960 by 720 pixels, with unchanged surrogate dynamics and noisy-sensor/controller interfaces. Public mesh assets are preinstalled; no download is required."
    put(
        task,
        "instruction.md",
        f"""# {base}

{public["goal"]}

## Train, deploy, inspect and revise
{training}

Use `from control_public.client import Client, artifact`; `Client().describe()` provides the public defaults and bounds. Call `deploy(policy, diagnosis)` for up to three rounds. A deployment can take minutes: if your tool call times out and the response is lost, `result(round_id)` returns that completed round's stored response again (it runs nothing). An episode that crashes, leaves its course or arena, or makes the simulation diverge ends at that moment: its telemetry and frames stop there. Each round reuses the same {public["adaptation_cases"]} development cases. Diagnose failures from the returned video frames and noisy telemetry, then revise. Preserve code, training logs, policies and exact feedback under `/app/output/`. The client saves the exact response and image bytes. A diagnosis should briefly state the observed failure, proposed change and expected effect.

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
    put(
        task,
        "tests/test.sh",
        "#!/bin/bash\nmkdir -p /logs/verifier\npython /tests/grade.py\n",
        True,
    )
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
        put(
            task,
            "solution/neuralfly_reference.py",
            (SRC / "neuralfly_reference.py").read_text(),
        )
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
        put(
            task,
            "solution/solve.sh",
            "#!/bin/bash\nset -euo pipefail\ncd /app\npython /solution/reference.py\n",
            True,
        )
    if family in ("anycar-drift", "anycar-drift-v3"):
        default_module = "anycar_drift_feedback" if family == "anycar-drift-v3" else "anycar_drift"
        put(
            task,
            "solution/reference.py",
            (
                "from control_public.client import Client\n"
                f"from control_public.{default_module} import DEFAULT\n"
                "c = Client()\nc.describe()\n"
                "for i in range(3):\n"
                "    r = c.deploy(DEFAULT, 'Frozen nominal controller; repeated for lifecycle validation only, transfer success is not established.')\n"
                "c.seal(r['round_id'], 'Unadapted nominal baseline; robust randomized success is not established.')\n"
            ),
        )
        put(
            task,
            "solution/solve.sh",
            "#!/bin/bash\nset -euo pipefail\ncd /app\npython /solution/reference.py\n",
            True,
        )
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
        put(
            task,
            "solution/solve.sh",
            "#!/bin/bash\nset -euo pipefail\ncd /app\npython /solution/reference.py\n",
            True,
        )
    if family == "spacecraft":
        from nonlinearbench.contract import REFERENCE

        solve = (
            "from control_public.client import Client\nc=Client()\npolicy="
            + repr(REFERENCE)
            + "\nfor i in range(3):\n r=c.deploy(policy, 'Reference nonlinear controller; fixed repeated policy for integration validation.')\nc.seal(r['round_id'],'Reference integration run.')\n"
        )
        put(task, "solution/reference.py", solve)
        put(
            task,
            "solution/solve.sh",
            "#!/bin/bash\nset -euo pipefail\ncd /app\npython /solution/reference.py\n",
            True,
        )
    normalize(task)   # last (PROTOCOL §1): fields, README, instruction's closing sections, monitor, DIGEST


def main():
    """render | check: every task of TASK_NAMES (two instances each) into tasks/ (or --output-root); check compares the
    committed tasks with a fresh render and fails on a roboengineer Control Transfer directory it does not write."""
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["render", "check", "list-circuits"])
    p.add_argument("--output-root", type=Path, default=TASK_ROOT, help="Task directory root; default tasks/")
    a = p.parse_args()
    if a.action == "list-circuits":
        from scripts.control_transfer.components.anycarbench.tracks import track_ids

        print(json.dumps(track_ids(), indent=2))
        return
    os.umask(0o022)
    bad = []
    expected = set()
    for name in TASK_NAMES:
        for i in range(2):
            ident = task_dir_name(name, i)
            expected.add(ident)
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
    from scripts.control_transfer.packaging import PREFIX, LANDING_NAME
    stray = sorted(d.name for d in a.output_root.glob(PREFIX + "*") if d.is_dir() and d.name not in expected
                   and not d.name.startswith(PREFIX + LANDING_NAME + "-"))
    if stray:
        bad += [f"{n} (not written by this generator)" for n in stray]
    if bad:
        raise SystemExit("Generated tasks differ: " + ", ".join(bad))
    print(f"control transfer: {len(expected)} tasks " + a.action)


if __name__ == "__main__":
    main()
