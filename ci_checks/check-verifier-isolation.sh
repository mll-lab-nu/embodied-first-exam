#!/usr/bin/env bash
# PROTOCOL §4: the verifier must run in its own sandbox, never in the container the agent controlled.
# task.toml: [verifier].environment_mode = "separate"; tests/Dockerfile exists, FROMs a pinned registry image and ships
# /tests/test.sh; any compose sidecar image is pinned. Agent egress is a run-time choice (scripts/set_agent_egress.py):
# public is allowed; if an allowlist is set it must list hosts (an empty allowlist breaks the agent's model API).
# Two more rules, because Harbor mounts /logs/verifier read-write into the agent's container and some simulators keep a
# cache of generated code: tests/test.sh empties /logs/verifier before grading (a planted reward.json must not survive a
# grader crash), and no writable volume crosses the trust boundary — named volumes mounted by a trusted container (the
# verifier, a limited task's sim sidecar) are *_trusted and never mounted by the agent's container.
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
sh = t / "tests/test.sh"
if not sh.is_file() or "find /logs/verifier -mindepth 1 -maxdepth 1 ! -name test-stdout.txt -exec rm -rf {} +" not in sh.read_text():
    fail("tests/test.sh must empty /logs/verifier (all but test-stdout.txt) before grading")


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
