#!/usr/bin/env python3
"""Render/check self-contained Harbor policy tasks; stdlib only."""

import ast
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SRC = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
from scripts.control_transfer.packaging import LANDING_NAME, TASK_ROOT, normalize, cutoff_sec, task_dir_name

PUBLIC = ("model.py", "policy.py", "nominal.py", "client.py")
BASE = next(
    line.split("=", 1)[1]
    for line in (ROOT / "scripts/eai_standard/client.env").read_text().splitlines()
    if line.startswith("CLIENT_IMAGE=")
)
HOSTS = next(
    ast.literal_eval(n.value)
    for n in ast.parse((ROOT / "scripts/set_agent_egress.py").read_text()).body
    if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "HOSTS" for t in n.targets)
)


def put(task, path, text, executable=False):
    p = task / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    p.chmod(0o755 if executable else 0o644)


def package(task, where, private=False):
    for path in (
        "scripts/__init__.py",
        "scripts/quadrotor_landing/__init__.py",
        "scripts/quadrotor_landing/public/__init__.py",
    ):
        put(task, f"{where}/{path}", "")
    for name in PUBLIC:
        put(task, f"{where}/scripts/quadrotor_landing/public/{name}", (SRC / "public" / name).read_text())
    if private:
        for part in ("trusted", "native"):
            for file in sorted((SRC / part).glob("*.py")):
                put(task, f"{where}/scripts/quadrotor_landing/{part}/{file.name}", file.read_text())


# The frozen case seeds (3 adaptation, then 6 held-out) per instance: independent random 62-bit numbers (#329 review:
# the earlier small sequential seeds let an agent recover the adaptation seeds from the pad positions it is shown,
# through the public task sampler, and guess the held-out ones). They are in the private instance only.
CASE_SEEDS = {0: [2340373329952157779, 4461507513662650648, 1677516078028978978, 1368547839372076676, 2721909774847666069, 3215200149820338993, 3250595428567560715, 1596460257806331067, 3594346411366189521], 1: [1363051104769783013, 1194637519526507563, 2189518629130379092, 4326007715772235137, 3085282784588827519, 3862659006590689685, 70888593357599779, 2301472379728769886, 50004572136537272]}


EVIDENCE = {   # the reference learner of solution/ run by Harbor's oracle agent on the shipped tasks (#329 review, board 0146)
    0: "Harbor 0.23.0 oracle agent on aws:rcb-cpu3, 2026-10-18, image eai-quadrotor-landing:0.1.0: six safe held-out landings of six, mean score 84.11; nop 0.",
    1: "Harbor 0.23.0 oracle agent on aws:rcb-cpu3, 2026-10-18, image eai-quadrotor-landing:0.1.0: six safe held-out landings of six, mean score 82.89; nop 0.",
}


