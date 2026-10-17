#!/usr/bin/env python3
"""Generate the frozen DexHand task pairs, or compare them with a clean render."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SHARED = HERE / "shared"
LIBRARY = HERE / "task_library"
LAYER = ROOT / "scripts/eai_standard"
DAILY = HERE / "daily"
# Self-owned families (artifacts FAMILY_PLUGIN.md): every scripts/dexhand/families/<id>/family.json, plus listed
# external source folders that contain a family.json (none: every release family lives under scripts/dexhand/).
FAMILIES = HERE / "families"
HAMBURGER = FAMILIES / "assemble_hamburger"
EXTERNAL_FAMILIES: tuple[Path, ...] = ()
RELEASE = HERE / "release.json"
SOLUTION = SHARED / "solution"
# Repository rule: no committed file reaches 2 MB (split oracle rows with shared/solution/solution_parts.py).
MAX_FILE_BYTES = 2_000_000
OVERSIZED: set[str] = set()
# Shared files every plugin family receives next to its own runtime files (one source each, D9).
PLUGIN_SHARED = ("rcb_dexhand.py", "hands.py")
sys.path.insert(0, str(ROOT / "scripts"))
from task_conventions import normalize  # noqa: E402

IMAGE = "ghcr.io/mll-lab-nu/eai-dexhand:" + (ROOT / "images/dexhand/VERSION").read_text().strip()
# The published image is pinned by digest once pushed (images/dexhand/DIGEST, written after `docker push`).
if (ROOT / "images/dexhand/DIGEST").exists():
    IMAGE += "@" + (ROOT / "images/dexhand/DIGEST").read_text().strip()
CLIENT_IMAGE = next(
    line.split("=", 1)[1]
    for line in (LAYER / "client.env").read_text().splitlines()
    if line.startswith("CLIENT_IMAGE=")
)
# The agent's time cutoff per mode (PROTOCOL §2.12): this benchmark's own number, written into every task's `[agent]
# timeout_sec`, the one source; normalize renders from it the instruction's closing `## Time limit`, the README row and
# the sim service's wall clock. To change it (an owner decision; the pull request states old -> new), edit it here and
# regenerate.
CUTOFF = {"privileged": 3600, "standard": 3600}
# Standard mode's reset budget (owner, 2026-10-14, board 0109; PROTOCOL §4.5, DexToolBench's value): the compose
# default of RCB_RESET_BUDGET, which a run may override; the service's /spec budget.reset is authoritative.
RESET_BUDGET = 20
RESETS_SECTION = f"""## Episodes and resets
You have **{RESET_BUDGET} resets** (`spec["budget"]["reset"]`, which is authoritative: if it says 0, there is no reset
and the one episode is the run). A reset puts the robot and every object back in the same frozen starting state and
starts a new episode, either abandoning the running one or after one has ended; it takes no simulated time and
returns the start's images and proprioception:
```python
res = r._post("/reset", {{"cameras": ["overview"]}}, [], 900)   # POST /reset (the 2.2 client has no reset())
res.meta["episode"], res.meta["resets_left"]
```
Once an episode has ended, `submit` raises `EpisodeOver` until you reset. **Only the last episode is graded**: an
episode you reset away is never graded, a success ends the run at once (no reset after it), and when your time is up
the episode then running is the one graded. The wall clock is the run's and never restarts; `meta["episode"]` and
`meta["resets_left"]` count the episodes (`meta["control_steps"]` is the current episode's,
`meta["control_steps_total"]` all of them).
"""
TOOLING = (
    "runtime.py",
    "scene.py",
    "checker.py",
    "rcb_dexhand.py",
    "replay.py",
    "essential.py",
    "essential_articulated.py",
    "essential_inhand.py",
    "essential_rotary_multi.py",
    "essential_assets.py",
    "essential_visual.py",
    "essential_registry.json",
    "hands.py",
    *[entry["module"] + ".py" for entry in json.loads((LIBRARY / "index.json").read_text())["tasks"]],
)
ALLOWED_HOSTS = [
    "chatgpt.com",
    "*.chatgpt.com",
    "auth.openai.com",
    "api.openai.com",
    "*.openai.com",
    "api.anthropic.com",
    "*.anthropic.com",
    "openrouter.ai",
    "*.openai.azure.com",
    "*.cognitiveservices.azure.com",
    "pypi.org",
    "files.pythonhosted.org",
    "deb.debian.org",
    "security.debian.org",
    "archive.ubuntu.com",
    "security.ubuntu.com",
    "snapshot.ubuntu.com",
]
EVIDENCE = (
    "Checker feature fixtures and negative controls are provided by scripts/dexhand/tests/test_checker.py; "
    "scripts/dexhand/validate.py runs physical no-op and actuator-probe replay checks. "
    "No low-level successful policy or rollout is claimed; solvability and full agent-trial calibration "
    "remain provisional and require human review before scored release."
)
ESSENTIAL_EVIDENCE = (
    "The essential families use passive objects and native fixed-wrist constraints. "
    "Physical actuator policies and replay recordings are validated separately by "
    "scripts/dexhand/validate_essential.py; feature fixtures alone are not solvability evidence. "
    "No packaged low-level oracle is provided. Human solvability review and full agent-trial calibration "
    "remain required before scored release."
)


def daily_folders() -> dict[str, Path]:
    index = DAILY / "index.json"
    if not index.exists():
        return {}
    return {entry["id"]: DAILY / entry["folder"] for entry in json.loads(index.read_text())["tasks"]}


# ------------------------------------------------------------------------------------------- plugin families
PLUGIN_KEYS = {
    "schema_version", "id", "task", "runtime", "hands", "action_dim", "robot", "cameras", "max_rows",
    "instruction", "readme", "solution", "metadata", "timeouts", "compose_env", "notes", "control_hz",
}
PLACEHOLDERS = ("{{TITLE}}", "{{TASK_TEXT}}", "{{HANDS}}", "{{FAMILY}}", "{{MAX_ROWS}}", "{{AGENT_MINUTES}}",
                "{{NAME}}", "{{MODE}}", "{{TWIN}}", "{{IMAGE}}", "{{CONTROL_HZ}}", "{{RESETS}}")


def plugin_folders() -> dict[str, Path]:
    """Registered self-owned families: a directory scan, no central list to edit (FAMILY_PLUGIN.md)."""
    found = {}
    candidates = sorted(FAMILIES.glob("*/family.json")) if FAMILIES.is_dir() else []
    candidates += [folder / "family.json" for folder in EXTERNAL_FAMILIES if (folder / "family.json").is_file()]
    for manifest in candidates:
        family = json.loads(manifest.read_text()).get("id")
        if manifest.parent.parent == FAMILIES and family != manifest.parent.name:
            raise ValueError(f"{manifest}: id {family!r} must equal its folder name")
        if family in found:
            raise ValueError(f"Family {family!r} is registered twice")
        found[family] = manifest.parent
    return found


def _family_file(folder: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{folder.name}: family paths must be relative and inside the family folder: {relative}")
    target = folder / path
    if not target.exists():
        raise ValueError(f"{folder.name}: missing {relative}")
    return target


def load_plugin(folder: Path) -> tuple[dict, dict]:
    """Validate a family's family.json and return (manifest, frozen task spec)."""
    manifest = json.loads((folder / "family.json").read_text())
    unknown = set(manifest) - PLUGIN_KEYS
    if unknown:
        raise ValueError(f"{folder.name}/family.json: unknown keys {sorted(unknown)}")
    if manifest.get("schema_version") != 1:
        raise ValueError(f"{folder.name}/family.json: schema_version must be 1")
    spec = json.loads(_family_file(folder, manifest.get("task", "task.json")).read_text())
    if spec.get("id") != manifest["id"]:
        raise ValueError(f"{folder.name}: task.json id {spec.get('id')!r} differs from family id {manifest['id']!r}")
    for key in ("title", "description", "instruction", "difficulty", "category"):
        if not isinstance(spec.get(key), str) or not spec[key]:
            raise ValueError(f"{folder.name}: task.json needs a nonempty {key!r}")
    hands = manifest.get("hands", ["sharpa", "wuji"])
    if hands[:1] != ["sharpa"] or not set(hands) <= {"sharpa", "wuji"}:
        raise ValueError(f"{folder.name}: hands must start with the default 'sharpa' (optionally 'wuji')")
    widths = manifest.get("action_dim", {})
    if set(widths) != set(hands) or not all(isinstance(v, int) and v > 0 for v in widths.values()):
        raise ValueError(f"{folder.name}: action_dim must give a positive width for every hand in {hands}")
    if "agent_sec" in manifest.get("timeouts", {}):
        raise ValueError(f"{folder.name}/family.json: timeouts.agent_sec is gone; the agent's time limit is "
                         "CUTOFF in scripts/dexhand/generate.py (PROTOCOL §2.12)")
    if not isinstance(manifest.get("control_hz", 50), int) or not 1 <= manifest.get("control_hz", 50) <= 10_000:
        raise ValueError(f"{folder.name}: control_hz must be an integer rate in Hz")
    runtime = manifest.get("runtime", {})
    files = runtime.get("files", [])
    for required in ("runtime.py", "replay.py"):
        if required not in files:
            raise ValueError(f"{folder.name}: runtime.files must include {required}")
    for relative in files + runtime.get("dirs", []):
        _family_file(folder, relative)
    for name in runtime.get("shared", []):
        if not (SHARED / name).is_file():
            raise ValueError(f"{folder.name}: runtime.shared names an unknown shared file {name}")
    for mode in ("privileged", "standard"):
        _family_file(folder, manifest["instruction"][mode])
        readme = manifest["readme"]
        _family_file(folder, readme[mode] if isinstance(readme, dict) else readme)
    solution = manifest.get("solution")
    oracle = manifest.get("metadata", {}).get("oracle", "none")
    if oracle not in ("full", "partial", "none"):
        raise ValueError(f"{folder.name}: metadata.oracle must be full|partial|none")
    if oracle != "none":
        if not solution:
            raise ValueError(f"{folder.name}: oracle {oracle!r} needs a solution entry")
        for mode in ("privileged", "standard"):
            _family_file(folder, solution[mode])
    if oracle != "full" and not manifest.get("metadata", {}).get("oracle_evidence"):
        raise ValueError(f"{folder.name}: a non-full oracle needs metadata.oracle_evidence")
    return manifest, spec


def sharpa_only_section(reason: str) -> str:
    """The Hands section of a family that offers only the Sharpa Wave: the hand, why not Wuji (one line), refused."""
    return ("## Hands\nThis task uses the Sharpa Wave (22 finger actuators per hand). The Wuji Hand 2.2 is not offered "
            f"for this task: {reason}. Selecting Wuji is refused.\n")


