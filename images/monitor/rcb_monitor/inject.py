#!/usr/bin/env python3
"""Wires the resource monitor into a task directory (docs/protocol/README.md §6) and writes the caps docker applies to
every compose service but main's CPU and memory (Harbor writes those from task.toml `[environment]`). Called by
scripts/task_conventions.py `normalize` with the caps of the task's rule in scripts/task_resources.toml (or, for a task no
rule matches, the caps its compose file already has), so `task_conventions.py --check` keeps it in step; idempotent.

Every number is an upper bound for one container (`x-gpu-memory-gb` is the one field of our own, on the compose service
that holds the GPU). Who enforces which cap where: docs/protocol/README.md §6 (Docker / Harbor as far as the host lets
them; with RCB_LIMITS_ENFORCE=1 the monitor as the backstop for all of them, monitor.py).

What it writes (every generated line ends in `# rcb-monitor`, or sits between the `# >>> rcb_monitor` and
`# <<< rcb_monitor` markers, so a re-run first removes what an earlier run wrote):
- environment/rcb_monitor/limits.json (format rcb-limits/2: the caps of every service as applied, the GPU-memory and disk
  caps of the services the monitor's scope covers, and the agent's time limit, `[agent] timeout_sec`, for the clock in
  usage.json). The monitor's code (monitor.py, rcb_limits.py, selftest.py, CODE) is not copied into tasks: it is in
  the pinned monitor image (IMAGE) at /opt/rcb_monitor/, built from this directory (images/monitor/; CONTENTS below holds
  the sha256 of every file the image carries, so a change here without a new image fails ci_checks/check-monitor.py).
- environment/docker-compose.yaml (created when the task had none):
  - the `rcb_monitor` service (pid: host, cgroup: host, network_mode: none, CAP_SYS_PTRACE, the task's GPU reservation,
    its code from the image, its limits.json mounted read-only, RCB_LIMITS_ENFORCE (default 0) and RCB_LIMITS_TOLERANCE
    (default rcb_limits.TOLERANCE) from the run-time environment);
  - the beacon volumes: `rcb_limits` read-only at /run/rcb-limits in every service in the monitor's scope (kind_of:
    main, and in privileged mode every service the agent drives), `rcb_observe` at /run/rcb-observe in the ones only
    recorded (the benchmark's own services: the simulator sidecar of standard modes, RoboPaint's privileged `scorer`);
  - the caps: pids_limit on main (Harbor writes main's cpus and memory from [environment], which
    scripts/task_conventions.py writes from the same rule); cpus, mem_limit and pids_limit on every other service, and
    `x-gpu-memory-gb` on every service that holds a GPU, unless the service sets one itself
    (ci_checks/check-resources.py then requires the rule's value to be that one).
- tests/docker-compose.yaml (a separate verifier with a GPU): `x-gpu-memory-gb` on its GPU services, main's value, a cap
  recorded for the reader (the monitor does not run in the verifier phase). The verifier's CPU and memory are Harbor's:
  `[verifier.environment]` alone when the table exists (a key it lacks is no cap), main's `[environment]` otherwise.
- task.toml: the record as an artifact of service rcb_monitor, the first `[[verifier.collect]]` hook (seals the record
  before any other sidecar ends the episode), `[verifier.env] RCB_LIMITS_ENFORCE`.
- tests/: rcb_limits.json (the verifier's own copy of limits.json); tests/Dockerfile COPYs it, and rcb_limits.py from the
  pinned monitor image (`COPY --from=IMAGE`), into /tests/; a
  `trap` in tests/test.sh that runs the verifier step after the grader, whatever the grader does, and before the grader
  the line that removes links and special files from the agent's /app/output (rcb_limits.py sanitize).
"""
from __future__ import annotations

import json
import re
import shutil
import tomllib
from pathlib import Path

SRC = Path(__file__).resolve().parent
try:
    from rcb_monitor import rcb_limits   # imported as a package (scripts/task_conventions.py, the checks)
except ImportError:                      # run as a script from this directory
    import rcb_limits  # type: ignore[no-redef]
