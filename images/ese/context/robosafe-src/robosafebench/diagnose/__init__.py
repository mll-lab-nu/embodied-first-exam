"""After the trials: why did a hazard trial fail? (docs/DIAGNOSE.md)

`named` (the agent's own text names the evidence), a post-trial probe of the model in a fresh context, one label per
failed hazard trial, and the family flag `suspect_twin`. Runs outside the robot service, on records and verdicts.

    python -m robosafebench diagnose JOBS --index TASKS/index.json --out DIR [--probe auto] [--limit N]
    python -m robosafebench diagnose flip --source JOBS INDEX LABEL [--source ...] [--out FILE.md]
"""
from robosafebench.diagnose.labels import LABELS, RULES, label, suspect_twins  # noqa: F401
from robosafebench.diagnose.run import diagnose, probe_scenes  # noqa: F401
