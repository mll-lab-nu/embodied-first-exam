"""Idempotently register a `pi05_topogym_<task>` TrainConfig into OpenPI's config.py.

OpenPI discovers train configs only from the hardcoded `_CONFIGS` list in
`src/openpi/training/config.py` -- there is no external-config plugin seam. This
script appends a guarded block to the *end* of that file so the smoke config
is available to `compute_norm_stats.py` / `train.py` without a manual edit.

Why append at end-of-file (not insert into the list literal): `_CONFIGS_DICT` is
built at import (once), and `get_config` / `cli` read it at call time. An
end-of-file block runs after that, so `_CONFIGS.append(...)` + updating
`_CONFIGS_DICT[...]` reliably registers the config using config.py's own
module-level names (TrainConfig, pi0_config, LeRobotLiberoDataConfig, DataConfig,
_optimizer, weight_loaders -- all imported at the top of config.py).

Ensure-current semantics: each block is delimited by a begin/end marker pair
carrying its own config name. If the current desired block is already present ->
no-op; if a *stale* block for the same config name is present (e.g. an older
full-finetune version) -> only that block is replaced; otherwise it is appended.
So re-running always converges the file to the current template, and it
self-heals after an OpenPI re-sync/re-clone. Pure text edit -- imports nothing
from openpi, so any Python works.

The markers are per-config-name so blocks for several tasks coexist: registering
`pi05_topogym_cable_routing` leaves an existing `pi05_topogym_swap` block intact.

Why LoRA / low-mem: full fine-tuning pi0.5 (~3.3B params) with AdamW needs ~50 GB
(params + Adam m/v + grads + EMA) and OOMs a single 24 GB GPU. LoRA freezes the
base and trains only small adapters (`get_freeze_filter()`, `ema_decay=None`),
which fits a consumer card -- enough to prove the data enters the train loop.

Usage (from repo root):
    python scripts/register_openpi_config.py --task swap             # derives both names
    python scripts/register_openpi_config.py --openpi-dir .external/openpi \
        --config-name pi05_topogym_swap --repo-id topogym/swap_smoke

Mirrors the documented block in docs/develop/il_adaptation/pi05_smoke_zh.md §3.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def _begin_marker(config_name: str) -> str:
    return f"# === TopoGym {config_name} config begin (auto-appended"


def _end_marker(config_name: str) -> str:
    return f"# === TopoGym {config_name} config end ==="


# Pre-2026-08 single-marker block, always written last and with no end marker.
# Recognised so an existing checkout converges instead of ending up with two
# blocks registering the same config name.
_LEGACY_MARKER = "# === TopoGym swap smoke config (auto-appended"

# LoRA variants shared by model + freeze_filter (must match, per pi0_libero_low_mem_finetune).
_MODEL = (
    'pi0_config.Pi0Config(\n'
    '            pi05=True, action_horizon=10, discrete_state_input=False,\n'
    '            paligemma_variant="gemma_2b_lora", action_expert_variant="gemma_300m_lora",\n'
    '        )'
)

BLOCK_TEMPLATE = '''{begin_marker} by scripts/register_openpi_config.py) ===
# 详见 docs/develop/il_adaptation/pi05_smoke_zh.md 第 3 节。
# LoRA/低显存版：只训适配器，冻结基座（否则全参微调 pi0.5 需 ~50GB，单卡 24GB OOM）。
_CONFIGS.append(
    TrainConfig(
        name="{config_name}",
        model={model},
        data=LeRobotLiberoDataConfig(
            repo_id="{repo_id}",
            base_config=DataConfig(prompt_from_task=True),
            extra_delta_transform=False,
        ),
        batch_size=4,
        num_workers=0,
        num_train_steps=5,
        wandb_enabled=False,
        lr_schedule=_optimizer.CosineDecaySchedule(
            warmup_steps=1, peak_lr=5e-5, decay_steps=100, decay_lr=5e-5,
        ),
        optimizer=_optimizer.AdamW(clip_gradient_norm=1.0),
        freeze_filter={model}.get_freeze_filter(),
        ema_decay=None,
        weight_loader=weight_loaders.CheckpointWeightLoader(
            "gs://openpi-assets/checkpoints/pi05_base/params"
        ),
    )
)
_CONFIGS_DICT[_CONFIGS[-1].name] = _CONFIGS[-1]
{end_marker}
'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--openpi-dir",
        default=".external/openpi",
        help="OpenPI checkout root (contains src/openpi/training/config.py).",
    )
    parser.add_argument(
        "--task",
        default="swap",
        help="Task id used to derive --config-name and --repo-id when they are not given.",
    )
    parser.add_argument("--config-name", default=None, help="Defaults to pi05_topogym_<task>.")
    parser.add_argument("--repo-id", default=None, help="Defaults to topogym/<task>_smoke.")
    args = parser.parse_args()

    config_name = args.config_name or f"pi05_topogym_{args.task}"
    repo_id = args.repo_id or f"topogym/{args.task}_smoke"

    config_py = Path(args.openpi_dir) / "src" / "openpi" / "training" / "config.py"
    if not config_py.is_file():
        raise SystemExit(f"[error] config.py not found: {config_py} (run env_setup_vla_openpi.sh first)")

    begin, end = _begin_marker(config_name), _end_marker(config_name)
    block = BLOCK_TEMPLATE.format(
        begin_marker=begin, end_marker=end, config_name=config_name, repo_id=repo_id, model=_MODEL
    )
    text = config_py.read_text(encoding="utf-8")

    dropped_legacy = _LEGACY_MARKER in text
    if dropped_legacy:  # old single-marker block ran to EOF
        text = text[: text.index(_LEGACY_MARKER)].rstrip("\n") + "\n"

    # `dropped_legacy` still needs a write even when the desired block survives the
    # strip, otherwise the stale block would stay and register the name twice.
    if block.strip() in text and not dropped_legacy:
        print(f"[ok] {config_name} already registered (current) in {config_py}")
        return

    if begin in text:  # stale block for THIS config name -> splice just it out
        start = text.index(begin)
        end_at = text.index(end, start) + len(end) if end in text[start:] else len(text)
        text = text[:start].rstrip("\n") + "\n" + text[end_at:].lstrip("\n")
        action = "updated"
    else:
        action = "appended"
    config_py.write_text(text.rstrip("\n") + "\n\n" + block, encoding="utf-8")
    print(f"[ok] {action} {config_name} (LoRA, repo_id={repo_id}) -> {config_py}")


if __name__ == "__main__":
    main()