CODE = ("monitor.py", "rcb_limits.py", "selftest.py")   # in the monitor image at /opt/rcb_monitor/ (images/monitor/Dockerfile)
IMAGE = "ghcr.io/mll-lab-nu/efe:monitor-0.5.0@sha256:ecc5f24f1516ca11711d7c2d3ac07c89f79cd9220812c1244498ec71e352402a"
# The sha256 of each CODE file in IMAGE (`inject.py verify-image` reads them back from the image; `inject.py contents`
# prints them for this directory's files). A change to a CODE file needs a new image: build images/monitor/, bump its
# VERSION, push it, then put the new digest in IMAGE and the new hashes here.
CONTENTS = {
    "monitor.py": "b08e767164013f052d0eaa4063d2e526906cf8a6bc01b60ebd41170f21ed79b1",
    "rcb_limits.py": "4eadc759714606651cc07493dc5e160930865d8a00d578431a396353ea04bc4b",
    "selftest.py": "c9052986c2ad5d0dcbf8e87bd6a53e570bd36b26eb8bb2e07d199046210114b7",
}
CODE_DIR = "/opt/rcb_monitor"
LIMITS_MOUNT = f"./rcb_monitor/limits.json:{CODE_DIR}/limits.json:ro"   # the task's limits, next to the image's code
MARK = "# rcb-monitor"
BEGIN, END = "  # >>> rcb_monitor", "  # <<< rcb_monitor"
GEN_HEADER = "# Generated by images/monitor/rcb_monitor/inject.py (the task has no services of its own besides main). rcb-monitor"
RECORD = "/var/rcb-monitor/"
TICK, DISK_TICK = 5, 60
ARTIFACT = f'{{ source = "{RECORD}", service = "rcb_monitor" }}'
HOOK = ('# Resources (PROTOCOL §6): seal the monitor\'s record first.\n'
        '[[verifier.collect]]\n'
        'service = "rcb_monitor"\n'
        'command = "python3 /opt/rcb_monitor/monitor.py seal --wait 90"\n'
        'timeout_sec = 120\n')
TRAP = ("trap 'p=$(command -v python3 || command -v python); \"$p\" /tests/rcb_limits.py verify' EXIT   "
        "# resources, after the grader (PROTOCOL §6)")
# Before the grader: what the agent left under /app/output is untrusted input (rcb_limits.sanitize).
GUARD = ("p=$(command -v python3 || command -v python); \"$p\" /tests/rcb_limits.py sanitize /app/output || true   "
         "# untrusted agent files (PROTOCOL H.1)")
DOCKER_COPY = ("# resources (PROTOCOL §6) " + MARK + "\n"
               f"COPY --from={IMAGE} {CODE_DIR}/rcb_limits.py /tests/rcb_limits.py\n"
               "COPY rcb_limits.json /tests/rcb_limits.json")


def _docker_copy_line(ln: str) -> bool:
    """A COPY line DOCKER_COPY writes (a Dockerfile instruction cannot carry the MARK comment), of this or an older
    layout (`COPY rcb_limits.py rcb_limits.json /tests/`, or another monitor image), so a re-run replaces it."""
    t = ln.strip()
    return t in ("COPY rcb_limits.py rcb_limits.json /tests/", "COPY rcb_limits.json /tests/rcb_limits.json") or \
        (t.startswith("COPY --from=") and t.endswith(f" {CODE_DIR}/rcb_limits.py /tests/rcb_limits.py"))   # any monitor image name
SIDECAR_MODES = ("standard", "realtime")
# Privileged mode: compose services that are the benchmark's own, not the agent's to drive (it cannot start, stop or
# size them): recorded, never part of the scope the limits bind. Today RoboPaint's scoring service.
BENCHMARK_SERVICES = ("scorer",)
MONITOR_CAPS = {"cpus": 0.5, "mem": "256m", "pids": 64}
GPU_KEY = "x-gpu-memory-gb"   # the GPU-memory cap of the service that holds the GPU (GiB): docker ignores x- keys
FORMAT = "rcb-limits/2"
CAP_FIELDS = ("cpus", "memory_gb", "pids", "gpu_memory_gb", "disk_gb")   # a service's caps in limits.json (disk: main only)


def _num(v) -> str:
    v = float(v)
    return str(int(v)) if v == int(v) else f"{v:g}"


def mode_of(task: Path) -> str:
    for m in ("realtime", "privileged", "standard"):
        if task.name.endswith("-" + m):
            return m
    raise ValueError(task.name)


def kind_of(mode: str, name: str) -> str:
    """"scope": the limits bind the service; "observe": it is recorded only (PROTOCOL §6). The agent's container
    always counts. In standard modes every other service is the benchmark's (the simulator sidecar); in privileged mode
    the agent drives the simulators itself, so every service counts except the benchmark's own (BENCHMARK_SERVICES)."""
    if name == "main":
        return "scope"
    if mode in SIDECAR_MODES or name in BENCHMARK_SERVICES:
        return "observe"
    return "scope"


