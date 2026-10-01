#!/usr/bin/env python3
"""Generate the VLABench tasks: tasks/vlabench-<task>-i00 (privileged) and tasks/vlabench-<task>-i00-standard.

    python3 scripts/vlabench/generate.py            # every task freeze.sh verified (frozen/report.json)
    python3 scripts/vlabench/generate.py select_fruit

Inputs: tasks.json, frozen/<task>/{instance.json,oracle.npy} and frozen/report.json (import_pr4.py, freeze.sh), the
templates in templates/ and the shared sources in shared/ (copied byte for byte). Everything in a task directory except
results/ is rewritten; re-running reproduces the tasks exactly.
"""

import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SHARED = HERE / "shared"
TEMPLATES = HERE / "templates"
FROZEN = HERE / "frozen"
VERSION = (ROOT / "images/vlabench/VERSION").read_text().strip()
IMAGE = f"ghcr.io/embodied-agent-interface-v2-internal/eai-vlabench:{VERSION}"
# Standard-mode client image (agent container and verifier), as main's HumanoidBench standard tasks pin it.
CLIENT_IMAGE = (
    "docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f"
)
CLIENT_PIP = "requests==2.34.2 numpy==2.5.3 pillow==12.3.0 scipy==1.18.1"
AUTHOR, ORG = "Changhe Chen", "MLL Lab"
HOSTS = [
    "chatgpt.com", "*.chatgpt.com", "auth.openai.com", "api.openai.com", "*.openai.com", "api.anthropic.com",
    "*.anthropic.com", "openrouter.ai", "*.openai.azure.com", "*.cognitiveservices.azure.com",
]  # fmt: skip
MAX_CONTROL_STEPS = 9000  # standard: technical episode cap (the grading replay must fit the collect hook's timeout)
IMAGE_HW = 320
MS_STEP, MS_FRAME = 40, 15  # measured in eai-vlabench on the reference machine (docs/benchmarks/vlabench.md)
PANDA_LIMITS = (
    "[-2.90, 2.90], [-1.76, 1.76], [-2.90, 2.90], [-3.07, -0.07], [-2.90, 2.90], [-0.02, 3.75], [-2.90, 2.90]"
)
PATH_ENV = "/opt/VLABench:/opt/rrt-algorithms"

PRIV_ENV_DOCKERFILE = f"""# VLABench privileged task: the VLABench image, the task's tooling and its frozen instance.
FROM {IMAGE}
COPY instance.json /app/instance.json
COPY vlb_tool.py /opt/tools/vlb_tool.py
ENV PYTHONPATH=/opt/tools:{PATH_ENV}
RUN mkdir -p /app/output
WORKDIR /app
"""
PRIV_TESTS_DOCKERFILE = f"""# Separate verifier sandbox: the same image with the verifier's own copies of the tooling and the frozen instance;
# only the declared artifacts (/app/output/) arrive from the agent.
FROM {IMAGE}
COPY test.sh grade.py vlb_tool.py instance.json /tests/
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests:{PATH_ENV}
WORKDIR /tests
"""
STD_ENV_DOCKERFILE = f"""# Standard mode: the agent container has no simulator and no VLABench code -- only Python and the client.
FROM {CLIENT_IMAGE}
RUN pip install --no-cache-dir {CLIENT_PIP}
COPY rcb_client.py rcb1.py /opt/tools/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
"""
STD_TESTS_DOCKERFILE = f"""# Separate verifier sandbox: grades the sim service's own artifacts; needs nothing but Python.
FROM {CLIENT_IMAGE}
COPY test.sh grade.py /tests/
RUN chmod +x /tests/test.sh
"""


def compose(task_text: str, episode: str) -> str:
    return f"""# Standard mode: the simulator runs in the `sim` sidecar (the agent cannot open it); the agent only reaches port 8000.
# No `expose`/`ports` on sim: under Harbor's egress control it shares main's network namespace (localhost:8000).
# CPU only: MuJoCo physics and OSMesa rendering (~15 ms per 320x320 image); no GPU reservation.
services:
  main:
    depends_on: [sim]
  sim:
    image: {IMAGE}
    volumes:
      - ./sim:/srv:ro
    command: python /srv/server.py
    restart: on-failure:6                               # a crash resumes the same episode, never a reset (rcb_service.py)
    environment:
      RCB_INSTANCE: /srv/instance.json
      RCB_TASK_TEXT: {json.dumps(task_text)}
      RCB_EPISODE: {json.dumps(episode)}
      RCB_WALL_CLOCK_S: "3600.0"
      RCB_MAX_CONTROL_STEPS: "{MAX_CONTROL_STEPS}"
      RCB_IMAGE_HW: "{IMAGE_HW}"
      # The default is the standard configuration (one episode, no reset); results with resets are reported separately.
      RCB_RESET_BUDGET: "${{RCB_RESET_BUDGET:-0}}"
      PYTHONPATH: /srv:{PATH_ENV}
"""


def instruction_kind(task: str) -> str:
    if task.endswith("_common_sense"):
        return "a common-sense riddle that names the target only indirectly"
    if task.endswith("_semantic"):
        return "a request in conversation that names the target only by its meaning"
    if task.endswith("_spatial"):
        return "a description of where the target is"
    if task.endswith("_qa"):
        return "a physics question, answered by moving the right object"
    return "a direct command"


