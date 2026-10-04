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
    return run_stages(session, output, gravity_release_table_pickup_stages, selection=selection)
