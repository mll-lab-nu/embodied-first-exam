"""Existing full Horseshoe stage factory with hash-bound recipe inputs."""
import json
from topogym.planning.harbor_bridge.callbacks import data_path, run_stages
from .stages import gravity_release_table_pickup_stages


def run_feedback_policy(session, output, *, variation):
    recipe = json.loads(data_path(f"horseshoe_ring/{variation}/recipe.json").read_text())
    task = session.env._task
    if (task.model_revision != recipe["model_revision"] or task.terminal_revision != recipe["terminal_revision"]
            or task.resource_hashes != recipe["resource_sha256"]):
        raise ValueError("Frozen Horseshoe model or terminal differs from the reference recipe")
    selection = recipe["selection"]
    for name, item in selection[0]["parameters"].items():
        item["path"] = str(data_path(f"horseshoe_ring/{variation}/{name}.json"))
    # oraclefix2 O2-6: every recorded row within the standard service's per-step joint limit, so the privileged
    # reference is standard-executable as recorded. Clamp mode keeps each row's control step: hard's fold asked once
    # for 0.0408 rad (row 3397), and an inserted step shifts the closed-loop run after it (lab oraclefix2/exp/X11).
    from topogym.planning.standard_rate import rate_limited_runner
    return run_stages(session, output, gravity_release_table_pickup_stages, selection=selection,
                      runner=rate_limited_runner(session, mode="clamp"))
