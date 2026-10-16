#!/bin/bash
# Run on a normal Docker-enabled machine. No model/API credentials are used.
set -euo pipefail
if [ "$#" -ne 2 ]; then
  echo "Usage: bash accept.sh TASKS_DIR NEW_OUTPUT_DIR" >&2
  exit 2
fi
tasks_dir=$(realpath "$1")
accept_out=$(realpath -m "$2")
if [ -e "$accept_out" ]; then echo "Output directory already exists: $accept_out" >&2; exit 2; fi
command -v docker >/dev/null
command -v harbor >/dev/null
docker info >/dev/null
harbor --version
mkdir -p "$accept_out"
for task in ${RCB_ACCEPT_TASKS:-roboolympics-tabletennis-match-i01-privileged roboolympics-tabletennis-match-i02-privileged}; do
  docker build --tag "tt-fullsim-dev:$task" "$tasks_dir/$task/environment"
  docker build --tag "tt-fullsim-verify:$task" "$tasks_dir/$task/tests"
  # Verify the verifier image's static privilege boundary independently of the policy.
  docker run --rm --network none "tt-fullsim-verify:$task" python -c '
import os
from pathlib import Path
assert os.geteuid() == 0
assert Path("/opt/trusted").stat().st_mode & 0o777 == 0o700
os.setgroups([]); os.setgid(65534); os.setuid(65534)
assert Path("/opt/dev/tools/tt_fullsim/session.py").read_text()
try:
    Path("/opt/trusted/tools/tt_fullsim/formal.py").read_text()
except PermissionError:
    pass
else:
    raise SystemExit("FAIL: nobody can read trusted code")
try:
    Path("/opt/dev/pollution").write_text("bad")
except PermissionError:
    pass
else:
    raise SystemExit("FAIL: nobody can modify the dev image")
print("root-private referee and read-only public dev tree: OK")'
  for agent in nop oracle; do
    job="$task-$agent"
    harbor run -y -p "$tasks_dir" -i "$task" -a "$agent" -n 1 -o "$accept_out" --job-name "$job"
    python3 - "$accept_out/$job" "$agent" <<'PY'
import json
import sys
from pathlib import Path
job, agent = Path(sys.argv[1]), sys.argv[2]
trials = []
for path in job.rglob("result.json"):
    obj = json.loads(path.read_text())
    if "trial_name" in obj:
        trials.append(obj)
assert len(trials) == 1, f"expected one native Harbor trial, got {len(trials)}"
t = trials[0]
assert not t.get("exception_info"), t.get("exception_info")
r = (t.get("verifier_result") or {}).get("rewards")
assert r is not None, "missing verifier rewards"
assert r.get("infra_error") == 0, r
assert r.get("isolation_checked") == 1, r
if agent == "nop":
    assert r.get("success") == 0 and r.get("policy_error") == 1, r
else:
    assert r.get("valid") == 1 and r.get("deterministic") == 1 and r.get("replays") == 2, r
    # Metadata is partial oracle: a valid replayed loss is reported, never silently promoted to full oracle.
    print("oracle success:", r.get("success"))
print(agent, "acceptance passed", r)
PY
  done
done
printf '%s\n' 'Both tasks built; container boundary, native Harbor nop and oracle checks passed.'
