#!/usr/bin/env python3
"""Put the match extension of eai-standard/3.0 (docs/protocol/eai-standard.md#match-extension; eai_std/ next to this file) into
the Embodied Olympics - Match tasks that serve it, after an export (ci_checks/benchmarks/embodied-olympics-match/
exported.toml lists the files it changes in each task's `patched`). Idempotent: a second run changes nothing.

Per task (tasks/embodied-olympics-match/<task>/):
  - environment/sim/eai_std/: the adapter, a byte copy of eai_std/ (the sim image's `COPY . /srv/` puts it at /srv/eai_std);
  - environment/docker-compose.yaml: the sim sidecar runs `python3 -m eai_std.serve` (core/serve.py or core/lockstep.py,
    unchanged, with the standard endpoints on the same port) with EAI_STD_CLOCK = realtime | lockstep | turn;
  - environment/Dockerfile: the shared client (standard-files: rcb1.py and the realtime or the shared rcb_client.py) in /opt/tools;
  - instruction.md: `### Client` names the standard endpoints first, then the `game` command (unchanged).
The core and the sport (core/, sport/: source_sha) and the files-only image are not touched.

Usage: apply_eai_std.py [--check] [task dirs...]   (default: every task of TASKS)
"""
from __future__ import annotations

import re
import sys
import textwrap
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SRC = HERE / "eai_std"
FILES = ("__init__.py", "adapter.py", "pngdec.py", "rcb1.py", "serve.py")
TASKS_DIR = ROOT / "tasks/embodied-olympics-match"
P = "embodied-olympics-match-"
# the tasks on the extension (owner 2026-11-25): every real-time match and standard twin, the turn-based bout; not the
# low-level skill matches (matchlow: their own in-loop skill service) nor the G1 table tennis (core 0.5, its own image)
TASKS = [P + n for n in (
    "badminton-duelrl-i01-realtime", "badminton-duelrl-i01-standard",
    "badminton-match-i04-realtime", "badminton-match-i04-standard",
    "fencing-bout-i02-standard",
    "foosball-match-i01-realtime", "foosball-match-i01-standard",
    "soccer-jointcpu-i01-realtime", "soccer-jointcpu-i01-standard",
    "soccer-jointgpu-i01-realtime", "soccer-jointgpu-i01-standard",
    "soccer-match-i00-realtime", "soccer-match-i00-standard",
    "soccerssl-match-i01-realtime", "soccerssl-match-i01-standard",
    "tabletennis-duelrl-i01-realtime", "tabletennis-duelrl-i01-standard",
    "tabletennis-match-i04-realtime", "tabletennis-match-i04-standard")]
OLD_CMD = {"realtime": "python3 /srv/core/launch.py", "lockstep": "python3 -m core.lockstep", "turn": "python3 /srv/core/launch.py"}
CMD = "python3 -m eai_std.serve"
# the shared client's files-only image: the pin in images/standard-files/FILES.json (scripts/files_image.py), never a copy
sys.path.insert(0, str(ROOT / "scripts"))
import files_image  # noqa: E402

STD_FILES = files_image.image("standard-files")
CLIENT = {"realtime": "/rcb1.py /realtime/rcb_client.py", "lockstep": "/rcb1.py /rcb_client.py",
          "turn": "/rcb1.py /rcb_client.py"}
DOCKER_MARK = "# the eai-standard/3.0 client (docs/protocol/eai-standard.md): `from rcb_client import Robot`"