def render(task, index):
    instance = {
        "schema": "landing-instance/1",
        "task_version": "random-pad-landing/4",
        "score_version": "oracle-relative-time/1",
        "instance": index,
        "residual_sha256": "bebb6c7f9bc7364b296006c77542a9698162665dac6fb74e769e5583fc7a00ef",
        "bank": {
            "adaptation": [{"seed": seed, "scale": 1.0} for seed in CASE_SEEDS[index][:3]],
            "held_out": [{"seed": seed, "scale": 1.0} for seed in CASE_SEEDS[index][3:]],
        },
    }
    for folder in ("environment/sim", "tests"):
        put(task, f"{folder}/instance.json", json.dumps(instance, sort_keys=True, indent=2) + "\n")
    package(task, "environment/public")
    package(task, "environment/sim", private=True)
    put(task, "environment/nominal-requirements.txt", (SRC / "requirements.txt").read_text())
    put(
        task,
        "environment/Dockerfile",
        f"""FROM {BASE}
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends libgl1 libosmesa6 && rm -rf /var/lib/apt/lists/*
COPY nominal-requirements.txt /tmp/nominal-requirements.txt
RUN pip install --no-cache-dir -r /tmp/nominal-requirements.txt
WORKDIR /app
COPY public/scripts /app/scripts
ENV PYTHONPATH=/app PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 MUJOCO_GL=osmesa LANDING_SERVICE_URL=http://127.0.0.1:8000
RUN mkdir -p /app/output
""",
    )
    put(
        task,
        "environment/docker-compose.yaml",
        f'''services:
  main:
    # Start the idle client immediately so the monitor can discover its beacon.
    # Harbor Docker uses compose up --wait: this gates the agent on calibration.
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]
      interval: 5s
      timeout: 3s
      start_period: 1800s
      retries: 3
  sim:
    image: ghcr.io/mll-lab-nu/eai-quadrotor-landing:{(ROOT / "images/quadrotor-landing/VERSION").read_text().strip()}
    volumes:
      - ./sim:/srv:ro
    working_dir: /srv
    command: python -m scripts.quadrotor_landing.native.service
    restart: on-failure:3
    environment:
      PYTHONPATH: /srv
      RCB_INSTANCE: /srv/instance.json
      RCB_WALL_CLOCK_S: "{cutoff_sec("Neural Lander", "standard")}"
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]
      interval: 5s
      timeout: 3s
      start_period: 1800s
      retries: 3
''',
    )
    put(
        task,
        "task.toml",
        f"""schema_version = "1.3"
artifacts = [{{ source = "/data/", service = "sim" }}, "/app/output/"]

[task]
name = "robot-coding-bench/{task.name}"
description = "Learn a safe, fast random-pad landing policy from noisy deployment feedback over bounded adaptation rounds."
authors = [{{ name = "Robotic Engineering Bench contributors" }}]
keywords = ["robotics", "mujoco", "quadrotor", "policy", "system-identification", "standard-mode"]

[metadata]
author_name = "Robotic Engineering Bench contributors"
author_org = "Robotic Engineering Bench"
collection = "roboEngineer"
embodiment = "drone"
task_type = "policy"
simulator = "mujoco"
robot = "intel-aero-partial"
family = "roboengineer/landing-random-pad"
mode = "standard"
dynamics = "static"
protocol = "eai-policy/1.0"
oracle = "full"
oracle_evidence = "{EVIDENCE[index]}"
instance_seed = {index}
expert_time_estimate_hours = 2.0

[verifier]
timeout_sec = 1200.0
environment_mode = "separate"
network_mode = "no-network"

[[verifier.collect]]
service = "main"
command = "kill -9 -1 2>/dev/null; exit 0"   # PROTOCOL H.4: nothing the agent started runs on when the sidecar finalizes
timeout_sec = 30

[[verifier.collect]]
service = "sim"
command = "python -m scripts.quadrotor_landing.native.collect"
timeout_sec = 900

[agent]
timeout_sec = {cutoff_sec("Neural Lander", "standard")}.0
network_mode = "allowlist"
allowed_hosts = {json.dumps(HOSTS)}

[environment]
build_timeout_sec = 2400.0
cpus = 2
memory_mb = 5120

[verifier.environment]
build_timeout_sec = 600.0
""",
    )
    instructions = (SRC / "public/INSTRUCTIONS.md").read_text().replace("This prototype fixes", "This task fixes")
    instructions += """
This task uses `eai-policy/1.0`. Work in `/app`, preserve your code, policies, exact feedback and short iteration diagnoses in `/app/output/`. Nominal training is unrestricted within the resource and time limits. Only validated numeric policies reach deployment; editing your local controller implementation does not change the evaluator's controller. The deployment endpoint is `http://127.0.0.1:8000`; `GET /spec` describes its protocol. A deployment request consumes one round before execution. No reset, held-out query, score query or arbitrary code execution is provided.

Seal a completed round to select it. If you finish or time out without sealing, the evaluator selects the latest round completed before the cutoff. In-flight or late rounds cannot be selected. With no eligible round the score is zero. Harbor stops the agent at its time limit; the service also closes after the same duration from the first policy API request. Calibration and health checks do not consume deployment rounds. Binary benchmark success requires all six held-out cases to land safely; the continuous 0–100 score is reported separately as `final_reward` (`progress` is that score divided by 100).
"""
    put(task, "instruction.md", instructions)
    put(
        task,
        "README.md",
        f"""# {task.name}

**roboEngineer → Drone → Neural Landing.** See the [collection roadmap](../../docs/benchmarks/roboengineer.md).

Randomized aerial landing with bounded sensor-only policy adaptation and a private held-out bank. Reference runs: the Oracle row; build instructions: docs/benchmarks/roboengineer.md.

## Difficulty
Identify unmodeled aerodynamic forces using noisy sensors and camera samples, while trading landing time against contact safety.

## Reference solution
The scripted learner in `solution/` fits force corrections from permitted IMU/RPM feedback over three rounds. It is not installed in the agent image. It lands all six held-out cases on both instances (the Oracle row).

## Verification
The private MuJoCo service evaluates the sealed policy in six held-out cases, each replayed twice in fresh processes. The no-network verifier reads only collected simulator evidence and emits binary success plus a continuous score. Reference times come from finite full-model optimization, without a claim of global optimality. Ground-truth states, model residuals, seeds, reference searches and grades are never feedback to the agent.
""",
    )
    put(task, "tests/grade.py", (SRC / "native/verify.py").read_text())
    put(
        task,
        "tests/test.sh",
        "#!/bin/bash\nrm -rf /logs/verifier/*\nmkdir -p /logs/verifier\npython /tests/grade.py\n",
        True,
    )
    put(
        task,
        "tests/Dockerfile",
        f"""FROM {BASE}
COPY test.sh grade.py instance.json /tests/
RUN chmod +x /tests/test.sh
""",
    )
    # the reference learner lives outside public/ (reference/: never part of the agent's copy, #329 review)
    train = (
        (SRC / "reference/train.py")
        .read_text()
        .replace("from ..public.model", "from scripts.quadrotor_landing.public.model")
        .replace("from ..public.policy", "from scripts.quadrotor_landing.public.policy")
    )
    iterate = (
        (SRC / "reference/iterate.py")
        .read_text()
        .replace("from ..public.client", "from scripts.quadrotor_landing.public.client")
        .replace("from ..public.policy", "from scripts.quadrotor_landing.public.policy")
        .replace("from .train", "from train")
    )
    put(task, "solution/train.py", train)
    put(task, "solution/iterate.py", iterate)
    put(
        task,
        "solution/solve.sh",
        "#!/bin/bash\nset -euo pipefail\ncd /app\npython /solution/iterate.py --url http://127.0.0.1:8000 --out /app/output/reference\n",
        True,
    )
    normalize(task)


def snapshot(path):
    return {
        str(p.relative_to(path)): (p.read_bytes(), p.stat().st_mode & 0o777)
        for p in path.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }


def main():
    os.umask(0o022)
    if len(sys.argv) != 2 or sys.argv[1] not in ("render", "check"):
        raise SystemExit("usage: gen_tasks.py render|check")
    bad = False
    for index in range(2):
        name = task_dir_name(LANDING_NAME, index)
        target = TASK_ROOT / name
        with tempfile.TemporaryDirectory() as temporary:
            task = Path(temporary) / name
            render(task, index)
            if sys.argv[1] == "render":
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(task, target)
            elif snapshot(task) != snapshot(target):
                print(f"FAIL {name}: generated task differs")
                bad = True
    if bad:
        raise SystemExit(1)
    print("quadrotor landing: 2 policy tasks " + sys.argv[1])


if __name__ == "__main__":
    main()