def write_if_changed(p: Path, s: str | bytes) -> None:
    b = s.encode() if isinstance(s, str) else s
    if not p.is_file() or p.read_bytes() != b:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b)


# --------------------------------------------------------------------------------------------------- limits.json
def applied_caps(cfg: dict, compose: str | None) -> dict[str, dict]:
    """{service: {cpus, memory_gb, pids, gpu_memory_gb, disk_gb, gpu}} as docker and Harbor apply them: main's CPU,
    memory and disk from task.toml `[environment]` (cpus, memory_mb, storage_mb), everything else from the compose file
    (cpus, mem_limit, pids_limit, x-gpu-memory-gb; `gpu`: the service reserves an NVIDIA device). A cap that is not set
    is None. The monitor service itself is left out."""
    out = {k: v for k, v in (service_caps(compose) if compose else {}).items() if k != "rcb_monitor"}
    main = out.setdefault("main", {f: None for f in CAP_FIELDS[:4]} | {"gpu": False})
    env = cfg.get("environment") or {}
    main["cpus"] = float(env["cpus"]) if isinstance(env.get("cpus"), (int, float)) else main.get("cpus")
    main["memory_gb"] = (float(env["memory_mb"]) / 1024 if isinstance(env.get("memory_mb"), (int, float))
                         else main.get("memory_gb"))
    main["disk_gb"] = float(env["storage_mb"]) / 1024 if isinstance(env.get("storage_mb"), (int, float)) else None
    return out


def limits_json(task: Path, cfg: dict, caps: dict[str, dict]) -> dict:
    """limits.json (rcb-limits/2): what the monitor and the verifier step check, from the applied caps."""
    mode = mode_of(task)
    out = {"format": FORMAT, "task": task.name, "mode": mode,
           "caps": {n: {k: c[k] for k in CAP_FIELDS if c.get(k) is not None} for n, c in caps.items()}}
    # the services whose use the monitor sums (main, and in privileged mode every service the agent drives)
    out["scope_services"] = [n for n in caps if kind_of(mode, n) == "scope"]
    if len(out["scope_services"]) > 2:
        # the monitor tells the agent's container (main) from the others by /logs/agent alone: one other service at most
        raise ValueError(f"{task.name}: more than one service besides main in the monitor's scope "
                         f"({', '.join(out['scope_services'][1:])}): the monitor could not tell whose caps bind which")
    # the scope's GPU memory and the agent's disk (growth under rcb_limits.DISK_PATHS in main)
    # (a scope holds at most one GPU service, ci_checks/check-resources.py; no GPU in the scope: no GPU-memory cap, the
    # key is absent, and GPU memory seen anyway is recorded, never a violation)
    gpu = sum(float(caps[n].get("gpu_memory_gb") or 0) for n in out["scope_services"] if caps[n].get("gpu"))
    if gpu > 0:
        out["gpu_memory_gb"] = round(float(gpu), 3)
    if caps["main"].get("disk_gb"):
        out["disk_gb"] = caps["main"]["disk_gb"]
    # gpu: NVML must work (a fatal record otherwise) when a GPU-memory cap is enforceable
    out.update(tick_sec=TICK, disk_tick_sec=DISK_TICK, gpu=gpu > 0)
    # the agent's time limit (PROTOCOL §2, the task's own `[agent] timeout_sec`): the monitor shows the agent its
    # clock in /run/rcb-limits/usage.json (elapsed_s, time_left_s, deadline_utc)
    timeout = (cfg.get("agent") or {}).get("timeout_sec")
    if isinstance(timeout, (int, float)) and timeout > 0:
        out["agent_timeout_sec"] = int(timeout)
    return out


# --------------------------------------------------------------------------------------------------- compose
SERVICE_RE = re.compile(r"^  ([A-Za-z0-9_.-]+):\s*(#.*)?$")


def strip_generated(lines: list[str]) -> list[str]:
    out, skip = [], False
    for ln in lines:
        if ln.startswith(BEGIN):
            skip = True
            continue
        if skip:
            if ln.rstrip() == END:
                skip = False
            continue
        if ln.rstrip().endswith(MARK) or f"{MARK} GPU memory cap" in ln:   # the latter: 0.4.0's first x-gpu lines
            continue
        out.append(ln)
    return out


