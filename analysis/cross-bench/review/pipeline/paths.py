"""Where things are. Code and prompts live in the repo; trial data and outputs live in a work directory outside it
(the repo is public). Every location can be changed with an environment variable."""
from __future__ import annotations
import json, os, sys

REVIEW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # analysis/cross-bench/review
XB = os.path.dirname(REVIEW)                                             # analysis/cross-bench
DATA = os.environ.get("REVIEW_DATA", "/data/pingyue/cross-bench/pilot-hl")  # work directory (outputs, sample.json, judgments)
RAW = os.environ.get("XB_RAW", "/data/pingyue/cross-bench/raw")             # trial cache written by tools/fetch.py
XB_DATA = os.environ.get("XB_DATA", os.path.join(XB, "data"))               # trials.csv, features.csv from tools/index.py, features.py
PROMPT = os.path.join(REVIEW, "prompts", "recap.md")
CODES = os.path.join(REVIEW, "prompts", "codes.json")
FONT = os.environ.get("REVIEW_FONT", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
FONT_BOLD = os.environ.get("REVIEW_FONT_BOLD", "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc")
FONT_INDEX = int(os.environ.get("REVIEW_FONT_INDEX", "2"))              # face in the .ttc: 2 = Simplified Chinese

sys.path.append(os.path.join(XB, "tools"))      # atif.py (agent logs of every harness), bel.py (the eval board)


def sample() -> list[dict]:
    """The trials to review: DATA/sample.json, a list of {key, agent, outcome, task, bench}."""
    return json.load(open(f"{DATA}/sample.json"))


def keys(only: list[str] | None = None) -> list[str]:
    ks = [s["key"] for s in sample()]
    return [k for k in ks if k in only] if only else ks


def load(path: str, default=None):
    return json.load(open(path)) if os.path.exists(path) else default


def jdump(obj, path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(obj, open(path, "w"), ensure_ascii=False, indent=1)
