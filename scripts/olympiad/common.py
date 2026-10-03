"""Settings every Olympiad sport shares (scripts/olympiad/generate.py and the sports' spec.py)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION = (ROOT / "images/olympiad/VERSION").read_text().strip()
IMAGE = f"ghcr.io/mll-lab-nu/eai-olympiad:{VERSION}"   # the simulator image of every sport
PINS = ROOT / "scripts/eai_standard/client-requirements.txt"
OFFICIAL_SLOWDOWNS = [1, 2, 5, 10, 20]      # single player
DUEL_SLOWDOWNS = [10, 20]
START_S, REVIEW_S = 1800, 300               # duel: start window after the first player; review limit per point