def hands_section(widths: dict, mode: str, layout: str | None = None, reason: str = "") -> str:
    """The canonical hand-selection paragraph (HAND_INTERFACE.md section 6); identical words in every family."""
    sharpa, wuji = widths.get("sharpa"), widths.get("wuji")
    if not wuji:   # a family that offers only the Sharpa Wave
        return sharpa_only_section(reason)
    lines = [
        "## Hands",
        "Two genuine manufacturer hand models are available: `sharpa` (Sharpa Wave, 22 finger actuators; the "
        "default) and `wuji` (Wuji Hand 2.2, 20 finger actuators). The task, scene, mount, objects and success "
        "predicate are the same for both; only one hand is used per episode.",
    ]
    if layout:
        lines.append(layout)
    if mode == "privileged":
        lines.append(
            f"Choose the hand with `Session(..., hand=\"wuji\")` or the environment variable `DEXHAND_HAND=wuji` "
            f"(default `sharpa`). Action rows are `{sharpa}` wide for `sharpa`"
            + (f" and `{wuji}` wide for `wuji`" if wuji else "")
            + "; `s.actuator_names` gives the exact order. `s.save_trajectory(actions, path)` records the hand in "
            "the archive (`hand` member). The verifier rebuilds the scene with the recorded hand (default `sharpa` "
            "when the member is absent) and rejects a trajectory whose width does not match that hand; rows are "
            "never padded, truncated or converted between hands."
        )
    else:
        lines.append(
            "The robot service runs the hand named by `DEXHAND_HAND` on the sim service (default `sharpa`); the "
            "agent cannot switch it during an episode. `spec()[\"hand\"]` names it, and "
            "`spec()[\"action_types\"][\"joint_position\"]` gives the row width "
            f"(`{sharpa}` for `sharpa`" + (f", `{wuji}` for `wuji`" if wuji else "") + ") and the exact order. "
            "The episode record names the hand; the service grades the episode it ran with that hand."
        )
    return "\n".join(lines) + "\n"


# The standard twins' grading (owner, 2026-10-17, board 0151), for every README: the trusted sim service judges the
# live episode; no replay. Plugin families' shared README.task.md describe both modes; standard_verification()
# rewrites their replay sentences for the standard twin (the privileged README is unchanged).
STANDARD_GRADING = (
    "The trusted sim service judges the episode it ran (the last one after resets) with the task's predicate and\n"
    "the selected hand, after the agent's container is stopped; its record (`final.json`, `graded_by = \"live\"`) is the\n"
    "verdict, and nothing is replayed to grade it. The isolated verifier reads only the service's artifacts. The\n"
    "service then renders `replay.mp4` from the recorded trajectory in one video-only pass, which never changes the\n"
    "verdict. A missing or unfinished record, a give-up after crashes between the agent's calls and a frozen instance\n"
    "that does not build at the episode's start are infrastructure errors.")
PRIVILEGED_HASHES = ", and identical final\nstate hashes"   # the essential READMEs' privileged rule (two replays)
_STANDARD_REWRITES = (
    # "{{MODE}} mode. The verifier rebuilds ... A replay ends at the first success or the first failure."
    (re.compile(r"\{\{MODE\}\} mode\. The verifier rebuilds the frozen scene with the recorded hand.*?A replay ends at the"
                r"\s+first\s+success\s+or\s+the\s+first\s+failure\.", re.S),
     "Standard mode. " + STANDARD_GRADING + "\nThe episode ends at the first success or the first failure."),
    # pot_shelf_transfer, paper_half_fold: "Standard: the trusted (simulator) service journals every executed row; ..."
    (re.compile(r"Standard: the trusted (simulator )?service journals every executed\s+row;.*?(agree|live hash\))\.", re.S),
     "Standard: t" + STANDARD_GRADING[1:]),
)


def standard_verification(text: str) -> str:
    """A plugin family's README.task.md for its standard twin: the replay sentences become the live grading."""
    for pattern, new in _STANDARD_REWRITES:
        text = pattern.sub(lambda _m: new, text)
    section = text.split("## Verification", 1)[-1].split("\n## ", 1)[0]
    stale = re.search(r"live (final )?hash|collect hook replays|replay successes|in\s+standard\s+mode\s+the\s+replay", section)
    if "## Verification" in text and stale:
        raise ValueError(f"standard README still describes a grading replay: {stale.group(0)!r}")
    return text


def fill(text: str, values: dict) -> str:
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", str(value))
    left = [token for token in PLACEHOLDERS if token in text]
    if "{{" in text and left:
        raise ValueError(f"unfilled placeholders {left}")
    return text


def plugin_texts(folder: Path, manifest: dict, spec: dict, mode: str, name: str) -> tuple[str, str]:
    """(instruction.md, README.md) of a plugin family, rendered from the family's own text files."""
    twin = name.removesuffix(mode) + ("standard" if mode == "privileged" else "privileged")
    widths = manifest["action_dim"]
    values = {
        "TITLE": spec["title"],
        "TASK_TEXT": spec["instruction"],
        "HANDS": hands_section(widths, mode, manifest.get("notes", {}).get("layout"), manifest.get("notes", {}).get("hands", "")),
        "FAMILY": spec["id"],
        "MAX_ROWS": manifest.get("max_rows", 50_000),
        "CONTROL_HZ": manifest.get("control_hz", 50),
        "NAME": name,
        "MODE": mode,
        "TWIN": twin,
        "IMAGE": IMAGE,
        "RESETS": RESETS_SECTION if mode == "standard" else "",
    }
    instruction_text = fill(_family_file(folder, manifest["instruction"][mode]).read_text(), values)
    readme = manifest["readme"]
    body = _family_file(folder, readme[mode] if isinstance(readme, dict) else readme).read_text()
    body = fill(standard_verification(body) if mode == "standard" and not isinstance(readme, dict) else body, values)
    oracle = manifest.get("metadata", {}).get("oracle", "none")
    hands = ", ".join(f"{hand} {widths[hand]}" for hand in manifest.get("hands", ["sharpa", "wuji"]))
    header = f"""# {name}

| | |
|---|---|
| Benchmark | DexHand |
| Mode | {mode} |
| Twin | `{twin}` |
| Simulator / robot | MuJoCo 3.4.0, CPU / {f"selectable hand (action width: {hands}); default Sharpa Wave" if len(widths) > 1 else f"Sharpa Wave (action width {widths['sharpa']})"} |
| Family / instance | `{spec["id"]}` / i00 |
| Oracle | {oracle} |
| Agent time budget | {CUTOFF[mode]} s |
| Base image | `{IMAGE}` |

"""
    return instruction_text, header + body


def copy_tree(source: Path, target: Path) -> None:
    for file in sorted(source.rglob("*")):
        if file.is_file() and "__pycache__" not in file.parts and file.suffix != ".pyc":
            copy(file, target / file.relative_to(source))


def copy_plugin_runtime(folder: Path, manifest: dict, target: Path) -> None:
    runtime = manifest.get("runtime", {})
    for relative in runtime.get("files", []):
        copy(_family_file(folder, relative), target / relative)
    for relative in runtime.get("dirs", []):
        copy_tree(_family_file(folder, relative), target / relative)
    for name in dict.fromkeys(PLUGIN_SHARED + tuple(runtime.get("shared", []))):
        copy(SHARED / name, target / name)
    offered = manifest.get("hands", ["sharpa", "wuji"])
    if set(offered) != {"sharpa", "wuji"}:   # hands.py refuses any other hand in this task (hands.offered)
        write(target / "offered_hands.json", json.dumps(
            {"family": folder.name, "hands": offered, "reason": manifest.get("notes", {}).get("hands", "")}, indent=2) + "\n")


def solution_files(source: Path) -> list[tuple[Path, str]]:
    """(source file, name in solution/) for a single `.npz` or a `trajectory.json` multi-part manifest."""
    if source.suffix == ".json":
        manifest = json.loads(source.read_text())
        files = [(source, "trajectory.json")]
        for part in manifest["parts"]:
            relative = Path(part["file"])
            if relative.is_absolute() or ".." in relative.parts or relative.parent != Path("."):
                raise ValueError(f"solution parts must sit next to their manifest: {part['file']}")
            files.append((source.parent / relative, relative.name))
        return files
    return [(source, "trajectory.npz")]


HAND_TITLES = {"sharpa": "Sharpa Wave", "wuji": "Wuji Hand 2.2"}


def solution_shape(source: Path) -> tuple[int, int, str, str | None]:
    """(rows, width, hand, task or None) of a `.npz` solution or a `trajectory.json` parts manifest."""
    if source.suffix == ".json":
        manifest = json.loads(source.read_text())
        return int(manifest["rows"]), int(manifest["width"]), str(manifest.get("hand", "sharpa")), manifest.get("task")
    import numpy as np

    with np.load(source, allow_pickle=False) as archive:
        actions = archive["actions"]
        if actions.ndim != 2:
            raise ValueError(f"{source}: actions must be a 2-D array")
        hand = str(archive["hand"]) if "hand" in archive.files else "sharpa"
        task = str(archive["task"]) if "task" in archive.files else None
        return int(actions.shape[0]), int(actions.shape[1]), hand, task


def hand_solutions(solution: Path, widths: dict, family: str, max_rows: int | None = None) -> dict[str, Path]:
    """Reference solutions for a hand other than the default one, by convention next to the family's (Sharpa Wave)
    solution: `<solution dir>/<hand>/trajectory.npz`, or `<hand>/trajectory.json` + parts above 2 MB. Dropping one in
    is all a family does; the generator packages it as `solution/<hand>/` of both modes, and the oracle uses it when
    the run selects that hand (privileged: DEXHAND_HAND; standard: the sim service's hand). A hand without one keeps
    the default oracle unchanged."""
    found = {}
    for hand in sorted(HAND_TITLES):
        folder = solution.parent / hand
        if not folder.is_dir():
            continue
        if hand == "sharpa" or hand not in widths:
            raise ValueError(f"{family}: {folder.name}/ next to the solution must name an offered hand other than the "
                             f"default sharpa (offered: {sorted(widths)})")
        source = folder / "trajectory.json"
        source = source if source.is_file() else folder / "trajectory.npz"
        if not source.is_file():
            raise ValueError(f"{family}: {hand}/ needs trajectory.npz (or trajectory.json with its parts)")
        rows, width, recorded, task = solution_shape(source)
        if recorded != hand or width != widths[hand] or rows < 1 or (max_rows and rows > max_rows) \
                or task not in (None, family):
            raise ValueError(f"{family}: {hand}/{source.name} holds {rows} rows of width {width} for hand {recorded!r}"
                             f" and task {task!r}; expected {hand!r} rows of width {widths[hand]}"
                             + (f", at most {max_rows}" if max_rows else ""))
        found[hand] = source
    return found


