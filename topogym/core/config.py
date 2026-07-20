from __future__ import annotations

from pathlib import Path

from omegaconf import OmegaConf


CONFIG_ROOT = Path(__file__).resolve().parents[2] / "configs"
DEFAULT_COMMON_CONFIG = CONFIG_ROOT / "common_configs" / "manipulation_space_tabletop_v1.yaml"
DEFAULT_PREFAB_CONFIG = CONFIG_ROOT / "prefab_configs" / "topogym_prefabs_v1.yaml"


def add_common_config_arg(parser, *, default: Path = DEFAULT_COMMON_CONFIG) -> None:
    """Add the shared manipulation-space config flag used by prototype demos."""

    parser.add_argument(
        "--common-config",
        type=Path,
        default=default,
        help="Shared manipulation-space config with board, workspace, and robot setup defaults.",
    )


def load_topogym_configs(
    *,
    common_config: Path = DEFAULT_COMMON_CONFIG,
    env_config: Path,
    robot_config: Path,
    task_config: Path | None = None,
    prefab_config: Path = DEFAULT_PREFAB_CONFIG,
):
    """Load the standard TopoGym config stack.

    The returned root contains ``common``, ``env``, ``robot_control``,
    ``prefabs`` (shared parameter single-sources such as the PBD rope, see
    ``configs/prefab_configs/``), and optionally ``task``. Config files may use
    OmegaConf interpolations that reference values across these sections
    (e.g. ``${prefabs.rope_pbd.radius}``).
    """

    sections = {
        "common": OmegaConf.load(common_config),
        "env": OmegaConf.load(env_config),
        "robot_control": OmegaConf.load(robot_config),
        "prefabs": OmegaConf.load(prefab_config),
    }
    if task_config is not None:
        sections["task"] = OmegaConf.load(task_config)
    return OmegaConf.create(sections)
