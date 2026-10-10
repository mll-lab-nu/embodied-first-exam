#!/usr/bin/env python3
"""Compute resources (docs/PROTOCOL.md §2.9, protocol v1.1.4): every task.toml has `[metadata.resources]` with the
required keys and sane values, consistent with the task's GPU reservations and `[environment]` caps, and the README's
`## Compute resources` section shows the same values (it is rendered by scripts/task_conventions.py).

Usage: check-resources.py [task dirs...]   (default: every task under tasks/)
"""

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from task_conventions import RESOURCE_KEYS, render_resources  # noqa: E402  (one list of keys, one README renderer)

GPU_CLASSES = {"none", "any", "rtx"}
LIMITS = {
    "min_cpus": 128,
    "min_memory_gb": 1024,
    "min_gpu_memory_gb": 192,
    "verifier_min_cpus": 128,
    "verifier_min_memory_gb": 1024,
    "verifier_min_gpu_memory_gb": 192,
}
NVIDIA = re.compile(r"^\s*-?\s*driver:\s*nvidia\s*$", re.M)


def is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def check(task: Path) -> list[str]:
    errs = []
    d = tomllib.loads((task / "task.toml").read_text())
    r = d.get("metadata", {}).get("resources")
    if not isinstance(r, dict):
        return ["[metadata.resources] missing (PROTOCOL §2.9)"]
    for k, typ in RESOURCE_KEYS.items():
        if k not in r:
            if not (k == "recommended_gpu" and r.get("gpu_required") is False):
                errs.append(f"[metadata.resources].{k} missing")
            continue
        v = r[k]
        if typ is float and not is_num(v):
            errs.append(f"[metadata.resources].{k} must be a number")
        elif typ is bool and not isinstance(v, bool):
            errs.append(f"[metadata.resources].{k} must be true or false")
        elif typ is str and k == "recommended_gpu":
            if not (isinstance(v, str) and v.strip()) and not (
                isinstance(v, list) and v and all(isinstance(x, str) and x.strip() for x in v)
            ):
                errs.append("[metadata.resources].recommended_gpu must be a non-empty string or list of strings")
        elif typ is str and not (isinstance(v, str) and v.strip()):
            errs.append(f"[metadata.resources].{k} must be a non-empty string")
    for k in sorted(set(r) - set(RESOURCE_KEYS)):
        errs.append(f"[metadata.resources].{k}: unknown key")
    if errs:
        return errs
    for k, hi in LIMITS.items():
        lo_ok = r[k] >= 0 if "gpu" in k else r[k] > 0
        if not lo_ok or r[k] > hi:
            errs.append(f"[metadata.resources].{k} = {r[k]} outside {'[0' if 'gpu' in k else '(0'}, {hi}]")
    if r["gpu_class"] not in GPU_CLASSES:
        errs.append(f"[metadata.resources].gpu_class must be one of {sorted(GPU_CLASSES)}")
    if r["gpu_required"]:
        if r["min_gpu_memory_gb"] <= 0:
            errs.append("gpu_required = true but min_gpu_memory_gb is 0")
        if r["gpu_class"] == "none":
            errs.append('gpu_required = true but gpu_class = "none"')
    else:
        if r["min_gpu_memory_gb"] != 0 or r["gpu_class"] != "none":
            errs.append('gpu_required = false needs min_gpu_memory_gb = 0 and gpu_class = "none"')

    # the GPU the values claim is the GPU the compose files reserve (PROTOCOL §2.4)
    env_c = task / "environment/docker-compose.yaml"
    tst_c = task / "tests/docker-compose.yaml"
    env_gpu = env_c.is_file() and bool(NVIDIA.search(env_c.read_text()))
    tst_gpu = tst_c.is_file() and bool(NVIDIA.search(tst_c.read_text()))
    collect = bool(d.get("verifier", {}).get("collect"))  # standard modes: the sidecar replays in [[verifier.collect]]
    if env_gpu != r["gpu_required"]:
        errs.append(
            f"gpu_required = {str(r['gpu_required']).lower()} but environment/docker-compose.yaml "
            f"{'reserves' if env_gpu else 'does not reserve'} an NVIDIA GPU"
        )
    if tst_gpu and r["verifier_min_gpu_memory_gb"] <= 0:
        errs.append("tests/docker-compose.yaml reserves a GPU but verifier_min_gpu_memory_gb is 0")
    if r["verifier_min_gpu_memory_gb"] > 0 and not (tst_gpu or (collect and env_gpu)):
        errs.append(
            "verifier_min_gpu_memory_gb > 0 but no GPU reaches the verifier phase "
            "(tests/docker-compose.yaml, or a [[verifier.collect]] hook on a GPU service)"
        )

    # a minimum never exceeds a cap that bounds the whole phase
    env = d.get("environment", {})
    services = re.findall(r"^  ([A-Za-z0-9_.-]+):\s*$", env_c.read_text(), re.M) if env_c.is_file() else []
    sidecar = any(s not in ("main",) and not s.startswith("rcb_") for s in services)  # rcb_*: cache helpers
    if not sidecar:
        if env.get("cpus") and r["min_cpus"] > env["cpus"]:
            errs.append(f"min_cpus {r['min_cpus']} > [environment].cpus {env['cpus']}")
        if env.get("memory_mb") and r["min_memory_gb"] > env["memory_mb"] / 1024:
            errs.append(f"min_memory_gb {r['min_memory_gb']} > [environment].memory_mb {env['memory_mb']} / 1024")
    venv = d.get("verifier", {}).get("environment") or {}
    if not collect:
        if venv.get("cpus") and r["verifier_min_cpus"] > venv["cpus"]:
            errs.append(f"verifier_min_cpus {r['verifier_min_cpus']} > [verifier.environment].cpus {venv['cpus']}")
        if venv.get("memory_mb") and r["verifier_min_memory_gb"] > venv["memory_mb"] / 1024:
            errs.append(
                f"verifier_min_memory_gb {r['verifier_min_memory_gb']} > [verifier.environment].memory_mb "
                f"{venv['memory_mb']} / 1024"
            )

    # README: the section scripts/task_conventions.py renders from these values
    readme = (task / "README.md").read_text() if (task / "README.md").is_file() else ""
    want = "\n".join(render_resources(r))
    if want not in readme:
        errs.append(
            "README.md `## Compute resources` does not match [metadata.resources] "
            f"(run python3 scripts/task_conventions.py {task.relative_to(ROOT) if task.is_relative_to(ROOT) else task})"
        )
    return errs


def main(argv: list[str]) -> int:
    tasks = [Path(a).resolve() for a in argv] or sorted(
        p for p in (ROOT / "tasks").iterdir() if (p / "task.toml").is_file()
    )
    rc = 0
    n = 0
    for t in tasks:
        if not (t / "task.toml").is_file():
            continue
        n += 1
        for e in check(t):
            print(f"FAIL {t.name}: {e}")
            rc = 1
    if rc == 0:
        print(f"resources: {n} task(s) declare their minimum compute (PROTOCOL §2.9)")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
