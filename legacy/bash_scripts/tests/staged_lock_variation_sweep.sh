#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
task_python="${TOPOGYM_PYTHON:-.venv-gs121-nyx/bin/python}"
task_sweep_root="${TOPOGYM_LOCK_SWEEP_ROOT:-runs/staged_lock_task/sweep_free_key}"
variants=("$@")
if [ "$#" -eq 0 ]; then variants=(reindexed asymmetric tight_clearance); fi
for variant in "${variants[@]}"; do
  "$task_python" -m demos.connectivity.staged_lock_physical_demo \
    --config-name staged_lock_policy_views env.renderer.type=rasterizer \
    "task.variant=$variant" task.seed=3 recording.enabled=false \
    "run.output=${task_sweep_root}/${variant}_3"
done
# A failed blind insertion must remain a failed run, with an actual blocking
# contact. Capture its exit status and inspect its result rather than ignoring it.
if "$task_python" -m demos.connectivity.staged_lock_physical_demo \
    --config-name staged_lock_policy_views env.renderer.type=rasterizer \
    run.oracle_mode=blind recording.enabled=false \
    "run.output=${task_sweep_root}/blind"; then
  echo 'ERROR: blind fixed-angle policy unexpectedly succeeded' >&2
  exit 1
fi
"$task_python" - "$task_sweep_root" "${variants[@]}" <<'PY'
import json,sys
from pathlib import Path
root=Path(sys.argv[1])
names=[f'{variant}_3' for variant in sys.argv[2:]]+['blind']
results={name:json.loads((root/name/'report.json').read_text()) for name in names}
for variant in sys.argv[2:]:
    assert results[f'{variant}_3']['success'],variant
    assert results[f'{variant}_3']['initial_support']['weight_supported'],variant
    assert results[f'{variant}_3']['initial_support']['key_dofs']==6,variant
    for group in ('arm_framing','mechanism_framing'):
        assert all(v['all_visual_vertices_in_frame'] for v in results[f'{variant}_3'][group].values()),variant
    assert results[f'{variant}_3']['wrist_up_z_min_during_grasp']>0,variant
blind=results['blind']
assert not blind['success']
assert .8 < blind['state']['depth'] < 1.1,blind
assert blind['force_limit_triggered'],blind
assert blind['decisions'][0]['level']==1,blind
assert blind['max_contact_penetration'] < .002,blind
(root/'summary.json').write_text(json.dumps({k:{field:v[field] for field in
    ('success','state','max_contact_penetration','max_key_fixture_contact_force',
     'force_limit_triggered','geometry_error_steps','arm_framing',
     'mechanism_framing','wrist_up_z_min_during_grasp')}
    for k,v in results.items()},indent=2)+'\n')
print(f'{len(sys.argv)-2} generated variants succeeded; fixed-angle baseline was physically blocked.')
PY
