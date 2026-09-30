"""Markdown comparison of evaluation outputs, one row per output directory, from results.jsonl only (so an
interrupted run is reported too). run_eval writes each output's row as report.md; to compare outputs:

    python -m vla.gym.report runs/test_results/<run> [...]
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

COLUMNS = ("model", "task", "success", "outcomes", "control Hz", "execute steps", "instruction",
           "control steps / episode", "inferences / episode", "tracking error", "clipped rows / episode",
           "wall min / episode")


def markdown_row(cells):
    return "| " + " | ".join(map(str, cells)) + " |"


def summary_row(rows):
    """Outcome counts and per-episode means of one output; run-level fields come from its first row. Rows written
    before tracking_error_unit existed are shown without a unit."""
    first, outcomes = rows[0], Counter(row["outcome"] for row in rows)
    errors = [row["tracking_error_mean"] for row in rows if row["tracking_error_mean"] is not None]

    def mean(values):
        return sum(values) / len(values)

    def episode_mean(key):
        return mean([row[key] for row in rows])

    return markdown_row([
        first["model"], first["task"], f'{outcomes["success"]}/{len(rows)}',
        ", ".join(f"{name} {count}" for name, count in sorted(outcomes.items())),
        f'{first["control_hz_actual"]:g}', first["execute_steps"], f'v{first["instruction_version"]}',
        f'{episode_mean("control_steps"):.0f}', f'{episode_mean("inference_calls"):.0f}',
        f'{mean(errors):.3g} {first.get("tracking_error_unit", "")}'.strip() if errors else "-",
        f'{episode_mean("clipped_actions"):.0f}', f'{episode_mean("rollout_wall_s") / 60:.1f}'])


def table(run_dirs):
    lines = [markdown_row(COLUMNS), markdown_row(["---"] * len(COLUMNS))]
    for directory in run_dirs:
        results = (Path(directory) / "results.jsonl").read_text().splitlines()
        lines.append(summary_row([json.loads(line) for line in results]))
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("runs", nargs="+", type=Path, help="evaluation output directories")
    print(table(parser.parse_args().runs))


if __name__ == "__main__":
    main()
