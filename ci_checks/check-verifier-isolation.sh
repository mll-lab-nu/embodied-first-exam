#!/usr/bin/env bash
# INVARIANT (docs/PROTOCOL.md Appendix H.1 verifier isolation, H.3 the standard trust boundary's topology, H.4 evidence
# from a sidecar, H.6 egress): part of the required CI job `invariants` (ci_checks/run_invariants.sh); no task value can
# turn a rule here off. The verifier must run in its own sandbox, never in the container the agent controlled.
# task.toml: [verifier].environment_mode = "separate"; tests/Dockerfile exists and ships /tests/test.sh (image pins:
# ci_checks/check-dockerfile.sh, advisory). Agent egress (H.6): a task is on the allowlist, whose hosts are those of
# scripts/set_agent_egress.py (one list for every task; an empty one breaks the agent's model API), unless its author
# declares open egress, `[metadata] network = "open"` (then [agent] sets no network policy, or `public`).
# Appendix H.1 adds two rules, because Harbor mounts /logs/verifier read-write into the agent's container and some
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
# Review round 3 (M4, M5) closed four ways around these rules, all of them green before:
# - a service with `networks:` or `network_mode:` is one Harbor's egress control leaves alone (harbor 0.23
#   docker.py _egress_controlled_service_names routes only services without either key through the allowlist): not
#   allowed on any service but the generated rcb_monitor (`network_mode: none`, ci_checks/check-monitor.py);
# - a volume source with a variable is a runner-named directory only as the whole source `${RCB_NAME}` or
#   `${RCB_NAME:?message}`: a default (`${V:-rcb_x_trusted}`, `${D:-./sim}`), a variable the runner does not own
#   (`${PWD}`, `${CONTEXT_DIR}`) or a path after it resolves to a trusted volume, a task file or a host path;
# - the file's top level holds `services:` and `volumes:` only, and a top-level volume is a bare name: `name:`,
#   `external:` and `driver_opts:` alias one volume under two names or bind a path, `secrets:` / `configs:` /
#   `include:` hand a container files of the task;
# - a service takes no `secrets`, `configs`, `env_file` or `build` (the same files by another road; images are pinned).
t="$1"; python3 - "$t" "$(cd "$(dirname "$0")/.." && pwd)" <<'PY'
import sys, tomllib, pathlib, re
t = pathlib.Path(sys.argv[1]); root = pathlib.Path(sys.argv[2]); rc = 0
def fail(m):
    global rc; print(f"FAIL {t}: {m}"); rc = 1
d = tomllib.load(open(t / "task.toml", "rb"))
if (d.get("verifier") or {}).get("environment_mode") != "separate": fail('[verifier].environment_mode must be "separate"')
ag = d.get("agent") or {}
# Appendix H.6: the default is the allowlist; open egress is the task author's own declaration, never a list kept here
net = (d.get("metadata") or {}).get("network", "allowlist")
if net not in ("allowlist", "open"):
    fail(f'[metadata] network = {net!r}: "allowlist" (the default) or "open"')
if net == "open":
    if ag.get("network_mode", "public") != "public" or "allowed_hosts" in ag:
        fail('[metadata] network = "open", but [agent] sets another network policy: leave network_mode / allowed_hosts out (or network_mode = "public"), or drop the declaration')
elif ag.get("network_mode") != "allowlist":
    fail('[agent].network_mode must be "allowlist" (PROTOCOL Appendix H.6: the model APIs and the package registries, unless the task declares `[metadata] network = "open"`; the generator writes it, scripts/set_agent_egress.py allowlist)')
elif not ag.get("allowed_hosts"):
    fail('[agent] allowlist without allowed_hosts (the agent could not reach its model API)')
