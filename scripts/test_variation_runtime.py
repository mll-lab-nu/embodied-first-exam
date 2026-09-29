#!/usr/bin/env python3
"""Run implemented tiers through the existing Nyx lifecycle/video acceptance."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from topogym.config.registry import task_catalog, variation_catalog
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tasks", nargs="+", default=[r["task_id"] for r in task_catalog()])
    parser.add_argument("--tiers", nargs="+", choices=("easy", "medium", "hard"), default=["easy", "medium", "hard"])
    parser.add_argument("--steps", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=1800)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    report = dict(scope="Nyx lifecycle checks; not complete task solutions",
                  started_at_utc=datetime.now(timezone.utc).isoformat(), results=[])
    for task in args.tasks:
        for row in variation_catalog(task):
            if row["difficulty"] not in args.tiers:
                continue
            name = row["variation_id"]
            command = [sys.executable, str(ROOT/"scripts/test_base_tasks.py"), "--tasks", task,
                       "--variation", name, "--checks", "base", "--steps", str(args.steps),
                       "--timeout", str(args.timeout), "--output", str(args.output.resolve()/name)]
            item = dict(variation_id=name, command=command, status="pending")
            if row["status"] != "integrated":
                item.update(status="unavailable", reason=row["reason"])
            elif args.dry_run:
                item["status"] = "not_run"
            else:
                result = subprocess.run(command, cwd=ROOT, env=os.environ.copy(), check=False)
                item.update(status="passed" if result.returncode == 0 else "failed", exit_code=result.returncode)
            report["results"].append(item)
            (args.output/"summary.json").write_text(json.dumps(report, indent=2)+"\n")
            print(name, item["status"], flush=True)
    return int(any(r["status"] == "failed" for r in report["results"]))


if __name__ == "__main__":
    raise SystemExit(main())