def hand_solution_text(hands: dict[str, Path], mode: str | None = None) -> str:
    """The generator's own sentence about per-hand reference solutions (README for a mode, else task.toml)."""
    texts = []
    for hand, source in sorted(hands.items()):
        rows, title = solution_shape(source)[0], HAND_TITLES[hand]
        label = solution_label(source, code=mode is not None, folder=f"solution/{hand}/")
        if mode is None:
            texts.append(f"{label} is a validated {title} trajectory of this instance ({rows:,} controls, motor targets "
                         f"only, physical contact only); the oracle uses it when the run selects {hand} (privileged: "
                         f"DEXHAND_HAND={hand}; standard: the sim service's hand), and it replays to success in two "
                         "fresh processes with identical state hashes.")
        elif mode == "privileged":
            texts.append(f"{title}: {label} is a validated {title} trajectory of this instance ({rows:,} rows of motor "
                         f"targets, physical contact only). With `DEXHAND_HAND={hand}` set for the oracle, `solve.sh` "
                         f"hands it in instead of the Sharpa Wave rows; the verifier replays it with the {title}.")
        else:
            texts.append(f"{title}: {label} is a validated {title} trajectory of this instance ({rows:,} rows of motor "
                         f"targets, physical contact only). When the sim service runs the {title} "
                         f"(`DEXHAND_HAND={hand}`, `spec()[\"hand\"]`), `solve.sh` submits these rows as float64 instead "
                         "of the Sharpa Wave rows.")
    return " ".join(texts)


def with_hand_solutions(readme_text: str, hands: dict[str, Path], mode: str) -> str:
    """End a README's `## Reference solution` section with the per-hand solution paragraph (generator-owned)."""
    if not hands:
        return readme_text
    start = readme_text.find("\n## Reference solution\n")
    if start < 0:
        raise ValueError("README without a ## Reference solution section")
    end = readme_text.find("\n## ", start + 5)
    end = len(readme_text) if end < 0 else end
    return (readme_text[:end].rstrip("\n") + "\n\n" + hand_solution_text(hands, mode) + "\n"
            + readme_text[end:])


def write_solution(task: Path, mode: str, trajectory: Path, hands: dict[str, Path] | None = None) -> None:
    """Generator-owned oracle runners (one source for every family) plus the family's validated rows.

    Rows above the repository's 2 MB file limit are stored as `trajectory.json` + `trajectory.partNN.npz`
    (shared/solution/solution_parts.py `split`); the oracle concatenates and sha256-checks them before use.
    A per-hand solution (`hand_solutions`) becomes `solution/<hand>/`: its rows next to unchanged copies of the shared
    oracle runner and `solution_parts.py`, and `solve.sh` is then the `*_by_hand.sh` runner that picks the selected
    hand's folder. A task without one keeps the single-hand runner byte for byte.
    """
    runner = "oracle.py" if mode == "privileged" else "oracle_replay.py"
    folders = [(trajectory, task / "solution")]
    folders += [(source, task / "solution" / hand) for hand, source in sorted((hands or {}).items())]
    for rows, target in folders:
        for source, name in solution_files(rows):
            if source.stat().st_size >= MAX_FILE_BYTES:
                OVERSIZED.add(str(source.relative_to(ROOT) if source.is_relative_to(ROOT) else source))
            copy(source, target / name)
        copy(SOLUTION / "solution_parts.py", target / "solution_parts.py")
        copy(SOLUTION / runner, target / runner)
    copy(SOLUTION / f"solve_{mode}{'_by_hand' if hands else ''}.sh", task / "solution/solve.sh")
    (task / "solution/solve.sh").chmod(0o755)


def grading(manifest: dict | None) -> str:
    """Per-family grader limits read by the privileged grade.py (default replay timeout 1400 s). The replay video runs
    after the verdict in the time left of the verifier (board 0136): its timeout_sec is written here for that bound;
    video_timeout_s (at least the replay timeout) caps it."""
    timeouts = (manifest or {}).get("timeouts", {})
    return json.dumps({"replay_timeout_s": int(timeouts.get("replay_sec", 1400)),
                       # the video replays the whole episode again: never a shorter bound than the replay's own
                       "video_timeout_s": max(int(timeouts.get("video_sec", 1400)), int(timeouts.get("replay_sec", 1400))),
                       "verifier_timeout_s": int(timeouts.get("verifier_privileged_sec", 3600)),
                       "collect_timeout_s": int(timeouts.get("collect_sec", 3600))}, sort_keys=True) + "\n"


# Standard collect hook (finalize.sh): `rcb_limited.py end` waits at most END_WAIT_S for the service to end and dump
# its episode; then the verdict is written from the service's record (no replay, board 0151) and one video process
# films the trajectory. That process is the family's replay.py `--video`: it steps the episode once without rendering
# (replay_sec bounds that) and once more filming it (video_sec), so it gets both. The hook's timeout covers the end,
# the video and VIDEO_MARGIN_S (finalize.py) + 60 s, and is never longer than before the replays were removed.
END_WAIT_S = 300
# The files that declare the frozen instance, when present in the sim dir: the service compares their sha256 with
# grading.json's record when an episode begins (instance_mismatch: an infrastructure failure, no episode).
INSTANCE_FILES = ("instance.json", "catalog.json", "task.json", "wuji_reset.json", "offered_hands.json")


def std_video_s(manifest: dict | None) -> int:
    timeouts = (manifest or {}).get("timeouts", {})
    replay = int(timeouts.get("replay_sec", 1400))
    return replay + max(int(timeouts.get("video_sec", 1400)), replay)


def std_collect_s(manifest: dict | None) -> int:
    timeouts = (manifest or {}).get("timeouts", {})
    return min(int(timeouts.get("collect_sec", 3600)), END_WAIT_S + std_video_s(manifest) + 120)


def std_grading(manifest: dict | None, runtime: Path) -> str:
    """The standard collect hook's limits (finalize.py) and the frozen instance's file hashes (server.py)."""
    shas = {name: hashlib.sha256((runtime / name).read_bytes()).hexdigest()
            for name in INSTANCE_FILES if (runtime / name).is_file()}
    return json.dumps({"video_timeout_s": std_video_s(manifest), "collect_timeout_s": std_collect_s(manifest),
                       "instance_sha256": shas}, sort_keys=True) + "\n"


def release_families() -> list[str]:
    return list(json.loads(RELEASE.read_text())["families"])


FEATURES = {
    "force": "largest contact force on any task object, N (peak over the 2 ms substeps)",
    "speed": "largest absolute velocity of any task-object degree of freedom, m/s or rad/s (peak over the substeps)",
    "palm_drift": "palm displacement from its reset position, m",
    "wrist_rotation": "palm rotation from its reset orientation, rad",
    "support": "contacts (> 0.01 N) between a task object and the environment (table, fixtures)",
    "body_drift": "displacement of the free object's body from its reset position, m",
    "body_rotation": "rotation of the free object's body from its reset orientation, rad",
    "base_contacts": "fingers in contact (> 0.005 N) with the object's body / controller shell",
    "mechanism_contacts": "fingers in contact (> 0.005 N) with the moving mechanism (top layer / thumbstick)",
    "top_turn": "angle of the cube's top layer relative to its body, rad",
    "joystick_x": "thumbstick gimbal angle about its first axis, rad",
    "joystick_y": "thumbstick angle about its second axis, rad",
    "object_displacement": "object displacement from its reset position in the palm frame, m",
    "object_height": "height of the object's centre above the world origin, m (the table top is at 0.10 m)",
    "object_hand_contacts": "contacts (> 0.005 N) between the object and any hand link",
    "contacts": "fingers whose fingertip pad touches a task object (> 0.01 N)",
    "cube_error_1": "rotation between the marked sphere (palm frame) and its target after the first quarter turn, rad",
    "cube_error_2": "rotation between the marked sphere (palm frame) and its target after the second quarter turn, rad",
    "cube_error_3": "rotation between the marked sphere (palm frame) and its reset orientation, rad",
    "pen_axial": "pen displacement along its reset axis in the palm frame, m",
    "pen_angle": "angle between the pen axis and its reset axis in the palm frame, rad",
    "pen_grip_contacts": "fingers whose fingertip pad touches the pen inside the painted grip band (> 0.01 N)",
    "pen_palm_contacts": "palm contacts with the pen (> 0.01 N)",
    "pen_initial_palm_contacts": "palm contacts with the pen in the frozen reset (constant)",
    "pen_initial_horizontal_error": "inclination of the pen in the frozen reset, rad (constant)",
    "turn": "unwrapped knob angle, rad",
    "rotor_hand_contacts": "contacts (> 0.005 N) between the knob and the hand",
    "rotor_fingers": "fingers touching the knob (> 0.005 N)",
    "rotor_handoffs": "finger-set handoffs on the knob (a new set sharing a finger with the previous one, stable 40 ms)",
    "ball_pair_contacts": "contacts between the two walnuts",
    "deposit_support_a": "contacts between walnut A and the catch-tray floor",
    "a_deposit_distance": "horizontal distance of walnut A from the catch-tray centre, m",
    "a_height": "height of walnut A's centre, m (the tray floor is at about 0.155 m, the table top at 0.10 m)",
}
for _label, _name in (("a", "walnut A"), ("b", "walnut B")):
    FEATURES.update({
        f"{_label}_position_error": f"{_name} displacement from its reset position in the palm frame, m",
        f"{_label}_orientation_error": f"{_name} rotation from its reset orientation in the palm frame, rad",
        f"{_label}_hand_contacts": f"contacts (> 0.005 N) between {_name} and the hand",
        f"{_label}_finger_contacts": f"fingers touching {_name} (> 0.005 N)",
        f"{_label}_support": f"contacts (> 0.005 N) between {_name} and the environment",
        f"{_label}_linear_speed": f"{_name} linear speed, m/s",
        f"{_label}_angular_speed": f"{_name} angular speed, rad/s",
    })
FEATURES["a_quarter_turn_error"] = "rotation between walnut A and its +90 degree target about the declared axis, rad"
ESSENTIAL_WIDTHS = {"sharpa": 28, "wuji": 26}


def _bound(name: str, interval) -> str:
    lo, hi = interval
    fmt = lambda v: f"{v:.6g}"  # noqa: E731
    if lo is not None and hi is not None:
        return f"`{fmt(lo)} <= {name} <= {fmt(hi)}`" if lo != hi else f"`{name} == {fmt(lo)}`"
    return f"`{name} >= {fmt(lo)}`" if lo is not None else f"`{name} <= {fmt(hi)}`"


