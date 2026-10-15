#!/usr/bin/env python3
"""Compute resources (docs/PROTOCOL.md §2.9, protocol v1.1.4): every task.toml has `[metadata.resources]` with the
required keys and sane values, consistent with the task's GPU reservations and `[environment]` caps, and the README's
`## Compute resources` section shows the same values (it is rendered by scripts/task_conventions.py).
Resource limits (§2.10, v1.1.5): `[metadata.resources.limits]` with every key, the scope of the task's mode, limits no
lower than the minimums and no higher than the docker caps that bound them, and instruction.md ending in the
`## Resource limits` paragraph rendered from them. The caps are checked as docker really applies them (v1.2): main's
memory and CPU from `[environment]` (Harbor writes them), every other value from environment/docker-compose.yaml, each
equal to its `[metadata.resources.caps]` entry.

Usage: check-resources.py [task dirs...]   (default: every task under tasks/)
"""

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from task_conventions import (  # noqa: E402  (one list of keys, one README / instruction renderer)
    CAP_KEYS, CUTOFF_HEADING, LIMIT_KEYS, LIMIT_SCOPES, RESOURCE_KEYS, mode_of, observed_of, render_external, render_limits, render_resources,
    sidecars_of)
from rcb_monitor import inject  # noqa: E402  (one reader of the compose file's services and caps)

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
    for k in sorted(set(r) - set(RESOURCE_KEYS) - {"limits", "caps"}):
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
    # standard modes: the sidecar replays in [[verifier.collect]]. The resource monitor's own hook (service rcb_monitor,
    # in every task since v1.2) only seals its record: it is not a verifier phase on a sidecar.
    collect = any(isinstance(h, dict) and h.get("service") != "rcb_monitor"
                  for h in d.get("verifier", {}).get("collect") or [])
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
    services = inject.service_names(env_c.read_text()) if env_c.is_file() else []
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

    lim_errs = check_limits(task, d, r, env_gpu, services)
    if lim_errs:   # the README renders the limits too: compare it only once they are well-formed
        return errs + lim_errs

    # README: the section scripts/task_conventions.py renders from these values
    readme = (task / "README.md").read_text() if (task / "README.md").is_file() else ""
    want = "\n".join(render_resources(r, observed_of(task)))
    if want not in readme:
        errs.append(
            "README.md `## Compute resources` does not match [metadata.resources] "
            f"(run python3 scripts/task_conventions.py {task.relative_to(ROOT) if task.is_relative_to(ROOT) else task})"
        )
    return errs


