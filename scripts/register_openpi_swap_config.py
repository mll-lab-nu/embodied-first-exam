"""Idempotently register the `pi05_topogym_swap` TrainConfig into OpenPI's config.py.

OpenPI discovers train configs only from the hardcoded `_CONFIGS` list in
`src/openpi/training/config.py` -- there is no external-config plugin seam. This
script appends a guarded block to the *end* of that file so the swap smoke config
is available to `compute_norm_stats.py` / `train.py` without a manual edit.

Why append at end-of-file (not insert into the list literal): `_CONFIGS_DICT` is
built at import (once), and `get_config` / `cli` read it at call time. An
end-of-file block runs after that, so `_CONFIGS.append(...)` + updating
`_CONFIGS_DICT[...]` reliably registers the config using config.py's own
module-level names (TrainConfig, pi0_config, LeRobotLiberoDataConfig, DataConfig,
_optimizer, weight_loaders -- all imported at the top of config.py).

Idempotent: re-running is a no-op once the config name is present. Self-healing:
if OpenPI is re-synced/re-cloned (wiping the append), just run this again. Pure
text edit -- imports nothing from openpi, so any Python works.

Usage (from repo root):
    python scripts/register_openpi_swap_config.py                 # defaults
    python scripts/register_openpi_swap_config.py --openpi-dir .external/openpi \
        --config-name pi05_topogym_swap --repo-id topogym/swap_smoke

Mirrors the documented diff in docs/develop/il_adaptation/swap_to_pi05_smoke_zh.md §3.
"""

from __future__ import annotations

import argparse
from pathlib import Path

MARKER = "# === TopoGym swap smoke config (auto-appended"

BLOCK_TEMPLATE = '''

{marker} by scripts/register_openpi_swap_config.py) ===
# 详见 docs/develop/il_adaptation/swap_to_pi05_smoke_zh.md 第 3 节。幂等：按 name 去重。
_CONFIGS.append(
    TrainConfig(
        name="{config_name}",
        model=pi0_config.Pi0Config(pi05=True, action_horizon=10, discrete_state_input=False),
        data=LeRobotLiberoDataConfig(
            repo_id="{repo_id}",
            base_config=DataConfig(prompt_from_task=True),
            extra_delta_transform=False,
        ),
        batch_size=4,
        num_workers=0,
        num_train_steps=5,
        lr_schedule=_optimizer.CosineDecaySchedule(
            warmup_steps=1, peak_lr=5e-5, decay_steps=100, decay_lr=5e-5,
        ),
        optimizer=_optimizer.AdamW(clip_gradient_norm=1.0),
        ema_decay=0.999,
        weight_loader=weight_loaders.CheckpointWeightLoader(
            "gs://openpi-assets/checkpoints/pi05_base/params"
        ),
    )
)
_CONFIGS_DICT[_CONFIGS[-1].name] = _CONFIGS[-1]
'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--openpi-dir",
        default=".external/openpi",
        help="OpenPI checkout root (contains src/openpi/training/config.py).",
    )
    parser.add_argument("--config-name", default="pi05_topogym_swap")
    parser.add_argument("--repo-id", default="topogym/swap_smoke")
    args = parser.parse_args()

    config_py = Path(args.openpi_dir) / "src" / "openpi" / "training" / "config.py"
    if not config_py.is_file():
        raise SystemExit(f"[error] config.py not found: {config_py} (run env_setup_vla_openpi.sh first)")

    text = config_py.read_text(encoding="utf-8")
    if f'name="{args.config_name}"' in text:
        print(f"[ok] {args.config_name} already registered in {config_py}")
        return

    block = BLOCK_TEMPLATE.format(
        marker=MARKER, config_name=args.config_name, repo_id=args.repo_id
    )
    config_py.write_text(text.rstrip("\n") + "\n" + block, encoding="utf-8")
    print(f"[ok] appended {args.config_name} (repo_id={args.repo_id}) -> {config_py}")


if __name__ == "__main__":
    main()
