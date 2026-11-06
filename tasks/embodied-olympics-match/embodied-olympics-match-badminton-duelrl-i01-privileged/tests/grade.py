"""This duel twin's verifier entrypoint: the generic privileged grader (/tests/grade_generic.py: the files image's
privileged/tests/grade.py, unchanged) with tools.fullsim.duel.evaluate (the generic evaluation plus the built-in seat B
of the twin) in place of tools.fullsim.formal.evaluate. Trusted; never imports submitted code."""

import runpy
import sys

sys.path.insert(0, "/opt/trusted")
from tools.fullsim import duel, formal  # noqa: E402

formal.evaluate = duel.evaluate
runpy.run_path("/tests/grade_generic.py", run_name="__main__")