def predicate_section(spec: dict, mode: str = "privileged") -> str:
    """The exact ordered predicate of a frozen essential instance, rendered from its catalog entry."""
    where = ("the exact numbers are in `catalog.json` in `/opt/tools`" if mode == "privileged" else
             "the verifier uses the frozen task's unrounded values, which differ from these only beyond the sixth "
             "significant digit")
    lines = ["## Success predicate",
             "The verifier evaluates these conditions on features it computes from simulator state (values rounded "
             f"to six significant digits here; {where}). A stage or the terminal "
             "condition counts a control sample only if its bounds held at every 2 ms physics substep of that "
             "control interval; stages are completed in order and each starts after the previous one.", ""]
    for index, stage in enumerate(spec["stages"], 1):
        text = ", ".join(_bound(k, v) for k, v in stage["bounds"].items())
        lines.append(f"{index}. Stage `{stage['name']}`: {text}, for {stage['hold_steps']} consecutive control samples.")
        if stage.get("guards"):
            lines.append("   While this stage is active (fail-fast): "
                         + ", ".join(_bound(k, v) for k, v in stage["guards"].items()) + ".")
    terminal = spec["terminal"]
    lines.append(f"{len(spec['stages']) + 1}. Terminal hold after the last stage: "
                 + ", ".join(_bound(k, v) for k, v in terminal["bounds"].items())
                 + f", for {terminal['hold_steps']} consecutive control samples."
                 + (" Guards: " + ", ".join(_bound(k, v) for k, v in terminal["guards"].items()) + "."
                    if terminal.get("guards") else ""))
    lines += ["", "Invariants, checked at every physics substep for the whole episode (fail-fast): "
              + ", ".join(_bound(k, v) for k, v in spec.get("invariants", {}).items()) + ".", "",
              "The first violated invariant or guard, a non-finite feature or unstable physics fails the episode "
              "immediately and permanently: the episode ends there and later rows are not executed, so a dropped, "
              "slipped or knocked-away object can never be recovered"
              + (" in that episode (a reset starts a new one: `## Episodes and resets`)" if mode == "standard" else "")
              + ". Success is reached when the terminal hold "
              "completes; the episode ends there too. Completing only some stages is a failure.", "",
              "Feature definitions:"]
    used = list(dict.fromkeys(
        [k for stage in spec["stages"] + [terminal] for k in list(stage["bounds"]) + list(stage.get("guards", {}))]
        + list(spec.get("invariants", {}))))
    for name in used:
        lines.append(f"- `{name}`: {FEATURES.get(name, 'see scene.py')}")
    return "\n".join(lines) + "\n"


def solution_label(source: Path, code: bool = False, folder: str = "solution/") -> str:
    q = "`" if code else ""
    if source.suffix == ".json":
        parts = len(json.loads(source.read_text())["parts"])
        return (f"{q}{folder}trajectory.json{q} with its {parts} parts ({q}trajectory.partNN.npz{q}, concatenated in "
                f"order and sha256-checked by the oracle)")
    return f"{q}{folder}trajectory.npz{q}"


def solution_rows(source: Path) -> int:
    if source.suffix == ".json":
        return int(json.loads(source.read_text())["rows"])
    import numpy as np

    with np.load(source, allow_pickle=False) as archive:
        return int(archive["actions"].shape[0])


def offered_hands(family: str) -> tuple[list[str], str]:
    """An essential family's hands (task_library/<family>/offered_hands.json, copied into its runtime), else both."""
    path = LIBRARY / family / "offered_hands.json"
    if path.is_file():
        value = json.loads(path.read_text())
        return list(value["hands"]), str(value.get("reason", ""))
    return ["sharpa", "wuji"], ""


def sharpa_only_hands(mode: str, reason: str) -> str:
    """Hands + Action rows of an essential family that offers only the Sharpa Wave."""
    lines = ["## Action rows",
             "Rows are 28 wide: the six wrist targets, then `right_thumb_CMC_FE, right_thumb_CMC_AA, right_thumb_MCP_FE, "
             "right_thumb_MCP_AA, right_thumb_IP`, `right_<index|middle|ring>_MCP_FE, _MCP_AA, _PIP, _DIP` and "
             "`right_pinky_CMC, _MCP_FE, _MCP_AA, _PIP, _DIP`. The fingers use the dissipative velocity coefficient "
             "declared in the frozen instance and start from its declared finger pose."]
    if mode == "privileged":
        lines.append("`s.actuator_names` gives the exact order. `s.save_trajectory(actions, path)` records the hand in "
                     "the archive (`hand` member); the verifier replays the rows with the Sharpa Wave and rejects an "
                     "archive of another width or labelled with another hand.")
    else:
        lines.append("`spec()[\"hand\"]` names the hand, and `spec()[\"action_types\"][\"joint_position\"]` gives "
                     "the row width (`28`) and the exact order.")
    return sharpa_only_section(reason) + "\n" + "\n".join(lines) + "\n"


def essential_manifest(spec: dict) -> dict | None:
    """The six fixed-wrist families declare hands and the packaged oracle like a plugin family."""
    if not spec["id"].startswith("essential_"):
        return None
    solution = LIBRARY / spec["id"] / "solution/trajectory.json"
    if not solution.is_file():
        solution = LIBRARY / spec["id"] / "solution/trajectory.npz"
    offered = offered_hands(spec["id"])[0]
    manifest = {"hands": offered, "action_dim": {hand: ESSENTIAL_WIDTHS[hand] for hand in offered},
                "robot": "sharpa-wave-floating",
                "metadata": {"oracle": "none", "oracle_evidence": ESSENTIAL_EVIDENCE}}
    if solution.is_file():
        rows = solution_rows(solution)
        manifest["solution"] = solution
        manifest["hand_solutions"] = hand_solutions(solution, manifest["action_dim"], spec["id"])
        manifest["metadata"] = {
            "oracle": "full",
            "oracle_evidence": (
                f"{solution_label(solution)} is the validated Sharpa Wave actuator trajectory of this frozen instance "
                f"({rows} controls at 50 Hz, physical contact only). The privileged oracle hands it in; the standard "
                "oracle submits the same rows as float64 through the client's request path (the service executes the "
                "validated targets bit for bit). Both replay to success in two fresh processes with identical final "
                "state hashes (scripts/dexhand/verify_oracles.py); float32-rounded copies of all six oracles also score "
                "1. Human solvability review is pending; release status stays provisional."
            ),
        }
    return manifest


ARCHIVE_MAX_BYTES = int(re.search(r"^MAX_BYTES = ([\d_]+)", (SHARED / "grade.py").read_text(), re.M).group(1))
ARCHIVE_NOTE = (f"Save the archive compressed (`numpy.savez_compressed`; `s.save_trajectory` does): an archive file larger "
                f"than {ARCHIVE_MAX_BYTES // 1_000_000} MB is rejected with reward 0.")


def with_archive_note(text: str) -> str:
    """End a privileged instruction's Deliverable section with the archive limit (one number: shared/grade.py)."""
    start = text.find("\n## Deliverable\n")
    if start < 0:
        raise ValueError("privileged instruction without a ## Deliverable section")
    end = text.find("\n## ", start + 5)
    end = len(text) if end < 0 else end
    return text[:end].rstrip("\n") + "\n" + ARCHIVE_NOTE + "\n" + text[end:]


def write(path: Path, value: str, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value)
    path.chmod(0o755 if executable else 0o644)


def copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    target.chmod(0o755 if source.suffix == ".sh" else 0o644)


def tooling_source(name: str) -> Path:
    """Resolve shared utilities and independently owned task scene modules."""
    if name == "essential_registry.json":
        return LIBRARY / "index.json"
    for entry in json.loads((LIBRARY / "index.json").read_text())["tasks"]:
        if name == entry["module"] + ".py":
            return LIBRARY / entry["id"] / "scene.py"
    return SHARED / name


def copy_object_assets(spec: dict, folder: Path) -> None:
    """Package only declared offline mesh/texture/credit files, never policies."""
    assets = LIBRARY / spec["id"] / "assets"
    manifest = assets / "manifest.json"
    if not manifest.is_file():
        return
    for name in json.loads(manifest.read_text()).get("runtime_files", []):
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"Unsafe object asset path: {name}")
        target = folder / "object_assets" / spec["id"] / relative
        copy(assets / relative, target)
        if relative.suffix.lower() == ".obj":
            first, separator, geometry = target.read_bytes().partition(b"\n")
            # Omit the converter's automatic code URL from runtime copies.
            # All geometry/UV bytes and the artist's separate credits remain.
            if separator and first.rstrip(b"\r") == b"# https://github.com/mikedh/trimesh":
                target.write_bytes(geometry)


def resources(mode: str) -> str:
    standard = mode == "standard"
    return f'''[metadata.resources]
min_cpus = 2.0
min_memory_gb = 2.0
min_gpu_memory_gb = 0.0
gpu_required = false
gpu_class = "none"
verifier_min_cpus = 2.0
verifier_min_memory_gb = 2.0
verifier_min_gpu_memory_gb = 0.0
measured = "Conservative CPU-only allocation; local model validation and sample Docker smoke checks are recorded in docs/benchmarks/dexhand.md. Full agent-trial resource calibration remains pending."

[metadata.resources.limits]
scope = "{"agent" if standard else "trial"}"
max_gpu_memory_gb = 0.0
max_memory_gb = 8.0
max_processes = 512
max_disk_gb = 10.0
disk_paths = ["/app", "/tmp", "/root"]
disk_exclude = []
sustain_sec = 60.0
window_sec = 120.0
trial_max_gpu_memory_gb = 0.0
trial_max_memory_gb = {16.0 if standard else 8.0}
measured = "Conservative design defaults; no container peak measurement is claimed."

[metadata.resources.caps]
main = {{ cpus = 2.0, memory_gb = 10.0, pids = 8192 }}
{"sim = { cpus = 2.0, memory_gb = 8.0, pids = 8192 }" if standard else ""}
'''


