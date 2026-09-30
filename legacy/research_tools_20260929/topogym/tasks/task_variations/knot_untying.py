"""Compatibility parameter view of active tiers; retired aliases are not remapped."""
from topogym.config.registry import resolve_variation

VARIATIONS = {name: resolve_variation('knot_untying', name, {}, 0)
              for name in ('easy', 'medium', 'hard', 'double_overhand')}