def services_span(lines: list[str]) -> tuple[int, int]:
    """(index of `services:`, index after its last line)."""
    i = next((k for k, ln in enumerate(lines) if re.match(r"^services:\s*(#.*)?$", ln)), None)
    if i is None:
        raise ValueError("no top-level services:")
    j = next((k for k in range(i + 1, len(lines)) if re.match(r"^[A-Za-z_]", lines[k])), len(lines))
    return i, j


def service_blocks(lines: list[str], i: int, j: int) -> list[tuple[str, int, int]]:
    heads = [(k, SERVICE_RE.match(lines[k]).group(1)) for k in range(i + 1, j) if SERVICE_RE.match(lines[k])]
    out = []
    for n, (k, name) in enumerate(heads):
        end = heads[n + 1][0] if n + 1 < len(heads) else j
        out.append((name, k, end))
    return out


def has_key(lines: list[str], k0: int, k1: int, key: str) -> int | None:
    for k in range(k0 + 1, k1):
        if re.match(rf"^    {key}:", lines[k]):
            return k
    return None


def service_names(text: str) -> list[str]:
    """The compose services of a file, in order (a service line may end in a comment; other top-level tables' entries,
    e.g. named volumes, are not services)."""
    lines = text.splitlines(keepends=True)
    try:
        i, j = services_span(lines)
    except ValueError:
        return []
    return [name for name, _, _ in service_blocks(lines, i, j)]


def _mem_gb(v: str) -> float:
    """A compose byte value (`8192m`, `8g`, `1073741824`) in GiB."""
    m = re.fullmatch(r"([0-9.]+)\s*([bkmg]?)b?", v.strip().strip("'\"").lower())
    if not m:
        raise ValueError(f"mem_limit {v!r}")
    return float(m.group(1)) * {"": 1.0, "b": 1.0, "k": 2.0 ** 10, "m": 2.0 ** 20, "g": 2.0 ** 30}[m.group(2)] / 2.0 ** 30


GPU_DEVICE_RE = re.compile(r"^\s*-?\s*driver:\s*[\"']?(nvidia|cdi)\b")
# a device reservation whose capabilities name `gpu` (docker gives it a GPU with or without a `driver:` line), flow
# (`capabilities: [gpu]`) or block (`capabilities:` then `- gpu`) style
GPU_CAP_RE = re.compile(r"^\s*-?\s*capabilities:\s*\[[^\]#]*?[\"']?\bgpu\b")
CAP_BLOCK_RE = re.compile(r"^(\s*)-?\s*capabilities:\s*(#.*)?$")
# other ways compose gives a container a GPU (ci_checks/check-resources.py refuses them: a task reserves its GPU as a
# deploy device), counted as a GPU here so that no GPU goes unseen
GPU_OTHER_RE = re.compile(r"^    (gpus:|runtime:\s*[\"']?nvidia\b)")


def holds_gpu(block: list[str]) -> bool:
    """A compose service's lines reserve a GPU: a deploy device with an NVIDIA (or CDI) driver or `gpu` among its
    capabilities, `gpus:`, or `runtime: nvidia`."""
    for n, ln in enumerate(block):
        if GPU_DEVICE_RE.match(ln) or GPU_CAP_RE.match(ln) or GPU_OTHER_RE.match(ln):
            return True
        m = CAP_BLOCK_RE.match(ln)
        if m:
            for nxt in block[n + 1:]:
                if not nxt.strip() or nxt.lstrip().startswith("#"):
                    continue
                item = re.match(r"^(\s*)-\s*[\"']?([A-Za-z0-9_.-]+)", nxt)
                if not item or len(item.group(1)) < len(m.group(1)):
                    break
                if item.group(2) == "gpu":
                    return True
    return False


def deploy_limits(block: list[str]) -> bool:
    """A compose service's lines set `deploy.resources.limits` (docker refuses it beside `cpus` / `mem_limit`, the keys
    the caps are written in)."""
    path: list[tuple[int, str]] = []
    for ln in block:
        m = re.match(r"^(\s*)([A-Za-z0-9_.-]+):(.*)$", ln.rstrip("\n"))
        if not m or ln.lstrip().startswith("#"):
            continue
        ind, key, rest = len(m.group(1)), m.group(2), m.group(3)
        while path and path[-1][0] >= ind:
            path.pop()
        path.append((ind, key))
        keys = [k for _, k in path]
        if keys[-3:] == ["deploy", "resources", "limits"] or (key == "deploy" and "limits" in rest) or (
                keys[-2:] == ["deploy", "resources"] and "limits" in rest):
            return True
    return False


