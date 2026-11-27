#!/usr/bin/env python3
"""Resources (docs/protocol/README.md §6): every number is an upper bound (a cap) for one container, written where Harbor
and docker read it, and nothing else.

- task.toml has no `[metadata.resources]` (no minimums, no soft limits, no copy of the caps);
- main's caps in `[environment]`: `cpus` (a whole number), `memory_mb`, `storage_mb` (disk), and `gpu_types` (RTX-class
  models, task_conventions.RTX_GPU_MODELS) only on a task with a GPU; never `gpus` (Harbor 0.23's local docker refuses
  it: the GPU is a compose device reservation, never `gpus:` or `runtime: nvidia`);
- every other compose service (the monitor's own aside, check-monitor.py) sets `cpus`, `mem_limit` and `pids_limit`, main
  sets `pids_limit` (its CPU and memory are Harbor's, from `[environment]`), none sets `deploy.resources.limits`; the
  `deploy` key is written in block style (one key per line: what inject.py reads, cross-checked with a YAML parser when
  PyYAML is installed); a service that reserves a GPU sets `x-gpu-memory-gb`, and only such a service
  (tests/docker-compose.yaml too: written by normalize from main's cap, by hand when main holds no GPU); at most one service in the monitor's scope
  (main, and in privileged mode the services the agent drives) holds a GPU, since the monitor checks one GPU-memory cap
  for the scope;
- the caps of the task's rule in scripts/task_resources.toml are the ones applied (task_conventions.py writes them);
- instruction.md ends with its rendered `## Limits`, whose Network line (§5) and Resources line (main's caps) are the
  ones rendered for the task, and the README's `## Resources` is the one rendered from every container's caps.

Usage: check-resources.py [task dirs...]   (default: every task under tasks/)
"""

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from task_conventions import (  # noqa: E402  (one renderer of the paragraph and the README section, one rule reader)
    RESOURCES_HEADING, RTX_GPU_MODELS, iter_tasks, mode_of, readme_resources, rule_for, task_caps)
import task_conventions as tconv  # noqa: E402  (instructions v2: render_limits)
from rcb_monitor import inject  # noqa: E402  (one reader of the compose file's services and caps)

FLOW_DEPLOY_RE = re.compile(r"^\s+(deploy|resources|reservations|devices|limits|capabilities):\s*[\[{]")
FLOW_DEPLOY_OK_RE = re.compile(r"^\s+-?\s*capabilities:\s*\[[^\]{}]*\]\s*(#.*)?$")   # `capabilities: [gpu]` is fine


def yaml_view(txt: str) -> dict | None:
    """{service: (holds a GPU, sets deploy.resources.limits)} by a YAML parser, or None (no PyYAML, or no services)."""
    try:
        import yaml
    except ImportError:
        return None
    try:
        d = yaml.safe_load(txt) or {}
    except yaml.YAMLError:
        return None
    out = {}
    for name, svc in ((d.get("services") or {}) if isinstance(d, dict) else {}).items():
        svc = svc if isinstance(svc, dict) else {}
        res = ((svc.get("deploy") or {}).get("resources") or {})
        devs = (res.get("reservations") or {}).get("devices") or []
        gpu = any(isinstance(x, dict) and (x.get("driver") in ("nvidia", "cdi") or "gpu" in (x.get("capabilities") or []))
                  for x in devs) or "gpus" in svc or svc.get("runtime") == "nvidia"
        out[name] = (gpu, "limits" in res)
    return out


BOUNDS = {"cpus": 128, "memory_gb": 1024, "pids": 1 << 22, "gpu_memory_gb": 192, "disk_gb": 4096}


def is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def rel(task: Path) -> str:
    return str(task.relative_to(ROOT) if task.is_relative_to(ROOT) else task)