def render(template: str, values: dict) -> str:
    text = (TEMPLATES / template).read_text()
    for k, v in values.items():
        text = text.replace("{{" + k + "}}", str(v))
    if "{{" in text:
        raise ValueError(f"{template}: unfilled placeholder near {text[text.index('{{') :][:40]!r}")
    return text


def reset_dir(d: Path) -> None:
    """Remove everything except results/ (committed agent results)."""
    if d.exists():
        for c in d.iterdir():
            if c.name != "results":
                shutil.rmtree(c) if c.is_dir() else c.unlink()
    d.mkdir(parents=True, exist_ok=True)


def put(path: Path, text: str | None = None, src: Path | None = None, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if src is not None:
        shutil.copyfile(src, path)
    else:
        path.write_text(text)
    path.chmod(mode)


def make(task: str, rec: dict, source: str) -> None:
    fz = FROZEN / task
    dash = task.replace("_", "-")
    episode = (
        f'Ends when the task succeeds (reason "success"), after {MAX_CONTROL_STEPS} control steps ("failed"), when '
        'your time is up ("timeout"), or on a simulator error ("error").'
    )
    values = {
        "task": task,
        "dash": dash,
        "instruction": rec["instruction"],
        "instruction_toml": json.dumps(rec["instruction"])[1:-1],
        "instruction_kind": instruction_kind(task),
        "seed": rec["seed"],
        "image": IMAGE,
        "author": AUTHOR,
        "org": ORG,
        "allowed_hosts": ", ".join(json.dumps(h) for h in HOSTS),
        "n_actions": rec["n_actions"],
        "oracle_source": source,
        "live_sha": rec["live_state_sha"][:12],
        "panda_limits": PANDA_LIMITS,
        "max_steps": MAX_CONTROL_STEPS,
        "robot_seconds": round(MAX_CONTROL_STEPS * rec["control_dt"]),
        "image_hw": IMAGE_HW,
        "ms_step": MS_STEP,
        "ms_frame": MS_FRAME,
    }

    p = ROOT / "tasks" / f"vlabench-{dash}-i00"
    reset_dir(p)
    put(p / "task.toml", render("task.toml", values))
    put(p / "instruction.md", render("instruction.md", values))
    put(p / "README.md", render("README.md", values))
    put(p / "environment/Dockerfile", PRIV_ENV_DOCKERFILE)
    put(p / "environment/vlb_tool.py", src=SHARED / "vlb_tool.py")
    put(p / "environment/instance.json", src=fz / "instance.json")
    put(p / "tests/Dockerfile", PRIV_TESTS_DOCKERFILE)
    put(p / "tests/test.sh", src=SHARED / "test.sh", mode=0o755)
    put(p / "tests/grade.py", src=SHARED / "grade.py")
    put(p / "tests/vlb_tool.py", src=SHARED / "vlb_tool.py")
    put(p / "tests/instance.json", src=fz / "instance.json")
    put(p / "solution/solve.sh", src=SHARED / "solve_privileged.sh", mode=0o755)
    put(p / "solution/oracle_replay.py", src=SHARED / "oracle_privileged.py")
    put(p / "solution/oracle.npy", src=fz / "oracle.npy")

    s = ROOT / "tasks" / f"vlabench-{dash}-i00-standard"
    reset_dir(s)
    put(s / "task.toml", render("standard/task.toml", values))
    put(s / "instruction.md", render("standard/instruction.md", values))
    put(s / "README.md", render("standard/README.md", values))
    put(s / "environment/Dockerfile", STD_ENV_DOCKERFILE)
    put(s / "environment/docker-compose.yaml", compose(rec["instruction"], episode))
    put(s / "environment/rcb_client.py", src=SHARED / "standard/rcb_client.py")
    put(s / "environment/rcb1.py", src=SHARED / "standard/rcb1.py")
    for f in ("server.py", "rcb_service.py", "rcb1.py"):
        put(s / "environment/sim" / f, src=SHARED / "standard" / f)
    put(s / "environment/sim/vlb_tool.py", src=SHARED / "vlb_tool.py")
    put(s / "environment/sim/instance.json", src=fz / "instance.json")
    put(s / "tests/Dockerfile", STD_TESTS_DOCKERFILE)
    put(s / "tests/test.sh", src=SHARED / "test.sh", mode=0o755)
    put(s / "tests/grade.py", src=SHARED / "standard/grade.py")
    put(s / "solution/solve.sh", src=SHARED / "standard/solve.sh", mode=0o755)
    put(s / "solution/oracle_replay.py", src=SHARED / "standard/oracle_replay.py")
    put(s / "solution/oracle.npy", src=fz / "oracle.npy")


def main(tasks: list[str]) -> None:
    report = json.loads((FROZEN / "report.json").read_text())
    sel = json.loads((HERE / "tasks.json").read_text())
    verified = [t for t in sel["candidates"] if report.get(t, {}).get("verified")]
    for task in tasks or verified:
        if task not in verified:
            raise SystemExit(f"{task}: not verified by freeze.sh (frozen/report.json)")
        make(task, report[task], sel["oracle_source"][task])
    print(f"generated {2 * len(tasks or verified)} task directories")


if __name__ == "__main__":
    main(sys.argv[1:])