def check_block(name: str, block: list[str]) -> None:
    if deploy_limits(block):
        raise ValueError(f"service {name}: deploy.resources.limits; write the caps as `cpus`, `mem_limit` and "
                         "`pids_limit` (docs/protocol/README.md §6; docker refuses both forms together)")


def service_caps(text: str) -> dict[str, dict]:
    """{service: {"cpus", "memory_gb", "pids", "gpu_memory_gb", "gpu"}} as the compose file sets them (None: not set
    there; `gpu`: the service reserves an NVIDIA device): the caps docker really applies to every service but main,
    whose cpus and memory come from task.toml [environment] (Harbor)."""
    lines = text.splitlines(keepends=True)
    i, j = services_span(lines)
    out = {}
    for name, k0, k1 in service_blocks(lines, i, j):
        check_block(name, lines[k0:k1])
        got = {}
        for key, field, conv in (("cpus", "cpus", float), ("mem_limit", "memory_gb", _mem_gb), ("pids_limit", "pids", int),
                                 (GPU_KEY, "gpu_memory_gb", float)):
            k = has_key(lines, k0, k1, key)
            got[field] = None if k is None else conv(lines[k].split(":", 1)[1].split("#", 1)[0].strip().strip("'\""))
        got["gpu"] = holds_gpu(lines[k0:k1])
        out[name] = got
    return out


def monitor_block(gpu: bool, observe: bool) -> list[str]:
    b = [BEGIN + " (resource monitor, PROTOCOL §6; generated by images/monitor/rcb_monitor/inject.py)",
         "  rcb_monitor:",
         f"    image: {IMAGE}",
         "    pid: host",
         "    cgroup: host",
         "    network_mode: none",
         "    cap_add: [SYS_PTRACE]",
         f"    cpus: {MONITOR_CAPS['cpus']}",
         f"    mem_limit: {MONITOR_CAPS['mem']}",
         f"    pids_limit: {MONITOR_CAPS['pids']}",
         "    restart: on-failure",   # no count: a monitor that dies mid-throttle always comes back to undo it
         "    working_dir: /var/rcb-monitor",
         "    volumes:",
         f"      - {LIMITS_MOUNT}",
         "      - rcb_limits:/run/rcb-limits"]
    if observe:
        b.append("      - rcb_observe:/run/rcb-observe")
    b += ["    environment:",
          "      RCB_LIMITS_ENFORCE: ${RCB_LIMITS_ENFORCE:-0}",
          "      RCB_LIMITS_TOLERANCE: ${RCB_LIMITS_TOLERANCE:-" + _num(rcb_limits.TOLERANCE) + "}",
          '    command: ["python3", "/opt/rcb_monitor/monitor.py", "run"]']
    if gpu:
        b += ["    deploy:", "      resources:", "        reservations:", "          devices:",
              "            - driver: nvidia", "              count: 1", "              capabilities: [gpu]"]
    b.append(END)
    return [x + "\n" for x in b]


def cap_lines(name: str, caps: dict, present: set[str]) -> list[str]:
    c = caps.get(name) or {}
    out = []
    if name != "main":
        if "cpus" not in present and c.get("cpus"):
            out.append(f"    cpus: {_num(c['cpus'])}   {MARK}\n")
        if "mem_limit" not in present and c.get("memory_gb"):
            out.append(f"    mem_limit: {int(round(float(c['memory_gb']) * 1024))}m   {MARK}\n")
    if "pids_limit" not in present and c.get("pids"):
        out.append(f"    pids_limit: {int(c['pids'])}   {MARK}\n")
    if GPU_KEY not in present and c.get("gpu_memory_gb"):
        out.append(f"    {GPU_KEY}: {_num(c['gpu_memory_gb'])}   # GiB   {MARK}\n")
    return out


def current_caps(text: str | None) -> dict[str, dict]:
    """The caps a compose file sets now (generated lines included): what a task no rule matches keeps."""
    if not text:
        return {}
    try:
        return {n: {k: v for k, v in c.items() if k != "gpu" and v is not None}
                for n, c in service_caps(text).items() if n != "rcb_monitor"}
    except ValueError:
        return {}


def is_generated(text: str) -> bool:
    """A compose file this module wrote whole (GEN_HEADER, or the header of an earlier layout: its first line is a
    `# Generated by ... inject.py (...)` comment ending in `rcb-monitor`)."""
    first = text.split("\n", 1)[0]
    return first == GEN_HEADER or (first.startswith("# Generated by ") and "inject.py" in first and first.endswith(" rcb-monitor"))


