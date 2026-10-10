#!/usr/bin/env bash
# PROTOCOL §4: the verifier must run in its own sandbox, never in the container the agent controlled.
# task.toml: [verifier].environment_mode = "separate"; tests/Dockerfile exists, FROMs a pinned registry image and ships
# /tests/test.sh; any compose sidecar image is pinned. Agent egress is a run-time choice (scripts/set_agent_egress.py):
# public is allowed; if an allowlist is set it must list hosts (an empty allowlist breaks the agent's model API), and
# they are the hosts of scripts/set_agent_egress.py (one list for every task).
# PROTOCOL §2.6 adds two rules, because Harbor mounts /logs/verifier read-write into the agent's container and some
# simulators keep a cache of generated code:
# - tests/test.sh empties /logs/verifier before anything else (a planted reward.json must not survive a grader crash):
#   `rm -rf /logs/verifier/*`, or `find /logs/verifier -mindepth 1 ... -exec rm ...` (the form that keeps Harbor's
#   test-stdout.txt). Every task.
# - no writable volume crosses the trust boundary: named volumes mounted by a trusted container (the verifier, a
#   standard task's sim sidecar) are *_trusted and never mounted by the agent's container. Every task.
# The compose file is read without a YAML library, so the reader fails closed: a volumes entry or a service line it
# does not understand is a failure, never skipped (a trailing comment once hid every volume of a service from this
# check; ci_checks/check-ci-selftest.py now mutates real tasks and requires each rule to fire). Also, for every
# service but the generated rcb_monitor: nothing that widens a container (privileged, cap_add, devices, the host's
# namespaces, volumes_from ...), no published port on a sidecar, the agent's container binds only directories the
# runner names through an environment variable (never the task's own ./sim, ../tests, ../solution or a docker socket),
# beacons read-only; standard modes: the verifier's evidence is collected from a sidecar, never from `main`.
t="$1"; python3 - "$t" "$(cd "$(dirname "$0")/.." && pwd)" <<'PY'
import sys, tomllib, pathlib, re
t = pathlib.Path(sys.argv[1]); root = pathlib.Path(sys.argv[2]); rc = 0
def fail(m):
    global rc; print(f"FAIL {t}: {m}"); rc = 1
d = tomllib.load(open(t / "task.toml", "rb"))
if (d.get("verifier") or {}).get("environment_mode") != "separate": fail('[verifier].environment_mode must be "separate"')
ag = d.get("agent") or {}
if ag.get("network_mode") == "allowlist" and not ag.get("allowed_hosts"): fail('[agent] allowlist without allowed_hosts (the agent could not reach its model API)')
elif ag.get("network_mode") == "allowlist":
    # one allowlist for every task: scripts/set_agent_egress.py HOSTS (a task that lacks a model API's host ends as a 0
    # without having acted; one that adds a host opens what the others close)
    m = re.search(r"(?s)^HOSTS = \[(.*?)\]", (root / "scripts/set_agent_egress.py").read_text(), re.M)
    hosts = re.findall(r'"([^"]+)"', m.group(1)) if m else []
    if hosts and sorted(ag["allowed_hosts"]) != sorted(hosts):
        fail(f"[agent].allowed_hosts differs from scripts/set_agent_egress.py HOSTS (missing {sorted(set(hosts) - set(ag['allowed_hosts']))}, extra {sorted(set(ag['allowed_hosts']) - set(hosts))})")
df = t / "tests/Dockerfile"
if not df.is_file(): fail("tests/Dockerfile missing (separate verifier image)")
else:
    m = re.search(r"^FROM\s+(\S+)", df.read_text(), re.M); frm = m.group(1) if m else ""
    if not (re.match(r"^[\w.\-]+(:\d+)?/.+[:@].+", frm) and not frm.endswith(":latest")): fail(f"tests/Dockerfile FROM {frm!r} must be a pinned registry image")
    if "test.sh" not in df.read_text(): fail("tests/Dockerfile must COPY test.sh into /tests/")
cf = t / "environment/docker-compose.yaml"
if cf.is_file():
    for img in re.findall(r"^\s*image:\s*(\S+)", cf.read_text(), re.M):
        if not (re.match(r"^[\w.\-]+(:\d+)?/.+[:@].+", img) and not img.endswith(":latest")): fail(f"compose sidecar image {img!r} must be pinned")

