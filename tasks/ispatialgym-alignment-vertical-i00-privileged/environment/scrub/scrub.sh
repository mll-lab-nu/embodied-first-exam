#!/bin/sh
# The privileged agent's layer on eai-ispatialgym (docs/benchmarks/ispatialgym.md, LEAKAGE §1, §3): the agent shares this
# container with the simulator and may read every file in it (PROTOCOL §5), so what states the task or points to its
# solution goes, the simulator still loads the frozen start, and the build fails if anything survived.
#   scrub.sh <this task's BDDL problem in the image>
# 1. this task's start-only BDDL problem (neutral_bddl.py) from the image's own copy, into /opt/tools/activity_definitions;
# 2. removed: every BDDL problem (they state the goals); the docs (demos.md previews the reference demonstrations), tests,
#    configs, README and setup.sh; the dataset's name in eval/instances.py, the project URLs and the README the package
#    metadata carries (they locate the dataset that holds the demonstrations); every bytecode cache;
# 3. asserted: none of it is left, nothing under /app, /opt/tools or iSpatialGym names a target, a URL or the dataset,
#    and the tooling imports.
set -eu
ISG=/opt/ispatialgym
find $ISG -name __pycache__ -prune -exec rm -rf {} +
python "$(dirname "$0")/neutral_bddl.py" "$1" /opt/tools/activity_definitions
rm -rf $ISG/ispatialgym/assets/bddl $ISG/docs $ISG/tests $ISG/configs $ISG/README.md $ISG/setup.sh
sed -i 's|^HF_REPO_ID = .*|HF_REPO_ID = None  # removed in the privileged agent'"'"'s image: it names the dataset of the demonstrations|' \
    $ISG/ispatialgym/eval/instances.py
sed -i -E '/^(Repository|Dataset) = "https?:/d' $ISG/pyproject.toml
for f in $ISG/ispatialgym.egg-info/PKG-INFO /opt/conda/envs/behavior/lib/python3.11/site-packages/ispatialgym-*.dist-info/METADATA; do
    [ -f "$f" ] && awk 'NF == 0 {exit} !/^Project-URL:/' "$f" > "$f.new" && mv "$f.new" "$f"   # the headers; the body is the README
done
fail() { echo "scrub.sh: $1" >&2; exit 1; }
[ -z "$(find / -xdev -name 'problem*.bddl' -path '*ispatialgym*' 2>/dev/null)" ] || fail "an iSpatialGym BDDL problem is left"
[ -z "$(find $ISG -name '*.pyc')" ] || fail "bytecode is left"
! grep -rIlqE 'https?://|ispatialgym-eval-data|kmy17518' $ISG /opt/conda/envs/behavior/lib/python3.11/site-packages/ispatialgym-*.dist-info /app /opt/tools \
    || fail "a URL or the dataset's name is left"
! grep -rlqE '"(pose_targets|articulation_targets|goal_observation|task_variant)"' /app /opt/tools || fail "a target field is in the agent's files"
! grep -rlqE '"(target|targets|partner|distractors|source|destination|obstacles)_[a-z]+_[a-z0-9]+_[0-9]+"' /app || fail "a role name is in the instance"
cd /tmp && PYTHONPATH=/opt/tools python -c "import rcb_ispatialgym, ispatialgym.eval.loader" || fail "the tooling does not import"