def check_limits(task: Path, d: dict, r: dict, env_gpu: bool, services: list[str]) -> list[str]:
    """[metadata.resources.limits] (PROTOCOL §2.10)."""
    lim = r.get("limits")
    if not isinstance(lim, dict):
        return ["[metadata.resources.limits] missing (PROTOCOL §2.10)"]
    errs = []
    for k, typ in LIMIT_KEYS.items():
        v = lim.get(k)
        if v is None:
            errs.append(f"[metadata.resources.limits].{k} missing")
        elif typ is int and not (isinstance(v, int) and not isinstance(v, bool)):
            errs.append(f"[metadata.resources.limits].{k} must be an integer")
        elif typ is float and not is_num(v):
            errs.append(f"[metadata.resources.limits].{k} must be a number")
        elif typ is str and not (isinstance(v, str) and v):
            errs.append(f"[metadata.resources.limits].{k} must be a non-empty string")
        elif typ is list and not (isinstance(v, list) and (v or k == "disk_exclude")
                                  and all(isinstance(x, str) and x.startswith("/") for x in v)):
            errs.append(f"[metadata.resources.limits].{k} must be a list of absolute paths"
                        + (" (not empty)" if k == "disk_paths" else ""))
    for k in sorted(set(lim) - set(LIMIT_KEYS)):
        errs.append(f"[metadata.resources.limits].{k}: unknown key")
    if errs:
        return errs
    mode = mode_of(task)
    if lim["scope"] != LIMIT_SCOPES[mode]:
        errs.append(f"[metadata.resources.limits].scope must be {LIMIT_SCOPES[mode]!r} in {mode} mode (PROTOCOL §2.10)")
    if lim["max_processes"] < 16 or lim["sustain_sec"] <= 0 or lim["max_disk_gb"] <= 0 or lim["max_memory_gb"] <= 0:
        errs.append("[metadata.resources.limits]: max_processes >= 16, max_memory_gb, max_disk_gb and sustain_sec > 0")
    if not lim["sustain_sec"] < lim["window_sec"] <= 4 * lim["sustain_sec"]:
        errs.append("[metadata.resources.limits]: sustain_sec < window_sec <= 4 x sustain_sec")
    if not lim["measured"].strip():
        errs.append("[metadata.resources.limits].measured: say what the limits rest on")
    errs += check_caps(task, r, lim, services)
    # the whole trial's expected peak covers the minimum, and the limits never exceed it
    for k in ("gpu_memory_gb", "memory_gb"):
        if lim[f"trial_max_{k}"] < r[f"min_{k}"]:
            errs.append(f"trial_max_{k} {lim[f'trial_max_{k}']} < min_{k} {r[f'min_{k}']}")
        if lim[f"max_{k}"] > lim[f"trial_max_{k}"]:
            errs.append(f"max_{k} {lim[f'max_{k}']} > trial_max_{k} {lim[f'trial_max_{k}']}")
    env = d.get("environment", {})
    if lim["scope"] == "trial":
        # privileged: the limits bind every container, so they are at least the trial's minimums
        for k in ("gpu_memory_gb", "memory_gb"):
            if lim[f"max_{k}"] < r[f"min_{k}"]:
                errs.append(f"max_{k} {lim[f'max_{k}']} < min_{k} {r[f'min_{k}']} (scope trial)")
        if (lim["max_gpu_memory_gb"] > 0) != r["gpu_required"]:
            errs.append("scope trial: max_gpu_memory_gb > 0 exactly when the task has a GPU (gpu_required)")
    else:
        # standard modes: the agent's container only, bounded by its own docker cap
        if env.get("memory_mb") and lim["max_memory_gb"] > env["memory_mb"] / 1024:
            errs.append(f"max_memory_gb {lim['max_memory_gb']} > [environment].memory_mb {env['memory_mb']} / 1024")
        main_gpu = main_has_gpu(task)
        if lim["max_gpu_memory_gb"] > 0 and not main_gpu:
            errs.append("scope agent: max_gpu_memory_gb > 0 but the agent's container (main) has no GPU")
        if (lim["trial_max_gpu_memory_gb"] > 0) != r["gpu_required"]:
            errs.append("trial_max_gpu_memory_gb > 0 exactly when the task has a GPU (gpu_required)")
    # scope trial: the limits bind the whole trial, so its expected peak is the limit -- unless the task has a service
    # of the benchmark's own (recorded only), whose share the whole trial's peak adds
    whole = lim["scope"] == "trial" and not observed_of(task)
    if whole and lim["trial_max_gpu_memory_gb"] != lim["max_gpu_memory_gb"]:
        errs.append("scope trial: trial_max_gpu_memory_gb equals max_gpu_memory_gb (the limits bind the whole trial)")
    if whole and lim["trial_max_memory_gb"] != lim["max_memory_gb"]:
        errs.append("scope trial: trial_max_memory_gb equals max_memory_gb (the limits bind the whole trial)")
    # instruction.md ends with the paragraph rendered from these values
    ins = (task / "instruction.md").read_text() if (task / "instruction.md").is_file() else ""
    # ... before the closing `## Time limit` section (PROTOCOL §2.12; ci_checks/check-cutoffs.py checks that one)
    ins = re.sub(rf"(?ms)\n^{re.escape(CUTOFF_HEADING)}[ \t]*\n.*\Z", "", ins)   # with the blank line before it
    want = render_limits(lim, mode, sidecars_of(task), env.get("cpus"))
    if not ins.endswith("\n" + want):
        errs.append(
            "instruction.md does not end (before `## Time limit`) with the `## Resource limits` paragraph rendered from [metadata.resources.limits] "
            f"(run python3 scripts/task_conventions.py {task.relative_to(ROOT) if task.is_relative_to(ROOT) else task})"
        )
    # ... and, just before it, the `## External material` paragraph every task states in the same words (PROTOCOL §2.11)
    elif not ins[: -len(want)].endswith("\n" + render_external(task) + "\n"):
        errs.append("instruction.md does not state `## External material` (PROTOCOL §2.11; scripts/task_conventions.py "
                    "EXTERNAL_TEXT) just before `## Resource limits`")
    return errs


