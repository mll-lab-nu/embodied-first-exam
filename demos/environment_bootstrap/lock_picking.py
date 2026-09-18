"""Run the new lock scene with the established physical qualification routine."""
import json
from pathlib import Path
import traceback

import hydra

from topogym.tasks.catalog import baseline_manifest
from topogym.tasks.lock_picking.scene import LockPickingSceneBuilder
from topogym.tasks.lock_picking.runner import run


@hydra.main(version_base="1.3", config_path="../../configs", config_name="lock_picking_baseline")
def main(cfg):
    output = Path(cfg.run.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "baseline_manifest.json").write_text(json.dumps(
        baseline_manifest("lock_picking", int(cfg.task.seed)), ensure_ascii=False, indent=2) + "\n")
    try:
        run(cfg, scene_builder=LockPickingSceneBuilder)
    except Exception as exc:
        (output / "failure.json").write_text(json.dumps({
            "task_id": "lock_picking", "passed": False,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
        }, indent=2) + "\n")
        raise


if __name__ == "__main__":
    main()
