#!/bin/bash
# Verifier (separate sandbox, no network): the API test of the delivered skill on the development requests
# (skilleval: each request from its recorded start state in the full simulation, the skill in its own process as nobody).
mkdir -p /logs/verifier
rm -rf /logs/verifier/*
trap 'p=$(command -v python3 || command -v python); "$p" /tests/rcb_limits.py verify' EXIT   # resource limits, after the grader (docs/PROTOCOL.md §2.10)
p=$(command -v python3 || command -v python); "$p" /tests/rcb_limits.py sanitize /app/output || true   # the agent's files are untrusted input: no link out of /app/output, no FIFO or device (docs/PROTOCOL.md §2.6)
# the sandbox needs root (the skill runs as nobody, the simulator directory and the report are root-only): a verifier
# started as another user (e.g. a rootless container runtime) cannot grade, which is the infrastructure's failure
if [ "$(id -u)" != 0 ]; then
  echo "verifier must run as root (uid $(id -u)): the skill runs as nobody in a root-only sandbox" > /logs/verifier/evaluate.log
  echo '{"success": 0, "infra_error": 1, "grader_error": 0, "verifier_not_root": 1}' > /logs/verifier/reward.json
  echo 0 > /logs/verifier/reward.txt
  exit 0
fi
# the skill runs as nobody: it must not reach the log directory (Harbor makes it 777) nor the report the grade is read from
chmod 755 /logs/verifier
install -d -m 700 -o root -g root /var/lib/skilleval && rm -f /var/lib/skilleval/report.json
cd /srv/sim && MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa HOME=/tmp python3 -B -m skilleval.evaluate --sport-dir /srv/sim/sport \
  --impl skill --skill /app/output/skill --set hidden --no-competition --label player \
  --isolation "Harbor separate verifier, no network; the skill as nobody in its own process" \
  --out /var/lib/skilleval/report.json > /logs/verifier/evaluate.log 2>&1
# after every process of nobody is gone (engineer_grade.py ends any left, then reads the root-only report)
python3 /tests/engineer_grade.py 0.8 246 /var/lib/skilleval/report.json 2>> /logs/verifier/evaluate.log
