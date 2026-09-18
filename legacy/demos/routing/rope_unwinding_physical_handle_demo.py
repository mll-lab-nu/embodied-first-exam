"""Take a FEM rope OFF a post by physically grasping the plug on its free end.

Task book 2.5 (start_turns -> 0), the mirror of rope_winding: the rope spawns
already wound `task.winding.start_turns` times around the post, its anchor end
pinned at the terminal and its plug lying on the board. The oracle lifts the
plug to the height of the top wrap and orbits AGAINST the wrap, descending one
wrap per turn, until the winding number reads 0, then sets the plug down on C.
Orbiting the wrong way (`task.winding.orbit_direction=ccw` on a ccw wrap) takes
the count to 2 * start_turns instead, which is the task's contrast pair.

Everything but the entry point is `rope_winding_physical_handle_demo`: same
grasp, same attachment, same probes, same verdict. Configuration is Hydra
(`configs/rope_unwinding.yaml`).

    python -m demos.routing.rope_unwinding_physical_handle_demo run.viewer=true run.probe=true
    python -m demos.routing.rope_unwinding_physical_handle_demo task.winding.start_turns=2
    python -m demos.routing.rope_unwinding_physical_handle_demo task.winding.orbit_direction=ccw
"""

from __future__ import annotations

import sys
from pathlib import Path

import hydra
from omegaconf import DictConfig

# `demos` is a namespace package: importable from the repo root under
# `python -m`, but not when this file is run by path.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from demos.routing.rope_winding_physical_handle_demo import run_from_config  # noqa: E402
from topogym.tasks_legacy import RopeUnwindingSceneBuilder  # noqa: E402


@hydra.main(version_base="1.3", config_path="../../configs", config_name="rope_unwinding")
def main(cfg: DictConfig) -> None:
    run_from_config(cfg, scene_builder=RopeUnwindingSceneBuilder)


if __name__ == "__main__":
    main()