def check_caps(task: Path, r: dict, lim: dict, services: list[str]) -> list[str]:
    """[metadata.resources.caps] (§2.10): one entry per compose service (cache helpers rcb_* aside, main always), each
    equal to the cap docker really applies (main's memory and CPU: `[environment]`, written by Harbor; everything else:
    environment/docker-compose.yaml), and the relation chain on those real caps: the limited memory <= (sum of the
    scope's memory caps) / 1.2 and <= that sum - 2 GiB, so that the monitor sees a violation before the OOM killer;
    pids >= 8 x max_processes for the services the limits bind; no cap below the task's own minimums (min_cpus <= the
    CPU caps together; verifier_min_memory_gb <= the memory caps of the sidecars a collect hook replays in)."""
    caps = r.get("caps")
    if not isinstance(caps, dict):
        return ["[metadata.resources.caps] missing (PROTOCOL §2.10)"]
    errs = []
    want = {"main"} | {s for s in services if s != "main" and not s.startswith("rcb_")}
    if set(caps) != want:
        errs.append(f"[metadata.resources.caps] services {sorted(caps)} != compose services {sorted(want)}")
    mode = mode_of(task)
    scope = [s for s in caps if inject.kind_of(mode, s) == "scope"]   # the services the limits bind
    for svc, c in caps.items():
        if not isinstance(c, dict) or set(c) != set(CAP_KEYS):
            errs.append(f"[metadata.resources.caps].{svc} needs exactly {sorted(CAP_KEYS)}")
            continue
        if not (is_num(c["cpus"]) and c["cpus"] > 0 and is_num(c["memory_gb"]) and c["memory_gb"] > 0
                and isinstance(c["pids"], int) and not isinstance(c["pids"], bool) and c["pids"] > 0):
            errs.append(f"[metadata.resources.caps].{svc}: cpus, memory_gb and pids (an integer) > 0")
            continue
        if svc in scope and c["pids"] < 8 * lim["max_processes"]:
            errs.append(f"caps.{svc}.pids {c['pids']} < 8 x max_processes {lim['max_processes']}")
    if errs:
        return errs
    # the caps docker really applies, service by service: they are the declared ones
    env = tomllib.loads((task / "task.toml").read_text()).get("environment", {})
    comp = task / "environment/docker-compose.yaml"
    try:
        real = inject.service_caps(comp.read_text()) if comp.is_file() else {}
    except ValueError as e:
        return [f"environment/docker-compose.yaml: {e}"]
    main = real.get("main", {})
    if is_num(env.get("memory_mb")):
        if main.get("memory_gb") is not None and abs(main["memory_gb"] - env["memory_mb"] / 1024) > 1e-6:
            errs.append("service main: mem_limit in docker-compose.yaml differs from [environment].memory_mb (Harbor sets it)")
        real.setdefault("main", {})["memory_gb"] = env["memory_mb"] / 1024
    if is_num(env.get("cpus")):
        if main.get("cpus") is not None and main["cpus"] != float(env["cpus"]):
            errs.append("service main: cpus in docker-compose.yaml differs from [environment].cpus (Harbor sets it)")
        real.setdefault("main", {})["cpus"] = float(env["cpus"])
    src = {"cpus": "cpus", "memory_gb": "mem_limit", "pids": "pids_limit"}
    for svc, c in caps.items():
        for k in CAP_KEYS:
            got = (real.get(svc) or {}).get(k)
            where = (f"[environment].{'memory_mb / 1024' if k == 'memory_gb' else 'cpus'}" if svc == "main" and k != "pids"
                     else f"docker-compose.yaml `{src[k]}` of service {svc}")
            if got is None:
                errs.append(f"caps.{svc}.{k} = {c[k]} is declared, but {where} is not set: no such cap is applied")
            elif abs(float(got) - float(c[k])) > 1e-6:
                errs.append(f"caps.{svc}.{k} = {c[k]} but {where} is {got:g}: declare the cap that is applied "
                            "(scripts/task_resources.toml), or apply the declared one")
    if errs:
        return errs
    # a cap is never below what the task itself says it needs (§2.10): the trial's CPU minimum fits under the CPU caps
    # of all its services together (so that a runner that clamps a cap to the host's CPU count, on a host that has
    # min_cpus, never leaves the trial with less than its minimum), and a sidecar that holds the simulator in the
    # verifier phase (it replays in a [[verifier.collect]] hook) is not capped below the verifier phase's minimum
    d = tomllib.loads((task / "task.toml").read_text())
    cpus = sum(real[s]["cpus"] for s in caps)
    if r["min_cpus"] > cpus + 1e-9:
        errs.append(f"min_cpus {r['min_cpus']} > the CPU caps of all services together {cpus:g}: the declared minimum could never be used")
    hooked = sorted({h.get("service") for h in d.get("verifier", {}).get("collect") or [] if isinstance(h, dict)}
                    & (set(caps) - {"main"}))
    if hooked:
        side = sum(real[s]["memory_gb"] for s in hooked)
        if r["verifier_min_memory_gb"] > side + 1e-9:
            errs.append(f"verifier_min_memory_gb {r['verifier_min_memory_gb']} > the memory cap of the sidecar(s) the verifier phase "
                        f"runs in ({', '.join(hooked)}: {side:g} GiB): the kernel would kill the service at a cap below its own "
                        "declared minimum (scripts/task_resources.toml: raise the [[cap]])")
    total = sum(real[s]["memory_gb"] for s in scope)
    if lim["max_memory_gb"] > total / 1.2 + 1e-9 or lim["max_memory_gb"] > total - 2 + 1e-9:
        errs.append(f"max_memory_gb {lim['max_memory_gb']} must be <= the scope's memory caps {total:g} / 1.2 and <= {total:g} - 2")
    if sum(real[s]["memory_gb"] for s in caps) < lim["trial_max_memory_gb"]:
        errs.append("the memory caps of all services together are below trial_max_memory_gb")
    return errs


def main_has_gpu(task: Path) -> bool:
    c = task / "environment/docker-compose.yaml"
    if not c.is_file():
        return False
    lines = c.read_text().splitlines(keepends=True)
    try:
        i, j = inject.services_span(lines)
    except ValueError:
        return False
    return any(name == "main" and NVIDIA.search("".join(lines[k0:k1])) for name, k0, k1 in inject.service_blocks(lines, i, j))


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
        print(f"resources: {n} task(s) declare their minimum compute (PROTOCOL §2.9) and their limits (§2.10)")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
