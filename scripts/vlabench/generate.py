#!/usr/bin/env python3
"""Generate the VLABench tasks: tasks/vlabench-<task>-i00-privileged and tasks/vlabench-<task>-i00-standard.

    python3 scripts/vlabench/generate.py            # every task freeze.sh verified (frozen/report.json)
    python3 scripts/vlabench/generate.py select_fruit
    python3 scripts/vlabench/generate.py --check    # exit 1 if tasks/ differs from what this would write

Inputs: tasks.json (candidates, dropped, instruction restatements, oracle sources), frozen/<task>/{instance.json,
oracle.npy}, imported from PR #4 (commit ad3c5109), and frozen/report.json (freeze.sh), the
templates in templates/, the shared sources in shared/ (copied byte for byte) and the standard client's base image and
pins (scripts/eai_standard/client.env, client-requirements.txt). Each task directory is written from scratch and
finished with scripts/task_conventions.py (normalize, PROTOCOL v1.0.1); a vlabench-* directory this does not write is
removed. Re-running reproduces the tasks exactly.
"""

import filecmp
import json
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from task_conventions import normalize  # noqa: E402   (protocol v1.0.1 conventions)

# The agent's time cutoff per mode (PROTOCOL §2.12): this benchmark's own number, written into every task's `[agent]
# timeout_sec`, the one source; normalize renders from it the instruction's closing `## Time limit`, the README row and
# the sim service's wall clock. To change it (an owner decision; the pull request states old -> new), edit it here and
# regenerate.
CUTOFF_SEC = {"privileged": 1800, "standard": 1800}

TASKS_DIR = ROOT / "tasks"
SHARED = HERE / "shared"
TEMPLATES = HERE / "templates"
FROZEN = HERE / "frozen"
VERSION = (ROOT / "images/vlabench/VERSION").read_text().strip()
IMAGE = f"ghcr.io/mll-lab-nu/eai-vlabench:{VERSION}"
# Standard-mode client image (agent container and verifier): the one digest-pinned base and the exact pip pins of
# scripts/eai_standard/ (PROTOCOL §2.4; ci_checks/check-standard-client.sh).
_EAI = ROOT / "scripts/eai_standard"
_ENV = dict(ln.split("=", 1) for ln in (_EAI / "client.env").read_text().splitlines() if "=" in ln and ln[0] != "#")
CLIENT_IMAGE = _ENV["CLIENT_IMAGE"].strip()
CLIENT_PIP = " ".join(
    ln.split("#", 1)[0].strip()
    for ln in (_EAI / _ENV.get("CLIENT_REQUIREMENTS", "client-requirements.txt").strip()).read_text().splitlines()
    if ln.split("#", 1)[0].strip()
)
AUTHOR, ORG = "Changhe Chen", "MLL Lab"
HOSTS = [
    "chatgpt.com", "*.chatgpt.com", "auth.openai.com", "api.openai.com", "*.openai.com", "api.anthropic.com",
    "*.anthropic.com", "openrouter.ai", "*.openai.azure.com", "*.cognitiveservices.azure.com", "pypi.org", "files.pythonhosted.org", "deb.debian.org", "security.debian.org", "archive.ubuntu.com", "security.ubuntu.com", "snapshot.ubuntu.com",
]  # fmt: skip
MAX_CONTROL_STEPS = 9000  # standard: technical episode cap (the grading replay must fit the collect hook's timeout)
IMAGE_HW = 320
MS_STEP, MS_FRAME = 40, 15  # measured in eai-vlabench on the reference machine (docs/benchmarks/vlabench.md)
PANDA_LIMITS = (
    "[-2.90, 2.90], [-1.76, 1.76], [-2.90, 2.90], [-3.07, -0.07], [-2.90, 2.90], [-0.02, 3.75], [-2.90, 2.90]"
)
PATH_ENV = "/opt/VLABench:/opt/rrt-algorithms"
# VLABench's franka base (configs/robot_config.json); a task series may override it (configs/task_config.json), and the
# frozen episode configuration then carries it (episode.robot.position).
ROBOT_BASE = (0, -0.4, 0.78)

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
      RCB_WALL_CLOCK_S: "{float(CUTOFF_SEC["standard"])}"
      RCB_MAX_CONTROL_STEPS: "{MAX_CONTROL_STEPS}"
      RCB_IMAGE_HW: "{IMAGE_HW}"
      # One episode, no reset, as instruction.md tells the agent: pinned, not a knob (a `${{RCB_RESET_BUDGET:-0}}` here
      # would take the budget from the shell that runs harbor, and a host that exports it for another benchmark would
      # hand this task resets its instruction rules out).
      RCB_RESET_BUDGET: "0"
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
        return "a physics question, answered by pressing the button in front of the right object"
    return "a direct command"


def render(template: str, values: dict) -> str:
    text = (TEMPLATES / template).read_text()
    for k, v in values.items():
        text = text.replace("{{" + k + "}}", str(v))
    if "{{" in text:
        raise ValueError(f"{template}: unfilled placeholder near {text[text.index('{{') :][:40]!r}")
    return text