ENDPOINTS = """\
| HTTP | |
| --- | --- |
| `GET /spec` | the standard spec (`cameras` with intrinsics and pose, `action_types` with each type's fields and row layout, `timing`) and, under `match`, everything `game spec` gives |
| `GET /status` | the state, no image |
| `POST /start {{}}` | you are ready; the match begins when every seat has started |
| `POST /observe {{"cameras": [...]}}` | {observe} |
| `POST /submit {{"type": T, "rows": [ACTION, ...]{submit_args}}}` | {submit} |
| `POST /submit {{"type": T, "interpolate": "hold", "seconds": S}}` | {hold} |
| `POST /ready {{"why": "...", "plan": "..."}}` | your review{review} |
"""
_IMAGES = "(RCB1: `last/<camera>`, `frames/<camera>`, `view` = the tiled PNG of `game observe`)"
OBSERVE = {c: "the camera images of now, at once; no time passes " + _IMAGES for c in ("realtime", "lockstep", "turn")}
HOLD = {
    "realtime": "no new action for S seconds: what was planned for that robot from now on is dropped, and its last action stays in force",
    "lockstep": "lets S seconds of game time pass with your last actions in force (as `game wait S`)",
    "turn": "waits up to S seconds of real time for your turn (as `game wait`)",
}
SUBMIT_ARGS = {"realtime": ', "dt": DT, "at": STEP', "lockstep": ', "dt": DT', "turn": ""}
SUBMIT = {
    "realtime": "your actions (the objects of `game act`), a plan: row i at control step `at` + i × DT / control step",
    "lockstep": "your actions (the objects of `game act`), one after the other, each followed by DT of game time",
    "turn": "your action for this turn (one row: the object of `game act`)",
}
REVIEW = {"realtime": " when the world freezes", "lockstep": " when the world freezes", "turn": ""}
RULE = {
    "realtime": (
        "`/submit` answers at once. `at` (default: the current step, `meta.step`) and DT (default: one control step) "
        "place the rows; a new chunk replaces what was planned for the same robot from `at` on, and rows whose step has "
        "passed are dropped (`meta.late_rows`). Each row is sent to the match at its step and takes effect like a "
        "`game act`; the next answers list each row's `effect_step` in `meta.effects` (a row the match refuses: "
        "`code` 400 there). The last action stays in force (no interpolation between rows). The plan is cleared when "
        "the world freezes."),
    "lockstep": (
        "`/submit` returns after its last row: each row takes effect at the current step, then the world advances DT "
        "(default: one control step). An action the match refuses is a 400 (a later row's: `code` 400 in "
        "`meta.effects`)."),
    "turn": "`/submit` takes one row: the action of your turn; an action the match refuses is a 400.",
}
ENTITY = ("Where an action names a robot (`entity`), one chunk commands one: `\"entity\": E` in the chunk, or the "
          "type `T@E`.")
CLIENT_HEAD = """\
### Client
The service at `http://localhost:8000` speaks eai-standard/3.0 with the match extension: the endpoints
of every standard task, plus `/start` and `/ready`. The shared client is installed (`from rcb_client import Robot`).

"""
CLIENT_TAIL = (
    "Every answer's `meta` has `score`, `review_due` (send `/ready` now), `match_over`, `step`, `phase` and your `state`. "
    "A `/submit` while the world is frozen or before the start executes nothing (`ok: false`, `not_now`); after the "
    "match is over requests are a 409. `/finish` and `/reset` are not offered (404): the match's rules end it, and there "
    "is one match. What differs from the plain standard: `timing.deviations` in `/spec`.")
GAME_LEAD = ("The same match also answers the `game` command, or the same calls as HTTP with JSON under "
             "`http://localhost:8000/<SEAT>/` (the paths below are under it; your seat is `$SEAT`); you may use both:")


def clock_of(task: Path) -> str:
    m = re.search(r'EAI_STD_CLOCK: "(\w+)"', (task / "environment/docker-compose.yaml").read_text())
    if m:                                         # applied before
        return m.group(1)
    if task.name.endswith("-realtime"):
        return "realtime"
    return "lockstep" if f"command: {OLD_CMD['lockstep']}" in (task / "environment/docker-compose.yaml").read_text() else "turn"


def sub1(text: str, old: str, new: str, what: str, task: Path) -> str:
    if new in text and old not in text:
        return text
    if text.count(old) != 1:
        raise SystemExit(f"{task.name}: {what}: {old!r} found {text.count(old)} times")
    return text.replace(old, new)


def compose(text: str, clock: str, task: Path) -> str:
    if f"command: {CMD}" not in text:
        text = sub1(text, f"    command: {OLD_CMD[clock]}\n", f"    command: {CMD}\n", "sim command", task)
    if "EAI_STD_CLOCK" not in text:
        text = sub1(text, '      RCB_DATA: "/data"\n', f'      RCB_DATA: "/data"\n      EAI_STD_CLOCK: "{clock}"\n',
                    "sim environment", task)
    text = text.replace("unchanged (core/launch.py: the match service, ",
                        "unchanged (core/serve.py, with the standard endpoints of eai_std/serve.py on the same port: the match service, ")
    text = text.replace("unchanged (core/lockstep.py: the match service in lockstep, ",
                        "unchanged (core/lockstep.py, with the standard endpoints of eai_std/serve.py on the same port: the match service in lockstep, ")
    if not re.search(r'PLAYER_MODE_A: "unmetered"', text):
        raise SystemExit(f"{task.name}: seat A is not unmetered (eai_std.serve starts no metering proxy)")
    return text