def toml(spec: dict, mode: str, name: str, manifest: dict | None = None) -> str:
    """task.toml; a plugin family (manifest given) declares its own robot, hands, oracle and timeouts."""
    standard = mode == "standard"
    meta = (manifest or {}).get("metadata", {})
    timeouts = (manifest or {}).get("timeouts", {})
    artifacts = ['"/app/output/"']
    if standard:
        artifacts += [
            f'{{ source = "/data/{file}", service = "sim" }}'
            for file in (
                "final.json",
                "episode.jsonl",
                "trajectory.npz",
                "replay.mp4",
                "server.log",
                "journal.f64",
                "startups.jsonl",
                "video.json",
                "video.log",
            )
        ]
    evidence = (
        "An authoring-only native actuator controller and fresh replay checks live in "
        "scripts/dexhand/families/assemble_hamburger/. No oracle is packaged; independent human review "
        "and agent-trial calibration remain required before scored release."
        if spec["id"] == "assemble_hamburger"
        else ESSENTIAL_EVIDENCE
        if spec["id"].startswith("essential_")
        else EVIDENCE
    )
    if spec["id"] in daily_folders():
        evidence = (
            "Household extension scenes have ordered native-state predicates and declared reduced material models. "
            "Authoring probes are recorded separately; successful actuator policies, human solvability review and "
            "agent-trial calibration remain required. No successful policy is claimed or packaged."
        )
    oracle = "none"
    robot = 'robot = "sharpa-wave-floating"'
    keywords = ["robotics", "dexterous-hand", "mujoco", "sharpa-wave", spec["category"]]
    if manifest is not None:
        oracle = meta.get("oracle", "none")
        evidence = meta.get("oracle_evidence", "")
        if manifest.get("hand_solutions"):
            evidence = (evidence + " " + hand_solution_text(manifest["hand_solutions"])).strip()
        robot = (f'robot = {json.dumps(manifest.get("robot", "sharpa-wave-floating"))}\n'
                 f'hands = {json.dumps(manifest.get("hands", ["sharpa", "wuji"]))}\ndefault_hand = "sharpa"')
        keywords = ["robotics", "dexterous-hand", "mujoco", "sharpa-wave"]
        keywords += ["wuji-hand-2.2"] if "wuji" in manifest.get("hands", ["sharpa", "wuji"]) else []
        keywords += [spec["category"]] + meta.get("keywords", [])
        keywords = list(dict.fromkeys(keywords))
    evidence_line = "" if oracle == "full" and not evidence else f"oracle_evidence = {json.dumps(evidence)}\n"
    return f'''# Generated by scripts/dexhand/generate.py.
schema_version = "1.3"
artifacts = [{", ".join(artifacts)}]

[task]
name = "robot-coding-bench/{name}"
description = {json.dumps(spec["description"])}
authors = [{{ name = "Embodied Exam contributors" }}]
keywords = {json.dumps(keywords)}

[metadata]
author_name = "Embodied Exam contributors"
task_type = "trajectory"
simulator = "mujoco"
{robot}
family = "{spec["id"]}"
mode = "{mode}"
{'protocol = "eai-standard/2.2"' if standard else ""}
oracle = "{oracle}"
{evidence_line}expert_time_estimate_hours = {float(meta.get("expert_time_estimate_hours", 2.0))}
difficulty = "{spec["difficulty"]}"
release_status = "{spec.get("release_status", "provisional")}"

{resources(mode)}
[verifier]
timeout_sec = {float(timeouts.get("verifier_standard_sec", 600.0)) if standard else float(timeouts.get("verifier_privileged_sec", 3600.0))}
environment_mode = "separate"
network_mode = "no-network"

{
        f"""# The agent's time is up: stop whatever it left running in its container. Harbor stops that container only after
# collecting from it (~12 s), and a script still running there would keep driving the robot past the deadline.
[[verifier.collect]]
service = "main"
command = "kill -9 -1 2>/dev/null; exit 0"
timeout_sec = 30

[[verifier.collect]]
service = "sim"
command = "sh /srv/finalize.sh"   # end the episode, write its live verdict (no replay), then one video pass
timeout_sec = {std_collect_s(manifest)}                # the end wait, the video and a margin (generate.py std_collect_s)
"""
        if standard
        else ""
    }
[agent]
timeout_sec = {float(CUTOFF[mode])}
network_mode = "allowlist"
allowed_hosts = {json.dumps(ALLOWED_HOSTS)}

[environment]
build_timeout_sec = 1800.0
cpus = 2
memory_mb = 10240
'''


ESSENTIAL_LAYOUT = (
    "Sharpa rows: the six wrist targets, then `right_thumb_CMC_FE, right_thumb_CMC_AA, right_thumb_MCP_FE, "
    "right_thumb_MCP_AA, right_thumb_IP`, `right_<index|middle|ring>_MCP_FE, _MCP_AA, _PIP, _DIP` and "
    "`right_pinky_CMC, _MCP_FE, _MCP_AA, _PIP, _DIP`. Wuji rows: the same six wrist targets, then "
    "`r_wuji_r_THJ0..3` (thumb CMC flexion, CMC abduction, MCP, IP) and `r_wuji_r_FFJ0..3`, `MFJ0..3`, `RFJ0..3`, "
    "`LFJ0..3` (index, middle, ring, pinky: MCP flexion, MCP abduction, PIP, DIP). Both hands are mounted in the "
    "same wrist frame; Sharpa fingers use the dissipative velocity coefficient declared in the frozen instance, "
    "Wuji fingers the manufacturer's position servos. Sharpa starts from the instance's declared finger pose; Wuji "
    "starts from the pose in `wuji_reset.json` (neutral fingers when the file is absent), an authoring choice that "
    "keeps the object held at reset, not a policy. The wrist, fixtures and predicate are identical for both hands; "
    "where a Wuji grasp cannot hold an object at the Sharpa start pose, `wuji_reset.json` also declares the held "
    "objects' start poses in the Wuji grasp, and every reset-relative quantity is measured from the post-reset pose."
)


def instruction(spec: dict, mode: str) -> str:
    essential_family = spec["id"].startswith("essential_")
    only_sharpa = essential_family and offered_hands(spec["id"])[0] == ["sharpa"]
    hand_line = (
        "You control one dexterous hand on a six-DoF wrist positioning stage: a Sharpa Wave hand with 22 independently\n"
        "actuated finger joints (see Hands)."
        if only_sharpa
        else "You control one dexterous hand on a six-DoF wrist positioning stage: a Sharpa Wave hand with 22 independently\n"
        "actuated finger joints (the default) or a Wuji Hand 2.2 with 20 (see Hands)."
        if essential_family
        else "You control a Sharpa Wave hand with 22 independently actuated finger joints and a six-DoF wrist positioning stage."
    )
    intro = f"""# DexHand: {spec["title"]}

{spec["instruction"]}

{hand_line}
The wrist stage is position actuated in the physics engine; grasping and manipulating require physical contact.
The five fingers are thumb, index, middle, ring and pinky. The controller runs at 50 Hz, with ten 2 ms physics substeps.
"""
    if essential_family:
        wrist = spec["parameters"].get("initial_wrist", [-0.08, 0, 0.29, 0, 0, 0])
        intro += f"""
This is a fixed-wrist essential dexterity task. Native equality constraints lock all six wrist joints.
The first six entries of every action MUST remain {json.dumps(wrist)}.
Float32 wire-format rounding is accepted and normalized to those exact fixed targets before physics runs.
Use the declared target values rather than copying measured wrist joint positions. Only the finger targets may
change. Objects have no actuators, scripted motion or grasp attachments; they move through contact and normal gravity.

{sharpa_only_hands(mode, offered_hands(spec["id"])[1]) if only_sharpa else hands_section(ESSENTIAL_WIDTHS, mode, ESSENTIAL_LAYOUT)}
{predicate_section(spec, mode)}"""
    if mode == "privileged":
        text = (
            intro
            + f'''
## Deliverable
Save `/app/output/trajectory.npz`, a numeric `actions` array of shape `(T, 28)` with at most 50,000 rows,
and `/app/output/gen.py`, the script that produced it. Each row is one control step: wrist x/y/z targets in metres,
wrist XYZ Euler joint targets in radians, then the 22 Sharpa Wave joint targets in actuator order. Do not save object
states as the deliverable: the verifier executes the actions from the frozen start twice in fresh processes.
NaN, infinity, object arrays and malformed or oversized trajectories are rejected.

## Tooling
```python
from rcb_dexhand import Session
s = Session("{spec["id"]}")
s.joint_names                 # action/proprioception order, 28 joint names
s.state()                     # privileged qpos, qvel, ctrl, object poses and checker features
s.status()                    # success, done, reason, steps, stage, total_stages, state_sha
s.render_frame("overview")    # uint8 RGB 480 x 640; cameras: s.cameras()
s.reset()                     # exact frozen reset; unlimited during development
s.step(action28)              # execute one position-target row
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.replay(actions)             # reset, execute rows and recompute the predicate
```
Tooling lives in `/opt/tools`. Read `catalog.json`, `scene.py` and `checker.py` for the physical scene and exact
predicate. Wrist XYZ targets are positions of the stage joints in the world frame, metres, z up; the rotational
targets are serial XYZ revolute joints, not a quaternion. Finger position targets are in radians.

Success requires every ordered stage and the terminal hold to pass, with every invariant respected throughout the
episode. A held condition is consecutive control samples, and each stage starts collecting evidence after the previous
stage. Safety features include the maximum over the physics substeps. A terminal success ends the replay immediately,
so later rows cannot invalidate it; this preserves the completion of ordered mechanisms whose states may be transient.
'''
        )
        if spec["id"] == "assemble_hamburger":
            return (
                intro
                + """
## Deliverable
Save `/app/output/trajectory.npz` with a finite numeric `actions` array of shape `(T, 28)`, at most 7,500 rows,
and `/app/output/gen.py`, the script that produced it. Each row is one 50 Hz control: three wrist translations
in metres, three serial wrist XYZ rotation targets in radians, then the 22 finger targets in native actuator order.
The separate verifier starts from its own frozen scene and replays only these motor targets in two fresh processes.
Object poses, configuration overrides, pickled arrays and agent-written success claims are not deliverables.

## Tooling
```python
from rcb_dexhand import Session
s = Session("assemble_hamburger")
s.hold_action()                # current 28 motor targets
s.model.actuator_ctrlrange     # native target limits
s.model                       # privileged MuJoCo model
s.data                        # privileged MuJoCo state
s.features()                  # positions, alignment, contact graph, motion and bending diagnostics
s.status()                    # success, done, steps and layer count
s.step(action28)              # run ten 2 ms physics substeps
s.render_frame("overview")    # RGB uint8 (480, 640, 3); also "closeup"
s.reset()                     # exact frozen reset
```
Read `/opt/tools/task.json`, `scene.py` and `runtime.py` for the complete geometry and predicate.
Use the world frame with z up. The hand and wrist are position-actuated under native force bounds.
The last replay state must satisfy the complete released-hold predicate; later rows can invalidate a success.
"""
            )
        if spec["id"] in daily_folders():
            text = text.replace(
                "`catalog.json`, `scene.py` and `checker.py`",
                "`catalog.json`, `common_scene.py`, `task_scene.py`, `materials.py` and `checker.py`",
            )
        if essential_family:
            text = essential_privileged(text, spec, only_sharpa)
        return text
    text = (
        intro
        + "\n" + RESETS_SECTION + """
## Robot service
The simulator runs in a separate service. You receive camera RGB, optional calibrated depth, and the robot's own
joint positions, velocities, actuator efforts, wrist pose and current targets. A failure ends an episode at once; a
reset starts a new one (see `## Episodes and resets`). The service records every action and watch step, then judges
the graded episode as it ran (that is the verdict; nothing is replayed). Leave your controller at `/app/output/gen.py`;
no trajectory hand-in is needed.

```python
from rcb_client import Robot
r = Robot()
spec = r.spec()
obs = r.get_obs(cameras=["overview"], depth=True)
obs.last["overview"]           # RGB uint8 (480, 640, 3)
obs.last_depth["overview"]     # z-depth in metres
obs.meta["proprio"]            # named robot measurements
q = obs.group("joint_pos", now=True)
res = r.submit("joint_position", rows, dt=0.02, interpolate="hold", video="none")
r.fk(q)                       # robot-link forward kinematics; no physics is stepped
r.status()
res.save("/app/runs/001")
```
`rows` is `(T, 28)` in `spec["action_types"]["joint_position"]["layout"]` order: wrist XYZ translations (metres),
three serial XYZ rotational joints (radians), then 22 finger joints (radians). Actuator targets are clipped to the
published joint limits and clipping is reported. `dt` must be a multiple of 0.02 s, between 0.02 and 0.5 s; a chunk
covers at most 10 s. Hold interpolation holds each row for `dt`; linear interpolation starts from the previous target.
The robot has no scalar gripper opening. Quaternions in measured poses use WXYZ; world z is up. Cameras are overview,
side and palm, at 640 x 480. Requests can return RGB frames or mp4, with depth `none`, `last` or `frames`. Each call
returns at most 1,000 camera images, counting per-frame depth; reduce cameras, fps or duration for larger chunks.
`get_obs(seconds=...)` holds the current targets for up to 30 s and records those steps. Calling it without seconds
only observes the current state. Forward kinematics uses only the robot's own links; no IK primitive is supplied.
If the service connection fails, call `r.wait_ready()` and inspect `r.status()` before continuing. Crash recovery
resumes the same journaled episode, without a reset, and the wall-clock budget keeps running.
"""
    )
    if spec["id"] == "assemble_hamburger":
        text = text.replace("Cameras are overview,\nside and palm", "Cameras are overview and closeup")
    if essential_family:
        text = _swap(text, "Cameras are overview,\nside and palm, at 640 x 480.", ESSENTIAL_CAMERAS)
        text = _swap(text, 'obs = r.get_obs(cameras=["overview"], depth=True)',
                     'obs = r.get_obs(cameras=["overview", "inhand_top"], depth=True)')
    if essential_family and not only_sharpa:
        text = _swap(text, "`rows` is `(T, 28)` in", "`rows` is `(T, 28)` (Sharpa) or `(T, 26)` (Wuji) in")
        text = _swap(text, "then 22 finger joints (radians).", "then the 22 or 20 finger joints (radians).")
    return text


