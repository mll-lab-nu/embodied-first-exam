"""This turn-based twin's verifier entrypoint: the generic privileged grader (/tests/grade_generic.py: the files image's
privileged/tests/grade.py, unchanged) with tools.fullsim.turn.evaluate (the formal bout on the twin's own TurnService)
in place of tools.fullsim.formal.evaluate. Trusted; never imports submitted code."""

import runpy
import sys

sys.path.insert(0, "/opt/trusted")
from tools.fullsim import formal, turn  # noqa: E402

formal.evaluate = turn.evaluate
runpy.run_path("/tests/grade_generic.py", run_name="__main__")
