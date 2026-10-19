"""Paths and names shared by the tools."""
from __future__ import annotations
import csv, os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # analysis/cross-bench
DATA = os.environ.get("XB_DATA") or os.path.join(HERE, "data")   # staging runs set XB_DATA (e.g. data-next/)
WEIGHTS = os.environ.get("XB_WEIGHTS") == "1"                   # review shares weighted by stratum (queries.tally)
RAW = os.environ.get("XB_RAW", "/data/pingyue/cross-bench/raw")

# run id -> display name of the agent (model + native harness)
AGENTS = {
    "codex-gpt6_luna-xhigh": "GPT-6 Luna",
    "codex-gpt6_astra-high": "GPT-6 Astra",
    "codex-gpt6_sol-high": "GPT-6 Sol",
    "codex-gpt6_1_sol-high": "GPT-6.1 Sol",
    "claude_code-opus_5_5-high": "Opus 5.5",
    "claude_code-glm_5_3_flash-high": "GLM-5.3 Flash",
    "claude_code-qwen3_8_27b-high": "Qwen3.8 27B",
    "dsh-deepseek_v4_1_flash-high": "DeepSeek V4.1 Flash",
    "antigravity_cli-gemini_3_8_flash-high": "Gemini 3.8 Flash",
    "antigravity_cli-gemini_4_argon-high": "Gemini 4 Argon",
}
LUNA = "codex-gpt6_luna-xhigh"


def trial_key(trial: dict) -> str:
    """Stable directory name for a trial: <run>__<trial name>."""
    return f'{trial["run"]}__{trial["trial"]}'


def read_csv(name: str) -> list[dict]:
    p = os.path.join(DATA, name)
    return list(csv.DictReader(open(p))) if os.path.exists(p) else []


def write_csv(name: str, rows: list[dict]) -> None:
    os.makedirs(DATA, exist_ok=True)
    cols = list(rows[0]) if rows else []
    with open(os.path.join(DATA, name) + ".part", "w", newline="") as f:
        w = csv.DictWriter(f, cols)
        w.writeheader()
        w.writerows(rows)
    os.replace(os.path.join(DATA, name) + ".part", os.path.join(DATA, name))
