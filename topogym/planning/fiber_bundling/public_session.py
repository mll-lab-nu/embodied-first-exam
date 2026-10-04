"""Existing three-tier Fiber stages and selected parameters in a bound Session."""
import json
from topogym.planning.harbor_bridge.callbacks import data_path, run_stages
from .stages import stages


def run_feedback_policy(session, output, *, variation):
    selection = json.loads(data_path(f"fiber_bundling/{variation}/selection.json").read_text())
    return run_stages(session, output, stages, selection=selection)
