#!/usr/bin/env bash
# PROTOCOL §4: the verifier must run in its own sandbox, never in the container the agent controlled.
# task.toml: [verifier].environment_mode = "separate"; tests/Dockerfile exists, FROMs a pinned registry image and ships
# /tests/test.sh; any compose sidecar image is pinned. Agent egress is a run-time choice (scripts/set_agent_egress.py):
# public is allowed; if an allowlist is set it must list hosts (an empty allowlist breaks the agent's model API).
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
sys.exit(rc)
PY
