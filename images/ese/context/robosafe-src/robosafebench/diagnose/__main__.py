"""`python -m robosafebench.diagnose` is `python -m robosafebench diagnose`."""
import argparse
import sys

from robosafebench.diagnose import run

ap = argparse.ArgumentParser(prog="python -m robosafebench.diagnose", description=run.__doc__.split("\n\n")[0])
run.add_arguments(ap)
sys.exit(run.main(ap.parse_args()))
