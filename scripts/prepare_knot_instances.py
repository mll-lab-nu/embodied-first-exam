#!/usr/bin/env python3
"""Rebuild knot frozen instances and optional no-RGB development copies outside tasks/."""
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from topogym.planning.knot_untying.artifacts import task_dir
from topogym.planning.knot_untying.cli import freeze_sources, supervise
from topogym.utils.io import write_json_atomic


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--variations", choices=("easy", "medium", "hard"), nargs="+", default=["easy", "medium", "hard"])
    p.add_argument("--output", type=Path, required=True, help="new directory, outside tasks/")
    p.add_argument("--seed", type=int, default=0)
    a = p.parse_args()
    out = a.output.resolve()
    if out.is_relative_to(ROOT/"tasks"):
        p.error("write rebuilt instances to runs/, leaving benchmark task packages unchanged")
    out.mkdir(parents=True, exist_ok=False)
    source = freeze_sources(out)
    for tier in dict.fromkeys(a.variations):
        folder = out/tier
        folder.mkdir()
        state = folder/"instance_assets/ipc_state"
        state.parent.mkdir()
        tooling = source/(task_dir("knot_untying_"+tier)/"environment/rcb_topogym.py").relative_to(ROOT)
        base = ["--task", "knot_untying", "--variation", "knot_untying_"+tier, "--scene-seed", str(a.seed)]
        stages = [("export", ["export-ipc-state", *base, "--out", str(state)]),
                  ("freeze", ["make-instance", *base, "--ipc-settled-state", str(state/"manifest.json"),
                              "--out", str(folder/"instance.json")])]
        for name, args in stages:
            logs = folder/name; logs.mkdir()
            command = [sys.executable, str(tooling), *args]
            write_json_atomic(logs/"command.json", command)
            code = supervise(command, logs, source)
            if code:
                return code
        instance = json.loads((folder/"instance.json").read_text())
        instance["simulator"].update(enable_rgb=False, enable_depth=False)
        write_json_atomic(folder/"instance_norgb.json", instance)
        print(f"Prepared {tier}: {folder/'instance.json'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
