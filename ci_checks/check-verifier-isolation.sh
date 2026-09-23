#!/usr/bin/env bash
# PROTOCOL §4: the verifier must run in its own sandbox, never in the container the agent controlled.
# task.toml: [verifier] environment_mode = "separate"; tests/Dockerfile exists, FROMs a pinned registry image and
# ships /tests/test.sh itself (Harbor does not upload tests/ into a dedicated verifier image).
t="$1"; rc=0
grep -Eq '^environment_mode *= *"separate"' "$t/task.toml" || { echo "FAIL $t: [verifier] environment_mode must be \"separate\""; rc=1; }
[ -f "$t/tests/Dockerfile" ] || { echo "FAIL $t: tests/Dockerfile missing (separate verifier image)"; rc=1; }
if [ -f "$t/tests/Dockerfile" ]; then
  from=$(grep -m1 '^FROM ' "$t/tests/Dockerfile" | awk '{print $2}')
  case "$from" in *@sha256:*|*/*:*) [[ "$from" == *:latest ]] && { echo "FAIL $t: tests/Dockerfile FROM uses :latest"; rc=1; } ;; *) echo "FAIL $t: tests/Dockerfile FROM '$from' must be a pinned registry image"; rc=1 ;; esac
  grep -q 'test.sh' "$t/tests/Dockerfile" || { echo "FAIL $t: tests/Dockerfile must COPY test.sh into /tests/"; rc=1; }
fi
exit $rc
