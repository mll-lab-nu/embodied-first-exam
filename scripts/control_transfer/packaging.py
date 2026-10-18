"""roboEngineer task packaging: where the two generators write, the task directory names and the benchmark's cutoffs.

roboEngineer (docs/benchmarks/roboengineer.md) ships its tasks with its own multi-round runtime, `eai-policy/1.0`
(Neural Landing) and `eai-policy/1.1` (Control Transfer), declared in scripts/roboengineer/exported.toml (PROTOCOL §3:
a benchmark with its own runtime; Appendix H applies unchanged). Both generators (scripts/control_transfer/gen_tasks.py,
scripts/quadrotor_landing/gen_tasks.py) render into tasks/ and end with scripts/task_conventions.py `normalize`.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TASK_ROOT = ROOT / "tasks"
PREFIX = "roboengineer-"
sys.path.insert(0, str(ROOT / "scripts"))
import task_conventions as _tc  # noqa: E402

# The agent's cutoff per sub-collection (the task author's choice, PROTOCOL §2; at most 14400 s): written into
# `[agent] timeout_sec` and the sim service's RCB_WALL_CLOCK_S.
CUTOFF_SEC = {"Control Transfer": 14400, "Neural Lander": 3600}

# Control Transfer: the generator's family name (the frozen spec's own name, specs.py) -> the task directory's base after
# `roboengineer-` (no version tokens in task names, PROTOCOL §1). The frozen instances keep the spec names.
TASK_NAMES = {
    "neural-fly": "neuralfly-eight",
    "neural-fly-general-v1": "neuralfly-general",
    "neural-fly-general-skydio-v1": "neuralfly-general-skydio",
    "neural-fly-vector-wind-v1": "neuralfly-vector-wind",
    "anycar": "anycar-tracking",
    "anycar-drift": "anycar-drift-park",
    "anycar-drift-v3": "anycar-tight-drift-park",
    "anycar-circuit-compact-v3-monaco-6": "anycar-compact-lap-monaco-6",
    "anycar-circuit-compact-v3-silverstone-8": "anycar-compact-lap-silverstone-8",
    "go2-attitude": "go2-attitude",
    "go2-forward-jump": "go2-forward-jump",
    "go2-weave": "go2-weave",
    "go2-yaw-jump": "go2-yaw-jump",
}
LANDING_NAME = "landing-random-pad"


def cutoff_sec(bench, mode="standard"):
    return CUTOFF_SEC[bench]


def task_dir_name(name, index):
    """The task directory of a Control Transfer family name (or the landing family) and instance index."""
    base = LANDING_NAME if name == LANDING_NAME else TASK_NAMES[name]
    return f"{PREFIX}{base}-i{index:02d}-standard"


def spec_name_of(task_name):
    """(spec family name, instance index) of a Control Transfer task directory name; ValueError otherwise."""
    base, index = task_name.removeprefix(PREFIX).removesuffix("-standard").rsplit("-i", 1)
    names = {v: k for k, v in TASK_NAMES.items()}
    if not task_name.startswith(PREFIX) or base not in names:
        raise ValueError(f"not a Control Transfer task: {task_name}")
    return names[base], int(index)


def normalize(task):
    _tc.normalize(Path(task))