ESSENTIAL_CAMERAS = (
    "Cameras are overview,\nside, palm (behind the hand), and two close-ups of the held object, `inhand_top` (from above "
    "the palm)\nand `inhand_side` (from the thumb side), at 640 x 480; the default is overview and inhand_top. No "
    "object state is\npublished: the close-ups (with depth and their calibration) are how you see the object in the "
    "hand.")


def _swap(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"instruction template drift: {old!r}")
    return text.replace(old, new)


def essential_privileged(text: str, spec: dict, only_sharpa: bool = False) -> str:
    """Hand-aware deliverable/tooling wording for the fixed-wrist essential families."""
    family = spec["id"]
    if only_sharpa:
        text = _swap(text, """Save `/app/output/trajectory.npz`, a numeric `actions` array of shape `(T, 28)` with at most 50,000 rows,
and `/app/output/gen.py`, the script that produced it. Each row is one control step: wrist x/y/z targets in metres,
wrist XYZ Euler joint targets in radians, then the 22 Sharpa Wave joint targets in actuator order.""",
                     """Save `/app/output/trajectory.npz` with a numeric `actions` array of shape `(T, 28)` (at most 50,000 rows),
as written by `s.save_trajectory`, and `/app/output/gen.py`, the script that produced it. Each row is one control
step: wrist x/y/z targets in metres, wrist XYZ Euler joint targets in radians, then the 22 Sharpa Wave finger targets
in `s.actuator_names` order.""")
        text = _swap(text, f"""s = Session("{family}")
s.joint_names                 # action/proprioception order, 28 joint names""",
                     f"""s = Session("{family}")
s.action_dim, s.actuator_names  # 28; action order (s.joint_names: the joint each target drives)""")
    else:
        text = _swap(text, """Save `/app/output/trajectory.npz`, a numeric `actions` array of shape `(T, 28)` with at most 50,000 rows,
and `/app/output/gen.py`, the script that produced it. Each row is one control step: wrist x/y/z targets in metres,
wrist XYZ Euler joint targets in radians, then the 22 Sharpa Wave joint targets in actuator order.""",
                 """Save `/app/output/trajectory.npz` with a numeric `actions` array of shape `(T, 28)` for Sharpa or `(T, 26)`
for Wuji (at most 50,000 rows) and the `hand` it was made for, as written by `s.save_trajectory` (an archive
without `hand` is replayed as Sharpa), and `/app/output/gen.py`, the script that produced it. Each row is one
control step: wrist x/y/z targets in metres, wrist XYZ Euler joint targets in radians, then the finger targets in
`s.actuator_names` order.""")
        text = _swap(text, f"""s = Session("{family}")
s.joint_names                 # action/proprioception order, 28 joint names""",
                     f"""s = Session("{family}")      # or Session("{family}", hand="wuji")
s.hand, s.action_dim          # "sharpa", 28 (or "wuji", 26)
s.actuator_names              # action order; s.joint_names: the joint each target drives""")
    text = _swap(text, "s.step(action28)              # execute one position-target row",
                 "s.step(row)                   # execute one position-target row")
    text = _swap(text, """
Success requires every ordered stage and the terminal hold to pass, with every invariant respected throughout the
episode. A held condition is consecutive control samples, and each stage starts collecting evidence after the previous
stage. Safety features include the maximum over the physics substeps. A terminal success ends the replay immediately,
so later rows cannot invalidate it; this preserves the completion of ordered mechanisms whose states may be transient.
""", "")
    return text


def readme(spec: dict, mode: str, name: str) -> str:
    twin = name.removesuffix(mode) + ("standard" if mode == "privileged" else "privileged")
    if spec["id"] in daily_folders():
        from daily.templates import readme as daily_readme

        return daily_readme(spec, mode, name, twin, IMAGE)
    if spec["id"] == "assemble_hamburger":
        return f"""# {name}

| | |
|---|---|
| Benchmark | DexHand |
| Mode | {mode} |
| Twin | `{twin}` |
| Simulator / robot | MuJoCo 3.4.0, CPU / Sharpa Wave 22 joints + six-DoF actuated wrist |
| Family / instance | `assemble_hamburger` / i00 |
| Oracle | none; authoring controller available, independent review required |
| Agent time budget | {CUTOFF[mode]} s |
| Base image | `{IMAGE}` |

## Task
{spec["instruction"]}

## Difficulty
Thin layers need controlled contact pickup and release, and later placements must preserve the earlier layers.
The full predicate checks all six centers, the complete recipe, five neighboring contacts and a released stable hold.

## Reference solution
No packaged oracle. An authoring-only contact controller and recording tool live under
`scripts/dexhand/families/assemble_hamburger/`; neither is copied into the agent's environment or image.

## Verification
{"The isolated verifier replays numeric motor targets twice in fresh processes." if mode == "privileged" else STANDARD_GRADING}
{"Both replays must pass and have identical final integration state hashes." if mode == "privileged" else ""}
The frozen recipe comes from the task, never from an agent archive. A no-op fails.
Human review and full agent-trial calibration remain pending; report this task as provisional.

## Details
Source: `scripts/dexhand/families/assemble_hamburger/`, generated by `scripts/dexhand/generate.py`.
The existing offline Sharpa Wave assets are pinned to MuJoCo Menagerie commit
`0059d4335f8156206f63a35662313385f7ad6d74` (Apache-2.0), derived from Sharpa Robotics commit
`6eea427eb24189519f32b9f21674cd534d3f973c`. Finger inertias, geometry, limits and effort bounds are retained.
Ingredient visuals are original procedural geometry. Bun halves, patty and tomato have rigid cylinder contacts;
cheese and lettuce have three passive elastic strips. This is an articulated approximation of thin-sheet bending,
not continuum soft-food, crushing or tearing simulation. The bottom bun starts on the plate; preparation supports
give access to the other ingredients. This is assembly feasibility, not a gripper-superiority or zero-shot claim.
"""
    if spec["id"].startswith("essential_"):
        return essential_readme(spec, mode, name, twin)
    return f"""# {name}

| | |
|---|---|
| Benchmark | DexHand |
| Mode | {mode} |
| Twin | `{twin}` |
| Simulator / robot | MuJoCo 3.4.0, CPU / Sharpa Wave 22 joints + six-DoF actuated wrist |
| Family / instance | `{spec["id"]}` / i00 |
| Oracle | none; provisional solvability, human review required |
| Agent time budget | {CUTOFF[mode]} s |
| Base image | `{IMAGE}` |

## Task
{spec["instruction"]}

## Difficulty
{spec["difficulty"]}: {spec["description"]}
The scene uses {spec["mechanism"]} and independently controlled fingers; completing a two-finger lift alone does
not satisfy the ordered predicate.

## Reference solution
No low-level oracle is provided. Checker state fixtures exercise intended positive and negative predicate cases.
These fixtures validate logical recognition; they do not demonstrate a realizable action trajectory.

## Verification
{"The separate verifier replays the submitted numeric rows twice in fresh processes." if mode == "privileged" else STANDARD_GRADING}
Success requires all ordered stage holds and the terminal hold, and no invariant violation.{" Repeated final hashes must agree." if mode == "privileged" else ""} `nop` and wrong-state controls are checked by the
validation tooling. Missing standard service artifacts are infrastructure errors. No oracle; human review and a
review PR number remain pending. Every task is provisional and must be reported separately until solvability review.

## Details
Source: `scripts/dexhand/`; the image recipe is `images/dexhand/`. Both modes use identical frozen `instance.json`.
The Sharpa Wave model and all visual/contact meshes are pinned to MuJoCo Menagerie commit
`0059d4335f8156206f63a35662313385f7ad6d74` (Apache-2.0), derived from Sharpa Robotics
`sharpa-urdf-usd-xml` commit `6eea427eb24189519f32b9f21674cd534d3f973c`. Original joint limits, contact
geometry and inertias are retained; a six-DoF wrist stage mounts the hand. This is a wrist-stage dexterity benchmark.
No upstream policies or demonstrations are included. Renderer output is evidence; it never determines the verdict.
"""


WUJI_DETAILS = (
    "Wuji Hand 2.2 is the manufacturer's `hand2/hand2_2` model\nfrom `wuji-technology/wuji-description` commit "
    "`829c9aa27cb12c3a49d5b8d63c9869dd8f656702` (MIT), mounted unchanged in\nthe same wrist frame; its collision geoms "
    "are renamed to the predicate's finger/palm roles only.")
WUJI_DETAILS_PENDING = "Wuji Hand 2.2 support is pending for this family (`offered_hands.json`)."