def render_compose(text: str | None, mode: str, caps: dict) -> str:
    if text is None or is_generated(text):
        text = GEN_HEADER + "\nservices:\n  main:   " + MARK + "\n"
    lines = strip_generated(text.splitlines(keepends=True))
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    i, j = services_span(lines)
    blocks = service_blocks(lines, i, j)
    if not any(n == "main" for n, _, _ in blocks):
        lines.insert(i + 1, "  main:   " + MARK + "\n")
        i, j = services_span(lines)
        blocks = service_blocks(lines, i, j)
    gpu = any(holds_gpu(lines[k0:k1]) for _, k0, k1 in blocks)
    observe_any = False
    # edit the blocks bottom-up, so earlier indices stay valid
    for name, k0, k1 in reversed(blocks):
        check_block(name, lines[k0:k1])
        kind = kind_of(mode, name)
        observe_any |= kind == "observe"
        beacon = "rcb_limits:/run/rcb-limits:ro" if kind == "scope" else "rcb_observe:/run/rcb-observe:ro"
        present = {key for key in ("cpus", "mem_limit", "pids_limit", GPU_KEY) if has_key(lines, k0, k1, key) is not None}
        vk = has_key(lines, k0, k1, "volumes")
        if vk is not None:
            if lines[vk].split(":", 1)[1].strip() and not lines[vk].split(":", 1)[1].strip().startswith("#"):
                raise ValueError(f"service {name}: inline volumes list; use a block list")
            lines.insert(vk + 1, f"      - {beacon}   {MARK}\n")
        add = cap_lines(name, caps, present)
        if vk is None:
            add += [f"    volumes:   {MARK}\n", f"      - {beacon}   {MARK}\n"]
        lines[k0 + 1:k0 + 1] = add
    i, j = services_span(lines)
    end = j
    while end > i + 1 and not lines[end - 1].strip():
        end -= 1
    lines[end:end] = monitor_block(gpu, observe_any)
    vols = [f"  rcb_limits:   {MARK}\n"] + ([f"  rcb_observe:   {MARK}\n"] if observe_any else [])
    v = next((k for k, ln in enumerate(lines) if re.match(r"^volumes:\s*(#.*)?$", ln)), None)
    if v is None:
        if lines and lines[-1].strip():
            pass
        lines += [f"volumes:   {MARK}\n"] + vols
    else:
        lines[v + 1:v + 1] = vols
    return "".join(lines)


def render_test_compose(text: str, gpu_gb: float | None) -> str:
    """tests/docker-compose.yaml (a separate verifier's own services): `x-gpu-memory-gb` on every service that reserves
    a GPU and sets none itself, `gpu_gb` (main's cap: a recorded cap, nothing measures it in the verifier phase); the
    generated lines of an earlier run removed first."""
    lines = strip_generated(text.splitlines(keepends=True))
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    try:
        i, j = services_span(lines)
    except ValueError:
        return "".join(lines)
    for name, k0, k1 in reversed(service_blocks(lines, i, j)):
        if gpu_gb and holds_gpu(lines[k0:k1]) and has_key(lines, k0, k1, GPU_KEY) is None:
            lines[k0 + 1:k0 + 1] = cap_lines(name, {name: {"gpu_memory_gb": gpu_gb}}, {"pids_limit"})
    return "".join(lines)


