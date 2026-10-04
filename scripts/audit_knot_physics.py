#!/usr/bin/env python3
"""Audit every captured Knot physics tick without starting a simulator."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from topogym.planning.knot_untying.physics_audit import audit_capture  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True, help='physics_replay_NN directory')
    parser.add_argument('--output', type=Path, required=True, help='new audit directory')
    parser.add_argument('--workers', type=int, default=1, help='CPU measurement processes; tick order and checks are unchanged')
    args = parser.parse_args()
    result = audit_capture(args.capture, args.output, workers=args.workers)
    print(json.dumps(result, indent=2))
    return 0 if result['qualified'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
