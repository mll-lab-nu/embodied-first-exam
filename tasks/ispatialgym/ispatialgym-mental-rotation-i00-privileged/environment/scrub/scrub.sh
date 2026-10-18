#!/bin/sh
# The privileged agent's layer on eai-ispatialgym (docs/benchmarks/ispatialgym.md, docs/protocol/leakage.md §1, §3): the agent shares this
# container with the simulator and may read every file in it (PROTOCOL §5), so what states the task or points to its
# solution goes, the simulator still loads the frozen start, and the build fails if anything survived.
#   scrub.sh <this task's BDDL problem in the image>
# 1. this task's start-only BDDL problem (neutral_bddl.py) from the image's own copy, into /opt/tools/activity_definitions;
# 2. removed: every BDDL problem (they state the goals); the docs (demos.md previews the reference demonstrations; the
#    fork's docs link the authors' pages), tests, configs, README and setup.sh; the eval data's repository id and its
#    datasets' names in eval/instances.py and run_isg.py, the project URLs and the README the package metadata carries
#    (they locate the dataset that holds the demonstrations); every bytecode cache;
# 3. asserted: none of it is left, no scripted expert, sampler, task spec or eval-data file is in the image (the public
#    release ships none), nothing under /app, /opt/tools, iSpatialGym or the fork names a target, the eval data or a
#    URL to it, the start-only problem states no role or variant, and the tooling imports.
# The names this looks for are read from the image itself (eval/instances.py), so that no file of the task names them.
set -eu
ISG=/opt/ispatialgym
SP=/opt/conda/envs/behavior/lib/python3.11/site-packages
fail() { echo "scrub.sh: $1" >&2; exit 1; }
INSTPY=$ISG/ispatialgym/eval/instances.py
HFID=$(sed -n 's/^HF_REPO_ID = "\([^"]*\)".*/\1/p' "$INSTPY")
[ -n "$HFID" ] || fail "no HF_REPO_ID in eval/instances.py: upstream changed, review this layer"
OWNER=${HFID%%/*}; DATA_NAME=${HFID#*/}; PREFIX=${DATA_NAME%-*}-     # the eval data's owner; its datasets' common prefix
find $ISG -name __pycache__ -prune -exec rm -rf {} +
python "$(dirname "$0")/neutral_bddl.py" "$1" /opt/tools/activity_definitions
rm -rf $ISG/ispatialgym/assets/bddl $ISG/docs $ISG/tests $ISG/configs $ISG/README.md $ISG/setup.sh /behavior-src/docs
sed -i 's|^HF_REPO_ID = .*|HF_REPO_ID = None  # removed in the privileged agent'"'"'s image: it names the dataset of the demonstrations|' "$INSTPY"
sed -i "s|${PREFIX}demos|demos|g; s|${PREFIX}instances|instances|g" "$INSTPY" $ISG/ispatialgym/run_isg.py
sed -i -E '/^(Repository|Dataset) = "https?:/d' $ISG/pyproject.toml
for f in $ISG/ispatialgym.egg-info/PKG-INFO $SP/ispatialgym-*.dist-info/METADATA; do
    [ -f "$f" ] && awk 'NF == 0 {exit} !/^Project-URL:/' "$f" > "$f.new" && mv "$f.new" "$f"   # the headers; the body is the README
done
[ -z "$(find / -xdev -name 'problem*.bddl' -path '*ispatialgym*' -not -path '/opt/tools/*' 2>/dev/null)" ] || fail "an iSpatialGym BDDL problem is left"
! grep -rlqF '(:domain ispatialgym)' $ISG /behavior-src /data/ispatialgym-assets /app 2>/dev/null || fail "an iSpatialGym BDDL problem is left"
[ -z "$(find $ISG -name '*.pyc')" ] || fail "bytecode is left"
for d in $ISG/ispatialgym/oracle $ISG/ispatialgym/sampling $ISG/ispatialgym/generation $ISG/ispatialgym/assets/task_specs; do
    [ ! -e "$d" ] || fail "$d is in the image (a scripted expert, sampler or task spec)"
done
[ -z "$(find $ISG /behavior-src /data /app /opt/tools -xdev \( -name '*.oracle.json' -o -name '*-tro_state.json' -o -name '*goal_rgb*' \
        -o -name 'instances.jsonl' -o -name 'episodes.jsonl' \) 2>/dev/null)" ] || fail "an eval-data or expert file is in the image"
! grep -rIlqE "https?://|$OWNER|$PREFIX" $ISG $SP/ispatialgym-*.dist-info /app /opt/tools \
    || fail "a URL or the eval data's name is left"
! grep -rIlqE "$OWNER|$PREFIX" /behavior-src || fail "the fork names the eval data"
! grep -rlqE '"(pose_targets|articulation_targets|goal_observation|task_variant)"' /app /opt/tools || fail "a target field is in the agent's files"
! grep -rlqE '"(target|targets|partner|distractors|source|destination|obstacles)_[a-z0-9_]+_[0-9]+"' /app /opt/tools || fail "a role name is in the agent's files"
! grep -rlqiE 'target|partner|distractor|obstacle|variant|;' /opt/tools/activity_definitions || fail "the start-only problem states a role or the variant"
cd /tmp && PYTHONPATH=/opt/tools python -c "import rcb_ispatialgym, ispatialgym.eval.loader" || fail "the tooling does not import"