def dockerfile(text: str, clock: str, task: Path) -> str:
    if DOCKER_MARK in text:                       # applied before: keep the client's pin current
        return re.sub(r"^(COPY --from=)ghcr\.io/mll-lab-nu/efe:standard-files-[0-9.]+@sha256:[0-9a-f]{64}( /rcb1\.py )",
                      lambda m: m.group(1) + STD_FILES + m.group(2), text, flags=re.M)
    add = f"{DOCKER_MARK}\nCOPY --from={STD_FILES} {CLIENT[clock]} /opt/tools/\nENV PYTHONPATH=/opt/tools\n"
    anchor = re.search(r"^RUN chmod \+x /usr/local/bin/game.*\n", text, re.M)
    if anchor:                                    # the generic player image: after the `game` command
        return text[:anchor.end()] + add + text[anchor.end():]
    anchor = re.search(r"^ENV SIM_URL=", text, re.M)
    if not anchor:                                # a prebuilt seat image (soccer joint): before its ENV line
        raise SystemExit(f"{task.name}: environment/Dockerfile: neither a `game` install line nor ENV SIM_URL")
    return text[:anchor.start()] + add + text[anchor.start():]


def wrap(text: str) -> str:
    return textwrap.fill(text, width=120, break_long_words=False, break_on_hyphens=False)


def instruction(text: str, clock: str, task: Path) -> str:
    export_head = ("### Client\nThe `game` command, or the same calls as HTTP with JSON at `http://localhost:8000/<SEAT>/` "
                   "(your seat is `$SEAT`):\n")
    m = re.search(r"(?s)### Client\n.*?\n(?=\| `game` command \|)", text)
    if not m or (text.count(export_head) != 1 and "speaks eai-standard/3.0 with the match extension" not in m.group(0)):
        raise SystemExit(f"{task.name}: instruction.md: the `### Client` section is neither the export's nor ours")
    eps = ENDPOINTS.format(observe=OBSERVE[clock], submit_args=SUBMIT_ARGS[clock], submit=SUBMIT[clock],
                           hold=HOLD[clock], review=REVIEW[clock])
    if "`game say" in text:                    # a team format: the team channel
        eps += ('| `POST /say {"text": "..."}` | a message to your team (`game say`) |\n'
                '| `POST /team {"since": N}` | your team\'s messages (`game team`) |\n')
    rule = RULE[clock] + ("" if clock == "turn" else " " + ENTITY)
    new = (CLIENT_HEAD + eps.rstrip("\n") + "\n\n" + wrap(rule + " " + CLIENT_TAIL) + "\n\n"
           + wrap(GAME_LEAD) + "\n\n")
    return text[:m.start()] + new + text[m.end():]


def apply(task: Path, check: bool) -> list[str]:
    clock = clock_of(task)
    changed = []
    sim = task / "environment/sim/eai_std"
    for f in FILES:
        src = (SRC / f).read_bytes()
        dst = sim / f
        if not dst.is_file() or dst.read_bytes() != src:
            changed.append(str(dst.relative_to(task)))
            if not check:
                sim.mkdir(exist_ok=True)
                dst.write_bytes(src)
    edits = {
        "environment/docker-compose.yaml": lambda t: compose(t, clock, task),
        "environment/Dockerfile": lambda t: dockerfile(t, clock, task),
        "instruction.md": lambda t: instruction(t, clock, task),
    }
    for rel, fn in edits.items():
        p = task / rel
        old = p.read_text()
        new = fn(old)
        if new != old:
            changed.append(rel)
            if not check:
                p.write_text(new)
    return changed


def main(argv: list[str]) -> int:
    check = "--check" in argv
    dirs = [Path(a) for a in argv if not a.startswith("--")] or [TASKS_DIR / t for t in TASKS]
    bad = 0
    for d in dirs:
        ch = apply(d.resolve(), check)
        if ch:
            bad += 1
            print(f"{d.name}: {'would change' if check else 'changed'} {', '.join(ch)}")
    return 1 if check and bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
