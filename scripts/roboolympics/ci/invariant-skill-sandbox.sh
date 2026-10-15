#!/usr/bin/env bash
# INVARIANT hook (docs/PROTOCOL.md Appendix H.1: code the verifier runs for the agent is sandboxed): RoboOlympics' skill
# tasks run the agent's skill in the verifier; its test shows that a detached process of the skill is ended before
# anything is graded. Run by ci_checks/run_invariants.sh (the task dirs it is given are not needed).
set -euo pipefail
exec python3 "$(cd "$(dirname "$0")/.." && pwd)/tests/test_skill_sandbox.py"