# test.sh clears /logs/verifier first
CLEAR_LOGS = re.compile(r"^(rm\s+-[rRf]+\s+/logs/verifier/\*|find\s+/logs/verifier\s+-mindepth\s+1\b.*(-delete|-exec\s+rm))")
sh = t / "tests/test.sh"
if sh.is_file():
    cmds = [ln.strip() for ln in sh.read_text().splitlines() if ln.strip() and not ln.strip().startswith("#")]
    cmds = [c for c in cmds if not re.match(r"(set\s|mkdir\s+-p\s+/logs/verifier\s*$)", c)]
    if not cmds or not CLEAR_LOGS.match(cmds[0]):
        fail("tests/test.sh must empty /logs/verifier before anything else (`rm -rf /logs/verifier/*`, or find ... -exec rm keeping test-stdout.txt)")


def uncomment(line: str) -> str:
    """The line without its trailing comment (a `#` at the start or after white space, outside quotes)."""
    q = None
    for i, ch in enumerate(line):
        if q:
            if ch == q: q = None
        elif ch in "'\"": q = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"): return line[:i].rstrip()
    return line.rstrip()


BIND = (".", "/", "$", "~")     # a volume source that is a host path (bind mount), not a named volume
LONG_KEYS = r"(type|source|target|read_only|bind|volume|tmpfs|consistency)"


def compose_services(compose: pathlib.Path):
    """({service: {"keys": {key: inline value}, "mounts": [(kind, source, rest)]}}, [what could not be read]).
    kind: "volume" (a named volume) or "bind"; rest: target and mode of the short form (`/cache:ro`), or "ro" / "" for
    the long form. Indentation-based (2 spaces a level, as scripts/rcb_monitor/inject.py writes and requires), no YAML
    dependency; whatever it does not understand inside `services:` is reported, never skipped."""
    out, bad = {}, []
    svc, in_services, in_vols, item = None, False, False, None

    def close():
        nonlocal item
        if item is not None:
            typ, src = item.get("type", "volume"), item.get("source", "")
            if typ in ("volume", "bind") and src:
                kind = "bind" if typ == "bind" or src.startswith(BIND) else "volume"
                out[svc]["mounts"].append((kind, src, "ro" if item.get("read_only", "").lower() == "true" else ""))
            elif typ not in ("tmpfs",):
                bad.append(f"service {svc}: volume entry {item} (long form) not understood")
        item = None

    for n, raw in enumerate(compose.read_text().splitlines(), 1):
        line = uncomment(raw)
        if not line.strip(): continue
        if "\t" in line[: len(line) - len(line.lstrip())]:
            bad.append(f"line {n}: tab in the indentation"); continue
        ind = len(line) - len(line.lstrip())
        text = line.strip()
        if ind == 0:
            close(); in_services = bool(re.match(r"services\s*:\s*$", text)); svc = None; in_vols = False
            if text.startswith("services") and not in_services: bad.append(f"line {n}: `{text}` (services must be a block)")
            continue
        if not in_services: continue
        if ind == 2:
            close(); in_vols = False
            m = re.match(r"""^['"]?([A-Za-z0-9_.-]+)['"]?\s*:\s*$""", text)
            if not m:
                bad.append(f"line {n}: `{text}` is not a service line"); svc = None; continue
            svc = m.group(1); out[svc] = {"keys": {}, "mounts": []}
            continue
        if svc is None or ind < 4 or ind == 3:
            bad.append(f"line {n}: `{text}` at an unexpected indentation"); continue
        if ind == 4:
            close(); in_vols = False
            m = re.match(r"""^['"]?([A-Za-z0-9_.<-]+)['"]?\s*:\s*(.*)$""", text)
            if not m:
                bad.append(f"line {n}: service {svc}: `{text}` is not a key"); continue
            key, val = m.group(1), m.group(2).strip()
            out[svc]["keys"][key] = val
            if key == "volumes":
                if not val: in_vols = True
                elif val.startswith("[") and val.endswith("]"):
                    for it in [x.strip().strip("'\"") for x in val[1:-1].split(",") if x.strip()]:
                        src, _, rest = it.partition(":")
                        out[svc]["mounts"].append(("bind" if src.startswith(BIND) else "volume", src, rest))
                else: bad.append(f"line {n}: service {svc}: volumes `{val}` not understood")
            continue
        if not in_vols: continue                    # deeper lines of other keys (environment, deploy, ...)
        if text.startswith("-"):
            close()
            body = text[1:].strip()
            m = re.match(rf"^{LONG_KEYS}\s*:\s*(.*)$", body)
            if m:                                    # long form: `- type: volume` / `source: x` / `target: /y`
                item = {m.group(1): m.group(2).strip().strip("'\"")}
                continue
            body = body.strip("'\"")
            if not body or body.startswith(("{", "[", "*", "&")):
                bad.append(f"line {n}: service {svc}: volume entry `{text}` not understood"); continue
            src, _, rest = body.partition(":")
            if src.startswith("$"):                  # ${VAR:?message with : in it}:/target -> a bind named by the runner
                out[svc]["mounts"].append(("bind", src, rest)); continue
            out[svc]["mounts"].append(("bind" if src.startswith(BIND) else "volume", src, rest))
            continue
        m = re.match(rf"^{LONG_KEYS}\s*:\s*(.*)$", text)
        if item is not None and m:
            item[m.group(1)] = m.group(2).strip().strip("'\""); continue
        if item is not None and re.match(r"^[a-z_]+\s*:", text): continue      # options under bind: / volume: (nocopy, ...)
        bad.append(f"line {n}: service {svc}: `{text}` inside volumes not understood")
    close()
    return out, bad