def check(task: Path) -> list[str]:
    errs = []
    d = tomllib.loads((task / "task.toml").read_text())
    if "resources" in (d.get("metadata") or {}):
        errs.append("task.toml has [metadata.resources]: resources are caps per container only, in [environment] and the "
                    "compose files (PROTOCOL §6; run scripts/task_conventions.py)")
    env = d.get("environment") or {}
    if "gpus" in env:
        errs.append("[environment].gpus: Harbor's local docker refuses gpus > 0; reserve the GPU in "
                    "environment/docker-compose.yaml (an nvidia device) and cap its memory with x-gpu-memory-gb")
    for k in ("cpus", "memory_mb", "storage_mb"):
        v = env.get(k)
        if not (isinstance(v, int) and not isinstance(v, bool) and v > 0):
            errs.append(f"[environment].{k} must be a positive whole number (main's cap; Harbor reads it)")
    comp = task / "environment/docker-compose.yaml"
    try:
        caps = task_caps(task)
    except ValueError as e:
        return errs + [f"environment/docker-compose.yaml: {e}"]
    try:
        own = inject.service_caps(comp.read_text()) if comp.is_file() else {}
    except ValueError as e:
        return errs + [f"environment/docker-compose.yaml: {e}"]
    gpu = any(c.get("gpu") for c in caps.values())
    gt = env.get("gpu_types")
    if gt is not None and not (isinstance(gt, list) and gt and all(isinstance(x, str) and x.strip() for x in gt)):
        errs.append("[environment].gpu_types must be a non-empty list of GPU model names")
    elif gt and not gpu:
        errs.append("[environment].gpu_types is set but no service reserves a GPU")
    elif gt and set(gt) - set(RTX_GPU_MODELS):
        errs.append(f"[environment].gpu_types {sorted(set(gt) - set(RTX_GPU_MODELS))}: not RTX-class models "
                    f"(gpu_types is for a task that needs ray-tracing cores: {', '.join(RTX_GPU_MODELS)}); a task that "
                    "runs on any NVIDIA GPU sets none")
    for f in ("environment/docker-compose.yaml", "tests/docker-compose.yaml"):
        txt = (task / f).read_text() if (task / f).is_file() else ""
        for ln in txt.splitlines():
            if FLOW_DEPLOY_RE.match(ln) and not FLOW_DEPLOY_OK_RE.match(ln):
                errs.append(f"{f}: `{ln.strip()}`: write `deploy` in block style, one key per line (what "
                            "images/monitor/rcb_monitor/inject.py reads)")
                break
        yv = yaml_view(txt) if txt else None
        if yv is not None:
            try:
                lv = inject.service_caps(txt)
            except ValueError:
                lv = {}
            for n, (g, lim) in yv.items():
                if lim:
                    errs.append(f"{f}: service {n}: deploy.resources.limits; write the caps as `cpus`, `mem_limit` and "
                                "`pids_limit` (docker refuses both forms together)")
                if n in lv and lv[n]["gpu"] != g:
                    errs.append(f"{f}: service {n}: a YAML parser {'finds' if g else 'finds no'} GPU reservation, "
                                f"inject.py {'finds' if lv[n]['gpu'] else 'none'}: write the reservation in block style "
                                "(deploy.resources.reservations.devices, `driver: nvidia`, `capabilities: [gpu]`)")
        for m in re.finditer(r"(?m)^  ([A-Za-z0-9_.-]+):[^\n]*\n((?:    [^\n]*\n|\s*\n)*)", txt):
            if any(inject.GPU_OTHER_RE.match(ln) for ln in m.group(2).splitlines()):
                errs.append(f"{f}: service {m.group(1)} gets its GPU through `gpus:` or `runtime: nvidia`; reserve it as "
                            "a deploy device (deploy.resources.reservations.devices, driver: nvidia)")
    held = [n for n, c in caps.items() if c.get("gpu") and inject.kind_of(mode_of(task), n) == "scope"]
    if len(held) > 1:
        errs.append(f"services {held} all hold a GPU in the monitor's scope: it checks one GPU-memory cap per scope; "
                    "give the agent's side one GPU service")
    for svc, c in caps.items():
        if svc == "main":
            m = own.get("main") or {}
            if m.get("cpus") is not None or m.get("memory_gb") is not None:
                errs.append("service main: cpus / mem_limit in docker-compose.yaml (Harbor sets them from [environment])")
            need = ("pids",)
        else:
            need = ("cpus", "memory_gb", "pids")
        names = {"cpus": "cpus", "memory_gb": "mem_limit", "pids": "pids_limit"}
        for k in need:
            if c.get(k) is None:
                errs.append(f"service {svc}: no `{names[k]}` (every container has its caps, PROTOCOL §6)")
        if c.get("gpu") and not c.get("gpu_memory_gb"):
            errs.append(f"service {svc} reserves a GPU but sets no `{inject.GPU_KEY}` (its GPU-memory cap, GiB)")
        if not c.get("gpu") and c.get("gpu_memory_gb") is not None:
            errs.append(f"service {svc} sets `{inject.GPU_KEY}` but reserves no GPU")
        for k, hi in BOUNDS.items():
            v = c.get(k)
            if v is not None and not (is_num(v) and 0 < v <= hi):
                errs.append(f"service {svc}: {k} = {v} outside (0, {hi}]")
    tc = task / "tests/docker-compose.yaml"
    if tc.is_file():
        try:
            for svc, c in inject.service_caps(tc.read_text()).items():
                if c.get("gpu") and not c.get("gpu_memory_gb"):
                    errs.append(f"tests/docker-compose.yaml: service {svc} reserves a GPU but sets no `{inject.GPU_KEY}`: "
                                "normalize copies main's GPU-memory cap there only when main holds a GPU; otherwise write "
                                f"`{inject.GPU_KEY}: <GiB>` on that service yourself (normalize keeps it; PROTOCOL §6)")
        except ValueError as e:
            errs.append(f"tests/docker-compose.yaml: {e}")
    if errs:
        return errs
    # the rule's caps are the applied ones
    try:
        r = rule_for(task)
    except RuntimeError as e:
        return [str(e)]
    if r is not None:
        want = r["services"]
        if set(want) != set(caps):
            errs.append(f"scripts/task_resources.toml gives services {sorted(want)}, the compose file has {sorted(caps)}")
        for svc, c in want.items():
            for k, v in c.items():
                got = (caps.get(svc) or {}).get(k)
                if got is None or abs(float(got) - float(v)) > 1e-6:
                    where = ("[environment]" if svc == "main" and k in ("cpus", "memory_gb", "disk_gb")
                             else f"docker-compose.yaml service {svc}")
                    errs.append(f"{svc}.{k} = {v:g} in scripts/task_resources.toml but {where} applies "
                                f"{'nothing' if got is None else f'{got:g}'}: declare the cap that is applied, or apply "
                                f"the declared one (python3 scripts/task_conventions.py {rel(task)})")
        if (r.get("gpu_types") or None) != (gt or None):
            errs.append(f"[environment].gpu_types {gt} differs from scripts/task_resources.toml {r.get('gpu_types')}")
    if errs:
        return errs
    # instruction.md: the rendered `## Limits` last
    ins = (task / "instruction.md").read_text() if (task / "instruction.md").is_file() else ""
    if m := tconv.RETIRED_RULES_RE.search(" ".join(ins.split())):   # owner 11-24: wording that is gone from every task
        errs.append(f"instruction.md still has retired rule wording ({m.group(0)[:60]!r}; scripts/task_conventions.py "
                    "RETIRED_RULES_RE): drop it, the No cheating rule and the rules heading are rendered words")
    lim = tconv.render_limits(task, ins)      # the Network and Resources lines of `## Limits`, rendered
    for lab, text in (("Network", tconv.limits_network(task, dict(tconv.limits_lines(ins)).get("Network"))),
                      ("Resources", tconv.limits_resources(task))):
        if " ".join(f"{lab}: {text}".split()) not in " ".join(ins.split()):
            errs.append(f"instruction.md's `{tconv.LIMITS_HEADING}` does not state the {lab} line rendered for the task "
                        f"(run python3 scripts/task_conventions.py {rel(task)})")
    if not ins.endswith("\n" + lim):
        errs.append(f"instruction.md does not end with its rendered `{tconv.LIMITS_HEADING}` (run python3 "
                    f"scripts/task_conventions.py {rel(task)})")
    readme = (task / "README.md").read_text() if (task / "README.md").is_file() else ""
    if "\n".join(readme_resources(task, readme)) not in readme:
        errs.append(f"README.md `{RESOURCES_HEADING}` does not match the caps (run python3 scripts/task_conventions.py "
                    f"{rel(task)})")
    return errs


def main(argv: list[str]) -> int:
    tasks = [Path(a).resolve() for a in argv] or iter_tasks()
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
        print(f"resources: {n} task(s) state the caps of every container (PROTOCOL §6)")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