def essential_readme(spec: dict, mode: str, name: str, twin: str) -> str:
    manifest = essential_manifest(spec)
    offered, why = offered_hands(spec["id"])
    only_sharpa = offered == ["sharpa"]
    oracle = manifest["metadata"]["oracle"]
    rows = solution_rows(manifest["solution"]) if manifest.get("solution") else None
    if rows:
        reference = (
            f"{solution_label(manifest['solution'], code=True)} is the validated Sharpa Wave actuator trajectory of this "
            f"frozen instance: {rows} "
            f"finger-target rows at 50 Hz ({rows / 50:.1f} s) with the six wrist targets locked, executed through physical "
            "contact only. "
            + ("`solve.sh` hands it in unchanged as `/app/output/trajectory.npz`."
               if mode == "privileged" else
               "`solve.sh` submits the same rows as float64 through the agent's client request path (`hold`, dt "
               "0.02 s), so the service executes the validated targets bit for bit; float32-rounded rows (the client's "
               "`submit`) also succeed.")
            + " It was derived offline by authoring controllers (not part of the repository) and is bound to "
            "the validated evidence by `scripts/dexhand/verify_oracles.py` (byte-identical trajectory, model hash, two "
            "fresh-process replays with the validated final state hash). "
            + (f"The Wuji Hand 2.2 is not offered in this family ({why})." if only_sharpa else
               hand_solution_text(manifest["hand_solutions"], mode) if manifest.get("hand_solutions") else
               "No Wuji trajectory is packaged: Wuji is selectable and graded identically, but not demonstrated.")
        )
        oracle_row = ("full (validated Sharpa Wave and Wuji Hand 2.2 trajectories); human review pending"
                      if manifest.get("hand_solutions") else "full (validated Sharpa Wave trajectory); human review pending")
    else:
        reference = "No low-level oracle is provided."
        oracle_row = "none; provisional solvability, human review required"
    verification = (
        "The separate verifier replays the submitted numeric rows twice in fresh processes, with the hand recorded "
        "in the archive." if mode == "privileged" else
        STANDARD_GRADING
    )
    return f"""# {name}

| | |
|---|---|
| Benchmark | DexHand |
| Mode | {mode} |
| Twin | `{twin}` |
| Simulator / robot | MuJoCo 3.4.0, CPU / {"Sharpa Wave (22 finger joints)" if only_sharpa else "Sharpa Wave (22 finger joints, default) or Wuji Hand 2.2 (20)"} on a locked six-DoF wrist stage |
| Family / instance | `{spec["id"]}` / i00 |
| Oracle | {oracle_row} |
| Agent time budget | {CUTOFF[mode]} s |
| Base image | `{IMAGE}` |

## Task
{spec["instruction"]}

## Difficulty
{spec["difficulty"]}: {spec["description"]}
The scene uses {spec["mechanism"]} and independently controlled fingers with the wrist locked; every ordered stage and
a terminal hold must be reached through contact alone.

## Reference solution
{reference}

## Verification
{verification}
Reward 1 needs every ordered stage and the terminal hold with no invariant or guard violation{PRIVILEGED_HASHES if mode == "privileged" else ""}. Invariants and guards are checked at every 2 ms
physics substep and fail the episode immediately (a dropped, slipped or knocked-away object ends it as a failure);
partial completion fails. Rows of the wrong width for the recorded hand, a forged or unknown hand label, non-finite
or out-of-range targets and wrist motion are rejected with reward 0. `scripts/dexhand/tests/test_essential_strict.py`
covers the oracle, no-op, truncated, dropped-object, forged-metadata and wrong-width cases{" (and the refusal of any other hand)" if only_sharpa else " for both hands"}.
Release status is provisional until independent solvability review.

## Details
Source: `scripts/dexhand/` (task folder `task_library/{spec["id"]}/`); the image recipe is `images/dexhand/`. Both
modes use the identical frozen `instance.json`. The Sharpa Wave model and meshes are pinned to MuJoCo Menagerie commit
`0059d4335f8156206f63a35662313385f7ad6d74` (Apache-2.0). {WUJI_DETAILS_PENDING if only_sharpa else WUJI_DETAILS} Object assets carry
their own licenses and checksums under `object_assets/`. Renderer output is evidence; it never determines the verdict.
"""


def compose(spec: dict, manifest: dict | None = None) -> str:
    """Standard-mode compose file; a family's `compose_env` overrides a default key instead of repeating it."""
    environment = {
        "RCB_TASK": spec["id"],
        "RCB_DATA": "/data",
        "RCB_WALL_CLOCK_S": f'"{CUTOFF["standard"]}"',
        "RCB_RESET_BUDGET": f'"${{RCB_RESET_BUDGET:-{RESET_BUDGET}}}"',
        "RCB_STARTUP_TIMEOUT_S": '"300"',
        "DEXHAND_HAND": "${DEXHAND_HAND:-sharpa}",
        "MUJOCO_GL": "osmesa",
        "PYOPENGL_PLATFORM": "osmesa",
        "OPENBLAS_NUM_THREADS": '"1"',
        "PYTHONPATH": "/srv",
    }
    for key, value in (manifest or {}).get("compose_env", {}).items():
        if key in ("RCB_TASK", "RCB_DATA", "DEXHAND_HAND", "PYTHONPATH"):
            raise ValueError(f"compose_env cannot override {key}")
        environment[key] = json.dumps(str(value))
    lines = "".join(f"      {key}: {value}\n" for key, value in environment.items())
    return f"""services:
  main:
    depends_on: [sim]
  sim:
    image: {IMAGE}
    volumes:
      - ./sim:/srv:ro
    working_dir: /tmp
    command: sh /srv/run.sh
    restart: on-failure:6
    environment:
{lines}"""


def all_specs(only: set[str] | None = None) -> list[tuple[dict, dict | None, Path | None]]:
    """Every family as (frozen spec, plugin manifest or None, plugin folder or None), in a stable order."""
    # The thirty development families (catalog.json) are not in every checkout: the release branch carries only the
    # families of release.json.
    catalog = json.loads((HERE / "catalog.json").read_text()) if (HERE / "catalog.json").is_file() else {"tasks": []}
    specs = [(spec, None, None) for spec in catalog["tasks"]]
    if (HERE / "essential_catalog.json").exists():
        specs += [(spec, None, None) for spec in json.loads((HERE / "essential_catalog.json").read_text())["tasks"]]
    plugins = plugin_folders()
    if (HAMBURGER / "task.json").exists() and "assemble_hamburger" not in plugins:
        specs.append((json.loads((HAMBURGER / "task.json").read_text()), None, None))
    for folder in daily_folders().values():
        specs.append((json.loads((folder / "task.json").read_text()), None, None))
    for family, folder in sorted(plugins.items()):
        manifest, spec = load_plugin(folder)
        specs.append((spec, manifest, folder))
    ids = [spec["id"] for spec, _, _ in specs]
    duplicates = sorted({x for x in ids if ids.count(x) > 1})
    if duplicates:
        raise ValueError(f"Families registered twice: {duplicates}")
    if only is not None:
        missing = sorted(only - set(ids))
        if missing:
            raise ValueError("Unknown family: " + ", ".join(missing))
        specs = [item for item in specs if item[0]["id"] in only]
    return specs


# The held-object rotation bound before 2026-10-14 (board 0109), for the README's change log.
HELD_ROTATION_BEFORE = {"essential_held_joystick": 0.24, "essential_cube_layer": 0.24}


def video_frame_budget(folder: Path | None) -> int | None:
    """A plugin family's replay-video frame budget (`VIDEO_MAX_FRAMES` in its replay.py, board 0136), if it has one."""
    replay = folder / "replay.py" if folder is not None else None
    if replay is None or not replay.is_file():
        return None
    match = re.search(r"^VIDEO_MAX_FRAMES = ([0-9_]+)", replay.read_text(), re.M)
    return int(match.group(1)) if match else None


def change_log(spec: dict, mode: str, frames: int | None = None) -> str:
    """The README's change log: what changed after the tasks were first proposed (pull request #185 or #241)."""
    lines = []
    if mode == "standard":
        lines.append(
            f"- 2026-10-14 (board 0109, before the first scored run): {RESET_BUDGET} resets in standard mode (owner; "
            "PROTOCOL §4.5, DexToolBench's value). `POST /reset` starts a new episode from the frozen start (the same "
            "state hash as a fresh process); only the last episode is graded, a success ends the trial; `reward.json` "
            "adds `resets` and `reset_budget`. Before, one trial was one episode.")
    if spec["id"].startswith("essential_"):
        lines.append(
            "- 2026-10-14 (board 0109): two close-up cameras of the held object, `inhand_top` (above the palm) and "
            "`inhand_side` (thumb side), mounted on the locked hand like `palm`; the standard service returns "
            "`overview` and `inhand_top` by default. Before, the object was 40-60 px wide in the overview and the palm "
            "camera saw the back of the hand, so its in-hand pose could hardly be observed in standard mode.")
    if frames is not None:
        # A family of pull request #241 (wave 2): its own replay.py films at most `frames` steps.
        lines.append(
            "- 2026-10-16 (board 0136, video only): "
            + ("the verifier renders the replay video (`/logs/verifier/replay.mp4`) with a third fresh replay after "
               "`reward.json` is written, in its remaining time. Before, the privileged verifier rendered no video."
               if mode == "privileged" else
               "the collect hook renders the replay video in its remaining time (timeout_sec minus 60 s, at most "
               "the video limit).")
            + f" The video films at most {frames} steps (a longer episode at a larger stride; an OSMesa frame of an "
            "arm scene takes up to ~3.6 s on two cores), and the video, verifier and collect limits cover the longest "
            "archive the row limit allows. The verdict, the replays and `reward.json` are unchanged.")
    else:
        lines.append(
            "- 2026-10-16 (board 0136, video only): "
            + ("the verifier renders the replay video (`/logs/verifier/replay.mp4`) with a third fresh replay after "
               "`reward.json` is written, in its remaining time. Before, the privileged verifier rendered no video."
               if mode == "privileged" else
               "the collect hook renders the replay video in its remaining time (timeout_sec minus 60 s) instead of a "
               "fixed 300 s, which cut the video of episodes longer than ~10k steps.")
            + (" The video films every 2nd step but at most 1500 frames (a 640x480 OSMesa frame takes ~0.3 s)."
               if spec["id"].startswith("essential_") else "")
            + " The verdict, the replays and `reward.json` are unchanged; earlier results stay valid.")
    if mode == "standard":
        lines.append(
            "- 2026-10-17 (owner, board 0150/0151): standard mode graded by the live episode; no grading replay; video "
            "by one render pass from the trajectory after the verdict. `success` is the sim service's own verdict on "
            "the episode it ran (the same predicate a replay recomputed: the same rows through the same step, a "
            "success ending the episode); the collect hook no longer replays it twice in fresh processes, and "
            "`final.json` / `reward.json` drop `replay_success`, `deterministic` and `live_matches_replay` "
            "(`graded_by = \"live\"`, `replays = 0`). The service checks the frozen instance's files against the "
            "generator's record when an episode begins (`instance_mismatch`, an infrastructure error). A collect "
            "hook on `main` (`kill -9 -1`) stops whatever the agent left running before the service ends the "
            "episode. The agent's "
            "side (the instruction's grading sentence aside), the scene and the predicate are unchanged.")
    if spec["id"] in HELD_ROTATION_BEFORE:
        bound = spec["invariants"]["body_rotation"][1]
        lines.append(
            f"- 2026-10-14 (board 0109): the held object's rotation bound (invariant `body_rotation`) "
            f"{HELD_ROTATION_BEFORE[spec['id']]} -> {bound} rad (20 degrees, both held-object families). The reference "
            "solution peaked at 0.2396 rad (joystick) and 0.218 rad (cube layer), within 0.0004 / 0.022 rad of the "
            "old bound, so the bound was effectively the reference's own peak; finger targets perturbed by +-0.001 rad "
            "peak at 0.25-0.30 rad. The task's intent (keep the held object steady) is unchanged.")
    return "\n### Change Log\n" + "\n".join(lines) + "\n" if lines else ""


def task_name(family: str, mode: str) -> str:
    return f"dexhand-{family.replace('_', '-')}-i00-{mode}"