# --------------------------------------------------------------------------------------------------- task.toml / tests
def render_toml(s: str) -> str:
    s = s.replace(ARTIFACT + ", ", "").replace("artifacts = [" + ARTIFACT + "]\n", "")
    s = re.sub(r"(?ms)^# Resource(?: limit)?s \((?:docs/(?:PROTOCOL|protocol/README)\.md|PROTOCOL) §(?:2\.10|6)\): seal the monitor's record first.*?\ntimeout_sec = \d+\n\n?", "", s)
    s = re.sub(r'(?m)^RCB_LIMITS_ENFORCE = .*\n', "", s)
    s = re.sub(r"(?m)^\[verifier\.env\]\n(?=\n|\[|\Z)", "", s)
    # 1. the record, an artifact of the rcb_monitor service (first in the list)
    if re.search(r"(?m)^artifacts = \[", s):
        s = re.sub(r"(?m)^artifacts = \[", "artifacts = [" + ARTIFACT + ", ", s, count=1)
    else:
        s = re.sub(r'(?m)^(schema_version = .*\n)', r"\1" + "artifacts = [" + ARTIFACT.replace("\\", "\\\\") + "]\n", s, count=1)
    # 2. the seal hook, before every other [[verifier.collect]] (Harbor runs main's hooks first, then the sidecars' in order)
    m = re.search(r"(?m)^(#[^\n]*\n)*\[\[verifier\.collect\]\]\n", s)
    if m:
        s = s[:m.start()] + HOOK + "\n" + s[m.start():]
    else:
        v = re.search(r"(?m)^\[verifier\]\n", s)
        if not v:
            raise ValueError("task.toml has no [verifier] table")
        nxt = re.search(r"(?m)^\[", s[v.end():])
        at = v.end() + nxt.start() if nxt else len(s)
        head = s[:at].rstrip("\n") + "\n\n"
        s = head + HOOK + ("\n" + s[at:] if at < len(s) else "")
    # 3. the run-time switch, also for the verifier (used only when there is no sealed record to take it from)
    line = 'RCB_LIMITS_ENFORCE = "${RCB_LIMITS_ENFORCE:-0}"\n'
    if re.search(r"(?m)^\[verifier\.env\]\n", s):
        s = re.sub(r"(?m)^\[verifier\.env\]\n", "[verifier.env]\n" + line.replace("\\", "\\\\"), s, count=1)
    else:
        s = s.rstrip("\n") + "\n\n[verifier.env]\n" + line
    return s


def render_test_sh(s: str) -> str:
    lines = [ln for ln in s.splitlines(keepends=True)
             if "/tests/rcb_limits.py verify" not in ln and "/tests/rcb_limits.py sanitize" not in ln]
    k = next((n for n, ln in enumerate(lines) if re.match(r"\s*rm\s+-[rRf]+\s+/logs/verifier/\*", ln)), None)
    if k is None:
        k = next((n for n, ln in enumerate(lines) if ln.strip() and not ln.lstrip().startswith("#")), len(lines)) - 1
    lines[k + 1:k + 1] = [TRAP + "\n", GUARD + "\n"]
    return "".join(lines)


def render_dockerfile(s: str) -> str:
    lines = [ln for ln in s.splitlines(keepends=True)
             if not ln.rstrip().endswith(MARK) and not _docker_copy_line(ln)]
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    return "".join(lines) + DOCKER_COPY + "\n"


# --------------------------------------------------------------------------------------------------- entry point
def write_compose(task: Path, caps: dict[str, dict] | None = None) -> str:
    """Writes the caps (and the monitor's service) into the task's compose file; returns its new text."""
    task = Path(task)
    comp = task / "environment" / "docker-compose.yaml"
    old = comp.read_text() if comp.is_file() else None
    new = render_compose(old, mode_of(task), current_caps(old) if caps is None else caps)
    write_if_changed(comp, new)
    tc = task / "tests" / "docker-compose.yaml"
    if tc.is_file():   # a separate verifier with services of its own: main's GPU-memory cap on its GPU services
        applied = applied_caps(tomllib.loads((task / "task.toml").read_text()), new)
        main_gpu = applied["main"].get("gpu_memory_gb") or max(
            (float(c.get("gpu_memory_gb") or 0) for c in applied.values()), default=0.0)
        write_if_changed(tc, render_test_compose(tc.read_text(), main_gpu or None))
    return new


def apply(task: Path, caps: dict[str, dict] | None = None) -> None:
    """Wires the monitor into `task` and writes `caps` ({service: {cpus, memory_gb, pids, gpu_memory_gb}}, from the
    task's rule in scripts/task_resources.toml) into its compose file; None: the caps the compose file has now."""
    task = Path(task)
    cfg = tomllib.loads((task / "task.toml").read_text())
    for f in CODE:                               # the code is the image's (IMAGE); no copy in the task
        (task / "environment" / "rcb_monitor" / f).unlink(missing_ok=True)
    new = write_compose(task, caps)
    applied = applied_caps(cfg, new)
    lim = limits_json(task, cfg, applied)
    js = json.dumps(lim, indent=1, sort_keys=True) + "\n"
    write_if_changed(task / "environment" / "rcb_monitor" / "limits.json", js)
    write_if_changed(task / "task.toml", render_toml((task / "task.toml").read_text()))
    tests = task / "tests"
    (tests / "rcb_limits.py").unlink(missing_ok=True)   # the verifier's copy comes from IMAGE (DOCKER_COPY)
    write_if_changed(tests / "rcb_limits.json", js)
    if (tests / "Dockerfile").is_file():
        write_if_changed(tests / "Dockerfile", render_dockerfile((tests / "Dockerfile").read_text()))
    if (tests / "test.sh").is_file():
        write_if_changed(tests / "test.sh", render_test_sh((tests / "test.sh").read_text()))


