"""Compatibility view of old parameter aliases; no independent registry."""
from topogym.config.registry import resolve_variation

VARIATIONS = {name: resolve_variation('blanket_flatten', name, {}, 0)
              for name in ('three_folds', 'five_folds')}