else:
    # one allowlist for every task: scripts/set_agent_egress.py HOSTS (a task that lacks a model API's host ends as a 0
    # without having acted; one that adds a host opens what the others close)
    m = re.search(r"(?s)^HOSTS = \[(.*?)\]", (root / "scripts/set_agent_egress.py").read_text(), re.M)
    hosts = re.findall(r'"([^"]+)"', m.group(1)) if m else []
    if not hosts: fail("cannot read HOSTS from scripts/set_agent_egress.py (the allowlist every task must have)")
    elif sorted(ag["allowed_hosts"]) != sorted(hosts):
        fail(f"[agent].allowed_hosts differs from scripts/set_agent_egress.py HOSTS (missing {sorted(set(hosts) - set(ag['allowed_hosts']))}, extra {sorted(set(ag['allowed_hosts']) - set(hosts))})")
# Harbor lets a step's own policy override [agent] (trial/network_policy.py: `[[steps]]` with `[steps.agent]`): no task has
# steps, and one that sets a network policy there would open what [agent] closes, and what a run's gateway-only copy narrows
for st in d.get("steps") or []:
    for role in ("agent", "verifier", "environment"):
        if isinstance(st, dict) and {"network_mode", "allowed_hosts"} & set((st.get(role) or {})):
            fail(f"[[steps]] {st.get('name', '?')}: a step sets its own network policy ([steps.{role}]); the task's [agent] / [verifier] policy must be the only one")
df = t / "tests/Dockerfile"
if not df.is_file(): fail("tests/Dockerfile missing (separate verifier image)")
elif "test.sh" not in df.read_text(): fail("tests/Dockerfile must COPY test.sh into /tests/")

# test.sh clears /logs/verifier first
CLEAR_LOGS = re.compile(r"^(rm\s+-[rRf]+\s+/logs/verifier/\*(\s|;|&|$)|find\s+/logs/verifier\s+-mindepth\s+1\b.*(-delete|-exec\s+rm))")
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
# A source with a variable: the whole source is one variable of the runner's (RCB_*), without a default. Anything else
# (a default, another variable, a path or a name around it) resolves to something this reader cannot see.
RUNNER_DIR = re.compile(r"^\$\{RCB_[A-Z0-9_]+(:?\?[^}]*)?\}$")
VAR_RULE = "a variable in a volume source must be the whole source, `${RCB_NAME}` or `${RCB_NAME:?message}` (no default, no path after it)"
TOP_LEVEL = ("services", "volumes")
LONG_KEYS = r"(type|source|target|read_only|bind|volume|tmpfs|consistency)"


def compose_services(compose: pathlib.Path):
    """({service: {"keys": {key: inline value}, "mounts": [(kind, source, rest)]}}, [what could not be read]).
    kind: "volume" (a named volume) or "bind"; rest: target and mode of the short form (`/cache:ro`), or "ro" / "" for
    the long form. Indentation-based (2 spaces a level, as scripts/rcb_monitor/inject.py writes and requires), no YAML
    dependency; whatever it does not understand inside `services:` is reported, never skipped."""
    out, bad = {}, []
    svc, in_services, in_vols, item, top, first = None, False, False, None, None, False

    def close():
        nonlocal item
        if item is not None:
            typ, src = item.get("type", "volume"), item.get("source", "")
            if "$" in src and not RUNNER_DIR.match(src):
                bad.append(f"service {svc}: volume source `{src}`: {VAR_RULE}")
            elif typ in ("volume", "bind") and src:
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
            top = text.partition(":")[0].strip().strip("'\"")
            if top not in TOP_LEVEL:
                bad.append(f"line {n}: top-level `{top}` is not allowed (only {' and '.join(TOP_LEVEL)}: include, secrets, configs and networks reach files and networks this check does not read)")
            elif top == "volumes" and text.partition(":")[2].strip():
                bad.append(f"line {n}: `{text}` (top-level volumes must be a block of bare names)")
            continue
        if not in_services:
            # a top-level volume is a bare name (a volume of this trial only): `name:` / `external:` alias one volume
            # under two names (or name one that outlives the trial), `driver_opts:` binds a path
            if top == "volumes" and not (ind == 2 and re.match(r"""^['"]?[A-Za-z0-9_.-]+['"]?\s*:\s*(\{\s*\}|null|~)?$""", text)):
                bad.append(f"line {n}: top-level volume line `{text}` is not a bare name (no name:, external:, driver or driver_opts: a volume belongs to one trial and has one name)")
            continue
        if ind == 2:
            close(); in_vols = False
            m = re.match(r"""^['"]?([A-Za-z0-9_.-]+)['"]?\s*:\s*$""", text)
            if not m:
                bad.append(f"line {n}: `{text}` is not a service line"); svc = None; continue
            svc = m.group(1); out[svc] = {"keys": {}, "mounts": []}; first = True
            continue
        if svc is not None and first and ind != 4:      # a service whose keys sit deeper would be read as having none
            bad.append(f"line {n}: service {svc}: `{text}` at an unexpected indentation (a service's keys are indented 4 spaces)"); svc = None; continue
        first = False
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
                        if "$" in it: bad.append(f"line {n}: service {svc}: volume entry `{it}`: {VAR_RULE} (and in the block form)")
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
            if "$" in body:                          # ${RCB_VAR:?message with : in it}:/target -> a bind named by the runner
                m = re.match(r"^(\$\{[^}]*\})(?::(.*))?$", body)
                if m and RUNNER_DIR.match(m.group(1)) and "$" not in (m.group(2) or ""):
                    out[svc]["mounts"].append(("bind", m.group(1), m.group(2) or ""))
                else: bad.append(f"line {n}: service {svc}: volume entry `{body}`: {VAR_RULE}")
                continue
            src, _, rest = body.partition(":")
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
         "cgroup", "cgroup_parent", "userns_mode", "extends", "<<",
         "oom_kill_disable", "oom_score_adj", "memswap_limit", "sysctls", "runtime")   # around the declared caps (§2.10)
