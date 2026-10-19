"""`python -m embodied_safety_exam.diagnose` is `python -m embodied_safety_exam diagnose`."""
import argparse
import sys

from embodied_safety_exam.diagnose import run

ap = argparse.ArgumentParser(prog="python -m embodied_safety_exam.diagnose", description=run.__doc__.split("\n\n")[0])
run.add_arguments(ap)
sys.exit(run.main(ap.parse_args()))
