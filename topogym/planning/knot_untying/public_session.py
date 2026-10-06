"""Run the existing knot decision algorithm without owning Session lifecycle."""
from pathlib import Path
from types import SimpleNamespace
from topogym.planning.harbor_bridge.callbacks import prepare_output
from .robot_oracle import Runner


def run_feedback_policy(session, output, *, variation):
    output = prepare_output(session, output, __file__)
    args = SimpleNamespace(variation="knot_untying_" + variation, instance=Path("/app/instance.json"),
        output=output, close=.005, end_offset=.035, full_pull=variation == "hard",
        max_pull=.55 if variation == "hard" else .6, speed=.04, max_decisions=16, settle=10.)
    if variation in {'very_easy', 'easier'}:
        from .below_easy_runner import BelowEasyRunner
        return BelowEasyRunner(args, session=session).run()
    return Runner(args, session=session).run()
