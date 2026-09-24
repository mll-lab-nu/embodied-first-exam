#!/usr/bin/env bash
# PROTOCOL §4: the verifier must run in its own sandbox, never in the container the agent controlled, and the agent
# must not have open egress (it could fetch the scrubbed reference solutions from the public upstream repos).
# task.toml: [verifier].environment_mode = "separate"; [agent].network_mode in {allowlist, no-network};
# tests/Dockerfile exists, FROMs a pinned registry image and ships /tests/test.sh; any compose sidecar image is pinned.
t="$1"; python3 - "$t" <<'PY'
import sys, tomllib, pathlib, re
t = pathlib.Path(sys.argv[1]); rc = 0
def fail(m):
    global rc; print(f"FAIL {t}: {m}"); rc = 1
d = tomllib.load(open(t / "task.toml", "rb"))
if (d.get("verifier") or {}).get("environment_mode") != "separate": fail('[verifier].environment_mode must be "separate"')
if (d.get("agent") or {}).get("network_mode") not in ("allowlist", "no-network"): fail('[agent].network_mode must be "allowlist" or "no-network" (agent egress leaks the scrubbed solutions)')
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
sys.exit(rc)
PY
