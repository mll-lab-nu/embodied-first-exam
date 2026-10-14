"""Whether a text names a thing by one of its called words. Pure: the judge needs it in the sim image, which carries
no model-calling code (`recognise` re-exports it for the recognisability audit)."""
from __future__ import annotations

import re


def named(answer: str, words) -> str | None:
    """The first of `words` the answer contains (case does not matter; a word must start at a word boundary, so
    `batter` finds `batteries`). An entry `re:<pattern>` is a regular expression, matched with case."""
    low = answer.lower()
    for w in words or ():
        if w.startswith("re:"):
            if re.search(w[3:], answer):
                return w
        elif re.search(r"(?<![a-z0-9])" + re.escape(w.lower()), low):
            return w
    return None