def generated_sources() -> set[bytes]:
    """The files apply() copies verbatim into a task (normalize's text rewrites must leave them alone): none since the
    code is in the image."""
    return set()


def contents() -> dict[str, str]:
    """{file: sha256} of this directory's CODE files (what IMAGE must carry at CODE_DIR)."""
    import hashlib
    return {f: hashlib.sha256((SRC / f).read_bytes()).hexdigest() for f in CODE}


def registry_contents_problems(image: str = IMAGE) -> list[str]:
    """Problems with the CODE files the pinned image's top layer carries against CONTENTS, read from the registry with
    an anonymous token (the image is public; standard library only, no docker): the check that ties CONTENTS to IMAGE."""
    import gzip, hashlib, io, json as _json, tarfile, urllib.request
    ref, digest = image.split("@")
    repo = ref.split("/", 1)[1].rsplit(":", 1)[0]
    tok = _json.load(urllib.request.urlopen(f"https://ghcr.io/token?scope=repository:{repo}:pull", timeout=30))["token"]

    def get(path: str, accept: str = "") -> bytes:
        req = urllib.request.Request(f"https://ghcr.io/v2/{repo}/{path}", headers={"Authorization": f"Bearer {tok}",
                                                                                  **({"Accept": accept} if accept else {})})
        return urllib.request.urlopen(req, timeout=120).read()
    man = _json.loads(get(f"manifests/{digest}", "application/vnd.oci.image.manifest.v1+json,"
                                                  "application/vnd.docker.distribution.manifest.v2+json"))
    blob = get(f"blobs/{man['layers'][-1]['digest']}")
    got = {}
    with tarfile.open(fileobj=io.BytesIO(gzip.decompress(blob) if blob[:2] == b"\x1f\x8b" else blob)) as t:
        for m in t.getmembers():
            name = m.name.removeprefix("./")
            if m.isfile() and name.startswith(CODE_DIR.lstrip("/") + "/"):
                got[name.rsplit("/", 1)[1]] = hashlib.sha256(t.extractfile(m).read()).hexdigest()
    return [f"{CODE_DIR}/{f}: image {got.get(f)} != CONTENTS {CONTENTS.get(f)}" for f in CODE if got.get(f) != CONTENTS.get(f)]


def verify_image(image: str = IMAGE) -> list[str]:
    """Problems with the files IMAGE carries at CODE_DIR against CONTENTS (needs docker and the image)."""
    import subprocess
    r = subprocess.run(["docker", "run", "--rm", "--network", "none", "--entrypoint", "sha256sum", image,
                        *[f"{CODE_DIR}/{f}" for f in CODE]], capture_output=True, text=True)
    if r.returncode != 0:
        return [f"docker run {image}: {r.stderr.strip()[-300:]}"]
    got = {Path(ln.split()[1]).name: ln.split()[0] for ln in r.stdout.splitlines() if ln.strip()}
    return [f"{CODE_DIR}/{f}: image {got.get(f)} != CONTENTS {CONTENTS.get(f)}" for f in CODE if got.get(f) != CONTENTS.get(f)]


if __name__ == "__main__":
    import sys
    if sys.argv[1:2] == ["stage-context"]:       # images/monitor/context/: the CODE files with content-derived mtimes
        sys.path.insert(0, str(SRC.parents[2] / "scripts"))
        import stamp_mtimes
        ctx = SRC.parent / "context"
        shutil.rmtree(ctx, ignore_errors=True)
        ctx.mkdir(parents=True)
        for f in CODE:
            shutil.copyfile(SRC / f, ctx / f)
            (ctx / f).chmod(0o644)
        stamp_mtimes.stamp_tree(str(ctx), True)
        print(ctx)
    elif sys.argv[1:2] == ["contents"]:          # the hashes for CONTENTS
        print(json.dumps(contents(), indent=1, sort_keys=True))
    elif sys.argv[1:2] == ["verify-image"]:      # IMAGE (or the given image) carries exactly CONTENTS
        bad = verify_image(*(sys.argv[2:3] or [IMAGE]))
        print("\n".join(bad) or f"ok {sys.argv[2] if len(sys.argv) > 2 else IMAGE}: {len(CODE)} files match CONTENTS")
        sys.exit(1 if bad else 0)
    else:
        for d in sys.argv[1:]:
            apply(Path(d))