def reset_dir(d: Path) -> None:
    """A task directory is written from scratch: what is not rendered here does not belong (no results/, PROTOCOL D3)."""
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)


def put(path: Path, text: str | None = None, src: Path | None = None, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if src is not None:
        shutil.copyfile(src, path)
    else:
        path.write_text(text)
    path.chmod(mode)


def robot_base(instance: Path) -> str:
    """The robot's base position in the frozen episode, e.g. "(0, -0.4, 0.78)"."""
    spec = json.loads(instance.read_text())
    pos = spec["episode"].get("robot", {}).get("position", ROBOT_BASE)
    return "(" + ", ".join(f"{float(v):g}" for v in pos) + ")"


def make(task: str, rec: dict, source: str, restated: dict, out: Path) -> tuple[Path, Path]:
    """restated: tasks.json's `instructions` entry for the task ({} if none): `text` (what the task states instead of
    VLABench's instruction, which stays in the instance) and `why`; `kind` overrides instruction_kind()."""
    fz = FROZEN / task
    dash = task.replace("_", "-")
    instruction = restated.get("text", rec["instruction"])
    note = row = ""
    if "text" in restated:
        upstream = rec["instruction"]
        note = (
            "\n\nThis states exactly what VLABench's success check requires; VLABench's own wording (also in "
            f"`s.state()[\"instruction\"]`) is: \"{upstream}\"."
        )
        row = f"\n| Instruction | restated; VLABench's own: \"{upstream}\" ({restated['why']}) |"
    episode = (
        f'Ends when the task succeeds (reason "success"), after {MAX_CONTROL_STEPS} control steps ("failed"), when '
        'your time is up ("timeout"), or on a simulator error ("error").'
    )
    values = {
        "agent_timeout": float(CUTOFF_SEC["privileged"]),   # both modes (PROTOCOL §2.15)
        "task": task,
        "dash": dash,
        "instruction": instruction,
        "instruction_toml": json.dumps(instruction)[1:-1],
        "instruction_kind": restated.get("kind", instruction_kind(task)),
        "instruction_note": note,
        "instruction_row": row,
        "robot_base": robot_base(fz / "instance.json"),
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

    p = out / f"vlabench-{dash}-i00-privileged"
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

    s = out / f"vlabench-{dash}-i00-standard"
    reset_dir(s)
    put(s / "task.toml", render("standard/task.toml", values))
    put(s / "instruction.md", render("standard/instruction.md", values))
    put(s / "README.md", render("standard/README.md", values))
    put(s / "environment/Dockerfile", STD_ENV_DOCKERFILE)
    put(s / "environment/docker-compose.yaml", compose(instruction, episode))
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
    normalize(p)
    normalize(s)
    return p, s


def render_all(out: Path, only: list[str]) -> list[str]:
    """Write the task directories of `only` (default: every verified task not dropped in tasks.json) into `out`;
    returns their names."""
    report = json.loads((FROZEN / "report.json").read_text())
    sel = json.loads((HERE / "tasks.json").read_text())
    verified = [t for t in sel["candidates"] if report.get(t, {}).get("verified")]
    names = []
    for task in only or [t for t in verified if t not in sel["dropped"]]:
        if task not in verified:
            raise SystemExit(f"{task}: not verified by freeze.sh (frozen/report.json)")
        if task in sel["dropped"]:
            raise SystemExit(f"{task}: dropped in tasks.json ({sel['dropped'][task]})")
        restated = sel["instructions"].get(task, {})
        names += [d.name for d in make(task, report[task], sel["oracle_source"][task], restated, out)]
    return names


def check() -> int:
    """tasks/ must be exactly what render_all writes, with no other vlabench-* directory."""
    with tempfile.TemporaryDirectory() as tmp:
        names = set(render_all(Path(tmp), []))
        have = {d.name for d in TASKS_DIR.glob("vlabench-*") if d.is_dir()}
        bad = sorted(have ^ names)
        for name in sorted(names & have):
            cmp = filecmp.dircmp(TASKS_DIR / name, Path(tmp) / name, ignore=["__pycache__"])
            stack = [cmp]
            while stack:
                c = stack.pop()
                if c.left_only or c.right_only or c.diff_files or c.funny_files:
                    bad.append(name)
                    break
                diff = filecmp.cmpfiles(c.left, c.right, c.common_files, shallow=False)[1]
                if diff:
                    bad.append(name)
                    break
                stack += list(c.subdirs.values())
    for name in sorted(set(bad)):
        print(f"FAIL tasks/{name}: differs from scripts/vlabench/generate.py (re-run it)")
    return 1 if bad else 0


def main(args: list[str]) -> int:
    if args == ["--check"]:
        return check()
    names = render_all(TASKS_DIR, args)
    if not args:  # a full run owns every vlabench-* directory
        for d in sorted(TASKS_DIR.glob("vlabench-*")):
            if d.is_dir() and d.name not in names:
                shutil.rmtree(d)
                print(f"removed stale {d.relative_to(ROOT)}")
    print(f"generated {len(names)} task directories")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