def named_volumes(services: dict) -> dict:
    return {s: [src for kind, src, _ in v["mounts"] if kind == "volume"] for s, v in services.items()}


env_c, test_c = t / "environment/docker-compose.yaml", t / "tests/docker-compose.yaml"
# The resource monitor's beacons (PROTOCOL §2.10): written only by the trusted rcb_monitor service, mounted read-only in
# the services it watches (ci_checks/check-monitor.py checks the read-only mounts); no write crosses the boundary.
BEACONS = {"rcb_limits", "rcb_observe"}
# Nothing that widens a container beyond its own namespaces and file system (the generated rcb_monitor service has
# its own rules: ci_checks/check-monitor.py). Sidecars publish no port: the agent reaches the service on localhost only.
WIDEN = ("privileged", "cap_add", "security_opt", "devices", "device_cgroup_rules", "volumes_from", "pid", "ipc", "uts",
         "cgroup", "cgroup_parent", "userns_mode", "extends", "<<")
mode = next((m for m in ("standard-realtime", "privileged", "standard") if t.name.endswith("-" + m)), "")
if env_c.is_file():
    services, bad = compose_services(env_c)
    for b in bad: fail(f"environment/docker-compose.yaml: {b} (ci_checks/check-verifier-isolation.sh reads no YAML: keep to the block form)")
    for svc, info in services.items():
        if svc == "rcb_monitor": continue
        for k in WIDEN:
            if k in info["keys"]: fail(f"service {svc}: `{k}` is not allowed (it widens the container beyond its own namespaces and files)")
        if svc != "main":
            for k in ("ports", "expose", "network_mode"):
                if k in info["keys"]: fail(f"sidecar {svc}: `{k}` is not allowed (the agent reaches a sidecar on localhost only, PROTOCOL §4.1)")
        for kind, src, rest in info["mounts"]:
            if kind == "bind":
                if svc == "main" and not src.startswith("$"):
                    fail(f"the agent container bind-mounts {src} (only a directory the runner names through an environment variable; never the task's own files or a socket)")
                continue
            if src in BEACONS:
                if "ro" not in rest.split(":"): fail(f"service {svc}: mounts the beacon volume {src} writable")
                continue
            if svc == "main" and src.endswith("_trusted"): fail(f"the agent container mounts trusted volume {src}")
            if svc != "main" and not src.endswith("_trusted"): fail(f"sidecar {svc} mounts {src}, which is not a *_trusted volume")
    if mode in ("standard", "standard-realtime"):
        # the verifier's evidence comes from a sidecar (a channel the agent cannot write), never from the agent's container
        sidecars = [s for s in services if s not in ("main", "rcb_monitor")]
        for a in d.get("artifacts") or []:
            src = a if isinstance(a, str) else (a.get("source") or "")
            who = "main" if isinstance(a, str) else a.get("service", "main")
            if who == "main" and re.match(r"^/(data|out|var/rcb-monitor)(/|$)", src):
                fail(f"artifact {src} is collected from the agent's container (the evidence must come from a sidecar)")
            if who != "main" and who != "rcb_monitor" and who not in sidecars:
                fail(f"artifact {src}: service {who!r} is not a sidecar of environment/docker-compose.yaml")
        hooks = {h.get("service") for h in (d.get("verifier") or {}).get("collect") or [] if isinstance(h, dict)}
        if sidecars and not (hooks & set(sidecars)):
            fail("no [[verifier.collect]] hook on a sidecar (the sidecar finalizes its own evidence, PROTOCOL §4.8)")
if test_c.is_file():
    services, bad = compose_services(test_c)
    for b in bad: fail(f"tests/docker-compose.yaml: {b}")
    for v in named_volumes(services).get("main", []):
        if not v.endswith("_trusted"): fail(f"the verifier mounts {v}, which is not a *_trusted volume")
sys.exit(rc)
PY
