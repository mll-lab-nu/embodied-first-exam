"""Address a generated episode by ``(task_id, split, index)``.

This is the thin layer that turns the committed seed lists in
``configs/episode_splits/<task_id>.yaml`` into stable ``EpisodeSpec`` objects,
so batch recording and replay can name "swap test #3" and get the same episode
every time. It only routes to the existing per-task generators; it does not
change how any episode is built.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterator

from omegaconf import OmegaConf

from .episode_spec import EpisodeSpec
from .variant_episode import build_variant_episode

_SPLIT_ROOT = Path(__file__).resolve().parents[2] / "configs" / "episode_splits"

#: Every task whose yaml declares a ``variation:`` block. They all resolve to the
#: same builder: the block already says which leaves a seed may rewrite, so a
#: hand-written generator per task would be the same 125 lines copied again.
#: The table stays because ``make_episode_spec`` addresses a task by name.
_TASK_IDS = (
    "band_untwist",
    "bar_through_hole",
    "cloth_fold",
    "cloth_unpleat",
    "cloth_unroll",
    "diverter_route_ball",
    "gate_cage_ball",
    "linkbar_rotate_to_zone",
    "ring_transfer",
    "rope_unwinding",
    "rope_winding",
    "swap_crossing_sign",
    "unlink_c_ring",
)


def _generic(cfg, *, seed: int, task_id: str, **kwargs) -> EpisodeSpec:
    return build_variant_episode(cfg, task_id, seed, **kwargs)[1]


_GENERATORS: dict[str, Callable[..., EpisodeSpec]] = {
    task_id: (lambda cfg, *, seed, _t=task_id, **kw: _generic(cfg, seed=seed, task_id=_t, **kw))
    for task_id in _TASK_IDS
}


def load_split(task_id: str) -> dict[str, list[int]]:
    """Load the committed train/val/test seed lists for one task."""
    path = _SPLIT_ROOT / f"{task_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(
            f"No episode split registry for task {task_id!r} at {path}."
        )
    doc = OmegaConf.load(path)
    splits = OmegaConf.to_container(doc.splits, resolve=True)
    return {
        str(name): [int(seed) for seed in seeds] for name, seeds in splits.items()
    }


def split_seeds(task_id: str, split: str) -> list[int]:
    """Return the ordered seed list for one split."""
    splits = load_split(task_id)
    if split not in splits:
        raise KeyError(
            f"Split {split!r} not defined for task {task_id!r}; "
            f"available: {sorted(splits)}."
        )
    return splits[split]


def make_episode_spec(
    task_id: str, split: str, index: int, *, cfg, **builder_kwargs
) -> EpisodeSpec:
    """Resolve one ``(task_id, split, index)`` triple into a stable EpisodeSpec."""
    if task_id not in _GENERATORS:
        raise KeyError(
            f"No generator registered for task {task_id!r}; "
            f"available: {sorted(_GENERATORS)}."
        )
    seeds = split_seeds(task_id, split)
    if not 0 <= index < len(seeds):
        raise IndexError(
            f"index {index} out of range for {task_id}/{split} (0..{len(seeds) - 1})."
        )
    return _GENERATORS[task_id](cfg, seed=seeds[index], **builder_kwargs)


def iter_episode_specs(
    task_id: str, split: str, *, cfg, **builder_kwargs
) -> Iterator[EpisodeSpec]:
    """Yield an EpisodeSpec for every seed in one split, in order."""
    for index in range(len(split_seeds(task_id, split))):
        yield make_episode_spec(task_id, split, index, cfg=cfg, **builder_kwargs)
