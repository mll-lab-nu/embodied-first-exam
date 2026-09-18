"""Does every config still compose, with every interpolation resolvable?

Composes each `configs/task_configs/*.yaml` and each demo's primary config through
Hydra, then resolves the whole tree. Two things fail here:

- a config group option that does not exist, or a `defaults` entry whose
  `group@package` key is wrong;
- an interpolation pointing at a key that is not there -- `${prefabs.rope_fem.E}`,
  `${task.physical_handle.handle_friction}` and friends. `OmegaConf.to_container`
  with `resolve=True` is what forces them; loading alone does not.

    python tests/check_configs_compose.py
    python tests/check_configs_compose.py --task swap_topogym_tabletop_v1

Exits non-zero if anything fails to compose or resolve, so it can gate a commit.

History: this replaces `check_hydra_compose_equivalence.py`, which compared Hydra's
result against `load_topogym_configs`. That function was deleted on 2026-08-10 with
the rest of the argparse config path, leaving nothing to compare against. The
compose-and-resolve half is what still has value, so only that half was kept.

Requires the `hydra-core` package, so it runs in the project venv only. The checks
that need no dependencies are in `tests/check_demo_configs.py`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
# The repo is not an installed package -- demos work because `python -m` from the
# repo root puts it on the path. A script run by path does not get that.
sys.path.insert(0, str(REPO))

from hydra import compose, initialize_config_dir  # noqa: E402
from omegaconf import OmegaConf  # noqa: E402

CONFIGS = REPO / "configs"
SECTIONS = ("common", "env", "robot_control", "prefabs", "task", "recording", "run")


def _count_keys(node) -> int:
    if isinstance(node, dict):
        return sum(1 + _count_keys(v) for v in node.values())
    if isinstance(node, list):
        return sum(_count_keys(v) for v in node)
    return 0


def check(label: str, config_name: str, overrides: list[str]) -> bool:
    try:
        with initialize_config_dir(version_base="1.3", config_dir=str(CONFIGS)):
            cfg = compose(config_name=config_name, overrides=overrides)
        resolved = OmegaConf.to_container(cfg, resolve=True)
    except Exception as error:  # noqa: BLE001 -- the message is the whole point
        print(f"{label:<46}失败")
        print(f"    {type(error).__name__}: {error}")
        return False

    missing = [s for s in SECTIONS if s not in resolved]
    if missing:
        print(f"{label:<46}缺节  {missing}")
        return False
    print(f"{label:<46}通过  ({_count_keys(resolved)} 个键)")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--task", default=None, help="Only this task config stem.")
    parser.add_argument("--env", default="world_tabletop_fem_v1")
    parser.add_argument("--robot", default="franka_panda_position_ik")
    parser.add_argument("--common", default="manipulation_space_tabletop_v1")
    parser.add_argument("--prefabs", default="topogym_prefabs_v1")
    args = parser.parse_args()

    failures: list[str] = []

    print("== 任务配置（配在基础 config.yaml 上）==")
    tasks = (
        [args.task]
        if args.task
        else sorted(p.stem for p in (CONFIGS / "task_configs").glob("*.yaml"))
    )
    for task in tasks:
        ok = check(
            task,
            "config",
            [
                f"common_configs@common={args.common}",
                f"env_configs@env={args.env}",
                f"robot_control_configs@robot_control={args.robot}",
                f"task_configs@task={task}",
                f"prefab_configs@prefabs={args.prefabs}",
            ],
        )
        if not ok:
            failures.append(task)

    print()
    print("== demo / 脚本主配置（各自的默认组合）==")
    primaries = sorted(
        p.stem
        for p in CONFIGS.glob("*.yaml")
        if p.stem != "config"
    )
    for name in primaries:
        if not check(name, name, []):
            failures.append(name)

    print()
    print("失败的配置：", failures if failures else "无")
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
