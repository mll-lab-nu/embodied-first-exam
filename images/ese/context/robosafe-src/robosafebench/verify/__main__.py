"""Verify a record without importing the development CLI or model-facing tools."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from robosafebench.verify import verify


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", type=Path)
    parser.add_argument("--json", action="store_true", help="write compact JSON (the default is indented JSON)")
    args = parser.parse_args(argv)
    verdict = verify(json.loads(args.record.read_text()))
    print(json.dumps(verdict, default=str, indent=None if args.json else 1))
    # A failing benchmark verdict is still a successful verification, as in the development CLI.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
