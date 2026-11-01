"""Verifier entry of a generated task (tools/generate.py copies this file to tests/grade.py and the Judge to
tests/eo_judge/): the Embodied Olympics Judge (framework/judge) on the match service's artifacts in RCB_DATA (/data),
writing verdict.json (eo-verdict/1), verdict_v0.json, reward.json and reward.txt to RCB_LOG (/logs/verifier).
Standard library only, no network."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from eo_judge.verifier import grade, main  # noqa: E402,F401  (grade: for callers of the core 0.3.0 grader)

if __name__ == "__main__":
    sys.exit(main(HERE))