def render(destination: Path, only: set[str] | None = None) -> list[Path]:
    tasks = []
    for spec, manifest, folder in all_specs(only):
        for mode in ("privileged", "standard"):
            name = task_name(spec["id"], mode)
            task = destination / name
            if task.exists():
                shutil.rmtree(task)
            if manifest is not None and manifest.get("metadata", {}).get("oracle", "none") != "none":
                manifest = {**manifest, "hand_solutions": hand_solutions(
                    _family_file(folder, manifest["solution"]["privileged"]), manifest["action_dim"], spec["id"],
                    manifest.get("max_rows"))}
            write(task / "task.toml", toml(spec, mode, name, manifest or essential_manifest(spec)))
            if manifest is not None:
                instruction_text, readme_text = plugin_texts(folder, manifest, spec, mode, name)
                write(task / "instruction.md", with_archive_note(instruction_text) if mode == "privileged" else instruction_text)
                write(task / "README.md", with_hand_solutions(readme_text, manifest.get("hand_solutions", {}), mode)
                      + change_log(spec, mode, video_frame_budget(folder)))
            else:
                text = instruction(spec, mode)
                write(task / "instruction.md", with_archive_note(text) if mode == "privileged" else text)
                write(task / "README.md", readme(spec, mode, name) + change_log(spec, mode))
            runtime_dirs = (
                [task / "environment", task / "tests"] if mode == "privileged" else [task / "environment/sim"]
            )
            for runtime in runtime_dirs:
                if manifest is not None:
                    copy_plugin_runtime(folder, manifest, runtime)
                elif spec["id"] in daily_folders():
                    for file in ("runtime.py", "common_scene.py", "materials.py", "replay.py"):
                        copy(DAILY / file, runtime / file)
                    copy(daily_folders()[spec["id"]] / "scene.py", runtime / "task_scene.py")
                    for file in ("checker.py", "rcb_dexhand.py", "hands.py"):
                        copy(SHARED / file, runtime / file)
                    copy(daily_folders()[spec["id"]] / "task.json", runtime / "task.json")
                elif spec["id"] == "assemble_hamburger":
                    for file in ("runtime.py", "scene.py", "replay.py", "task.json"):
                        copy(HAMBURGER / file, runtime / file)
                    for file in ("rcb_dexhand.py", "hands.py"):
                        copy(SHARED / file, runtime / file)
                else:
                    for file in TOOLING:
                        copy(tooling_source(file), runtime / file)
                    copy_object_assets(spec, runtime)
                    if (LIBRARY / spec["id"] / "wuji_reset.json").is_file():
                        copy(LIBRARY / spec["id"] / "wuji_reset.json", runtime / "wuji_reset.json")
                    if (LIBRARY / spec["id"] / "offered_hands.json").is_file():
                        copy(LIBRARY / spec["id"] / "offered_hands.json", runtime / "offered_hands.json")
                write(runtime / "catalog.json", json.dumps({"schema_version": 1, "tasks": [spec]}, indent=2) + "\n")
                write(runtime / "instance.json", json.dumps(spec, indent=2, sort_keys=True) + "\n")
                write(runtime / "grading.json",
                      grading(manifest) if mode == "privileged" else std_grading(manifest, runtime))
            if mode == "privileged":
                write(
                    task / "environment/Dockerfile",
                    f"""FROM {IMAGE}
COPY . /opt/tools/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
""",
                )
                write(
                    task / "tests/Dockerfile",
                    f"""FROM {IMAGE}
COPY . /tests/
ENV PYTHONPATH=/tests
RUN chmod +x /tests/test.sh
WORKDIR /tests
""",
                )
                copy(SHARED / "grade.py", task / "tests/grade.py")
            else:
                write(
                    task / "environment/Dockerfile",
                    f"""FROM {CLIENT_IMAGE}
COPY client-requirements.txt /tmp/client-requirements.txt
RUN pip install --no-cache-dir -r /tmp/client-requirements.txt
COPY rcb_client.py rcb1.py /opt/tools/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
""",
                )
                write(task / "environment/docker-compose.yaml", compose(spec, manifest))
                for file in ("rcb_client.py", "rcb1.py", "client-requirements.txt"):
                    copy(LAYER / file, task / "environment" / file)
                for file in ("rcb_limited.py", "rcb1.py", "run.sh"):
                    copy(LAYER / file, task / "environment/sim" / file)
                for file in ("server.py", "finalize.sh", "finalize.py"):
                    copy(SHARED / "standard" / file, task / "environment/sim" / file)
                write(task / "environment/sim/task_text.txt", spec["instruction"] + "\n")
                copy(SHARED / "standard/grade.py", task / "tests/grade.py")
                write(
                    task / "tests/Dockerfile",
                    f"""FROM {CLIENT_IMAGE}
COPY test.sh grade.py /tests/
RUN chmod +x /tests/test.sh
WORKDIR /tests
""",
                )
            if manifest is not None and manifest.get("metadata", {}).get("oracle", "none") != "none":
                write_solution(task, mode, _family_file(folder, manifest["solution"][mode]), manifest["hand_solutions"])
            elif (essential_manifest(spec) or {}).get("solution"):
                write_solution(task, mode, essential_manifest(spec)["solution"],
                               essential_manifest(spec)["hand_solutions"])
            write(
                task / "tests/test.sh",
                """#!/bin/bash
set -u
rm -rf /logs/verifier/*
mkdir -p /logs/verifier
python /tests/grade.py 2> /logs/verifier/grade.log
""",
                executable=True,
            )
            tasks.append(task)
    for task in tasks:
        normalize(task)
    return tasks


def tree(path: Path) -> dict:
    return {
        str(file.relative_to(path)): (file.read_bytes(), bool(file.stat().st_mode & 0o100))
        for file in sorted(path.rglob("*"))
        if file.is_file() and "__pycache__" not in file.parts
    }


def refresh_manifest(only: set[str] | None = None, release: bool = False) -> None:
    """Use Harbor 0.23.0's content-hash algorithm; the repository CI independently recomputes it.

    Entries of the selected families are replaced. With --release, every DexHand entry outside the release subset is
    dropped as well (the release branch contains only the release task directories).
    """
    manifest = ROOT / "tasks/dataset.toml"
    current = manifest.read_text()
    import re

    names = None if only is None else {task_name(family, mode) for family in only for mode in ("privileged", "standard")}

    def selected(block: str) -> bool:
        match = re.search(r'name = "robot-coding-bench/(dexhand-[^"]+)"', block)
        if not match:
            return False
        return release or names is None or match.group(1) in names

    blocks = current.split("[[tasks]]")
    current = blocks[0] + "".join("[[tasks]]" + block for block in blocks[1:] if not selected(block))
    current = current.rstrip() + "\n"
    tasks = sorted((ROOT / "tasks").glob("dexhand-*/"))
    if names is not None:
        tasks = [task for task in tasks if task.name in names]
    for task in tasks:
        files = [task / name for name in ("task.toml", "instruction.md", "README.md")]
        for sub in ("environment", "tests", "solution", "steps"):
            files.extend(
                file
                for file in (task / sub).rglob("*")
                if file.is_file()
                and "__pycache__" not in file.parts
                and not file.name.endswith((".pyc", ".swp", ".swo", "~"))
                and file.name != ".DS_Store"
            )
        digest = hashlib.sha256()
        for file in sorted(files, key=lambda file: file.relative_to(task).as_posix()):
            digest.update(
                f"{file.relative_to(task).as_posix()}\0{hashlib.sha256(file.read_bytes()).hexdigest()}\n".encode()
            )
        current += f'\n[[tasks]]\nname = "robot-coding-bench/{task.name}"\ndigest = "sha256:{digest.hexdigest()}"\n'
    manifest.write_text(current)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--refresh-manifest", action="store_true")
    parser.add_argument("--only-family", help="Render or check only one family, preserving other task directories")
    parser.add_argument("--release", action="store_true",
                        help="Render or check only the families in scripts/dexhand/release.json")
    parser.add_argument("--list", action="store_true", help="List registered families and their sources")
    args = parser.parse_args()
    only = None
    missing = []
    if args.release:
        only = set(release_families())
        try:
            registered = {spec["id"] for spec, _, _ in all_specs(None)}
        except (OSError, KeyError, ValueError) as error:
            print(f"FAIL {error}")
            return 1
        missing = sorted(only - registered)
        for family in missing:
            print(f"MISSING {family}: in release.json but not registered (no families/{family}/family.json yet)")
        only &= registered
    if args.only_family:
        only = {args.only_family} if only is None else only & {args.only_family}
        if not only:
            print(f"FAIL {args.only_family} is not in the release subset")
            return 1
    if args.list:
        plugins = plugin_folders()
        release = set(release_families()) if RELEASE.is_file() else set()
        for spec, manifest, folder in all_specs(only):
            source = (folder.relative_to(ROOT) if folder else
                      "task_library" if spec["id"].startswith("essential_") else
                      HAMBURGER.relative_to(ROOT) if spec["id"] == "assemble_hamburger" else
                      "daily" if spec["id"] in daily_folders() else "catalog.json")
            print(f"{spec['id']:32s} {'plugin' if spec['id'] in plugins else 'legacy':6s} "
                  f"{'release' if spec['id'] in release else '-':7s} {source}")
        return 0
    legacy_essential = only is None or any(family.startswith("essential_") for family in only)
    if legacy_essential and (HERE / "essential_catalog.json").exists():
        from library import inspect
        from sync_essential_catalog import content

        try:
            inspect()
        except (OSError, KeyError, ValueError) as error:
            print(f"FAIL task library: {error}")
            return 1
        if (HERE / "essential_catalog.json").read_text() != content():
            print("FAIL essential catalog: run scripts/dexhand/sync_essential_catalog.py before generation")
            return 1
    try:
        if args.check:
            with tempfile.TemporaryDirectory() as directory:
                tasks = render(Path(directory), only)
                bad = [task.name for task in tasks if tree(task) != tree(ROOT / "tasks" / task.name)]
                expected = {task.name for task in tasks}
                if only is None:
                    bad += [task.name for task in (ROOT / "tasks").glob("dexhand-*") if task.name not in expected]
            for name in bad:
                print(f"FAIL {name}: regenerate with scripts/dexhand/generate.py")
            for name in sorted(OVERSIZED):
                print(f"FAIL {name}: solution file of 2 MB or more; split it with shared/solution/solution_parts.py")
            bad += sorted(OVERSIZED)
            print(f"checked {len(tasks)} DexHand task directories: {len(bad)} differences"
                  + (f", {len(missing)} release families missing" if missing else ""))
            return int(bool(bad) or bool(missing))
        tasks = render(ROOT / "tasks", only)
    except (OSError, KeyError, ValueError) as error:
        print(f"FAIL {error}")
        return 1
    if args.refresh_manifest:
        refresh_manifest(only, release=args.release and not args.only_family)
    print(f"rendered {len(tasks)} DexHand task directories")
    for name in sorted(OVERSIZED):
        print(f"FAIL {name}: solution file of 2 MB or more; split it with shared/solution/solution_parts.py")
    return int(bool(OVERSIZED))


if __name__ == "__main__":
    raise SystemExit(main())
