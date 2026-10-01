#!/usr/bin/env bash
# PROTOCOL §4: the verifier must run in its own sandbox, never in the container the agent controlled.
# task.toml: [verifier].environment_mode = "separate"; tests/Dockerfile exists, FROMs a pinned registry image and ships
# /tests/test.sh; any compose sidecar image is pinned. Agent egress is a run-time choice (scripts/set_agent_egress.py):
# public is allowed; if an allowlist is set it must list hosts (an empty allowlist breaks the agent's model API).
# PROTOCOL §2.6 adds two rules, because Harbor mounts /logs/verifier read-write into the agent's container and some
# simulators keep a cache of generated code:
# - tests/test.sh empties /logs/verifier before anything else (a planted reward.json must not survive a grader crash):
#   `rm -rf /logs/verifier/*`, or `find /logs/verifier -mindepth 1 ... -exec rm ...` (the form that keeps Harbor's
#   test-stdout.txt). A hard failure for tasks on protocol v1.0 (they declare `oracle` and no `tier`); tasks from before
#   the migration (PROTOCOL §7) get the same rule as a warning from check-protocol-v1.py.
# - no writable volume crosses the trust boundary: named volumes mounted by a trusted container (the verifier, a
#   standard task's sim sidecar) are *_trusted and never mounted by the agent's container. Every task.
t="$1"; python3 - "$t" <<'PY'
import sys, tomllib, pathlib, re
t = pathlib.Path(sys.argv[1]); rc = 0
def fail(m):
    global rc; print(f"FAIL {t}: {m}"); rc = 1
d = tomllib.load(open(t / "task.toml", "rb"))
if (d.get("verifier") or {}).get("environment_mode") != "separate": fail('[verifier].environment_mode must be "separate"')
ag = d.get("agent") or {}
if ag.get("network_mode") == "allowlist" and not ag.get("allowed_hosts"): fail('[agent] allowlist without allowed_hosts (the agent could not reach its model API)')
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

# test.sh clears /logs/verifier first (the same rule as check-protocol-v1.py)
meta = d.get("metadata") or {}
v1 = "oracle" in meta and "tier" not in meta
CLEAR_LOGS = re.compile(r"^(rm\s+-[rRf]+\s+/logs/verifier/\*|find\s+/logs/verifier\s+-mindepth\s+1\b.*(-delete|-exec\s+rm))")
sh = t / "tests/test.sh"
if v1 and sh.is_file():
    cmds = [ln.strip() for ln in sh.read_text().splitlines() if ln.strip() and not ln.strip().startswith("#")]
    cmds = [c for c in cmds if not re.match(r"(set\s|mkdir\s+-p\s+/logs/verifier\s*$)", c)]
    if not cmds or not CLEAR_LOGS.match(cmds[0]):
        fail("tests/test.sh must empty /logs/verifier before anything else (`rm -rf /logs/verifier/*`, or find ... -exec rm keeping test-stdout.txt)")


def named_volumes(compose: pathlib.Path) -> dict:
    """service -> named volumes it mounts (a bind mount starts with . / or $). Indentation-based, no YAML dependency."""
    out, svc, in_services, in_vols = {}, None, False, False
    for line in compose.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"): continue
        ind = len(line) - len(line.lstrip())
        if ind == 0:
            in_services = line.startswith("services:"); svc = None; continue
        if in_services and ind == 2 and line.strip().endswith(":"):
            svc = line.strip()[:-1]; in_vols = False; continue
        if svc and ind == 4:
            in_vols = line.strip() == "volumes:"; continue
        m = re.match(r"^\s+-\s+['\"]?([^:'\"\s]+):", line)
        if svc and in_vols and m and not m.group(1).startswith((".", "/", "$")):
            out.setdefault(svc, []).append(m.group(1))
    return out


env_c, test_c = t / "environment/docker-compose.yaml", t / "tests/docker-compose.yaml"
if env_c.is_file():
    for svc, vols in named_volumes(env_c).items():
        for v in vols:
            if svc == "main" and v.endswith("_trusted"): fail(f"the agent container mounts trusted volume {v}")
            if svc != "main" and not v.endswith("_trusted"): fail(f"sidecar {svc} mounts {v}, which is not a *_trusted volume")
if test_c.is_file():
    for v in named_volumes(test_c).get("main", []):
        if not v.endswith("_trusted"): fail(f"the verifier mounts {v}, which is not a *_trusted volume")
sys.exit(rc)
PY
