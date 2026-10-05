"""Choose this benchmark's instances from the PR #4 RoboCasa365 families (run inside the benchmark image, PR #4 checkout
mounted at /src): prints the candidate order the selection rule defines.

Rule (deterministic, documented in docs/benchmarks/robocasa365.md): the families PR #4 accepted (instance i00 each)
are split into RoboCasa365's atomic and composite tasks (the module the environment class is defined in); 50 slots
are shared between the two groups in proportion to their sizes (largest remainder); within a group, families are taken
in the order of the SHA-256 of their environment name, skipping any whose reference does not verify with this
benchmark's tooling (import_references.py), until the group's slots are filled.

    python select_instances.py candidates.json
"""

import hashlib
import inspect
import json
import re
import sys
from pathlib import Path

import robocasa  # noqa: F401
from robosuite.environments.base import REGISTERED_ENVS

SRC = Path("/src/unlimited_tasks/robocasa365")
SLOTS = 50

rows = []
for d in sorted(SRC.glob("robocasa365-*-i00")):
    env = re.search(r'^environment_id = "(.*)"', (d / "task.toml").read_text(), re.M).group(1)
    path = inspect.getfile(REGISTERED_ENVS[env])
    group = "atomic" if "/kitchen/atomic/" in path else "composite"
    rows.append(
        {
            "env": env,
            "source": d.name,
            "group": group,
            "module": path.split("/environments/kitchen/")[-1],
            "rank": hashlib.sha256(env.encode()).hexdigest(),
        }
    )
sizes = {g: sum(r["group"] == g for r in rows) for g in ("atomic", "composite")}
exact = {g: SLOTS * n / len(rows) for g, n in sizes.items()}
slots = {g: int(v) for g, v in exact.items()}
for g in sorted(exact, key=lambda g: exact[g] - slots[g], reverse=True)[: SLOTS - sum(slots.values())]:
    slots[g] += 1
order = {g: sorted((r for r in rows if r["group"] == g), key=lambda r: r["rank"]) for g in sizes}
out = {"families": len(rows), "sizes": sizes, "slots": slots, "order": order}
Path(sys.argv[1]).write_text(json.dumps(out, indent=1) + "\n")