# A service with its own network setting is not routed through Harbor's egress control: the task's allowlist would not
# apply to it (harbor 0.23, docker.py _egress_controlled_service_names).
OWN_NETWORK = ("network_mode", "networks")
# Files of the task or the host handed to a container by another road than `volumes:`; `build` replaces Harbor's own
# build of main (context: environment/) or a sidecar's pinned image.
HANDS_FILES = ("secrets", "configs", "env_file", "build")
# the mode registry (PROTOCOL §2.16): RCB_MODES_TABLE from run_all.sh, "<mode> <sidecar 0|1> <twin>" longest first
import os
_table = os.environ.get("RCB_MODES_TABLE", "")
if not _table:
    sys.path.insert(0, str(root / "scripts")); import task_conventions as _tc; _table = _tc.modes_table()
_modes = [l.split() for l in _table.splitlines() if l.strip()]
mode = next((m for m, _s, _t in _modes if t.name.endswith("-" + m)), "")
sidecar_mode = any(m == mode and s == "1" for m, s, _t in _modes)
if env_c.is_file():
    services, bad = compose_services(env_c)
    for b in bad: fail(f"environment/docker-compose.yaml: {b} (ci_checks/check-verifier-isolation.sh reads no YAML: keep to the block form)")
    for svc, info in services.items():
        if svc == "rcb_monitor": continue
        for k in WIDEN:
            if k in info["keys"]: fail(f"service {svc}: `{k}` is not allowed (it widens the container beyond its own namespaces and files)")
        for k in OWN_NETWORK:
            if k in info["keys"]: fail(f"service {svc}: `{k}` is not allowed (Harbor's egress control skips a service with its own network setting: the allowlist would not apply; a sidecar is reached on localhost only, PROTOCOL §4.1)")
        for k in HANDS_FILES:
            if k in info["keys"]: fail(f"service {svc}: `{k}` is not allowed (it hands the container files of the task or the host outside `volumes:`, or replaces the pinned image)")
        if svc != "main":
            for k in ("ports", "expose"):
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
    if sidecar_mode:
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
    for svc, info in services.items():
        for k in WIDEN + HANDS_FILES:
            if k in info["keys"]: fail(f"tests/docker-compose.yaml: service {svc}: `{k}` is not allowed")
sys.exit(rc)
PY
