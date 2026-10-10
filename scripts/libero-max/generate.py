#!/usr/bin/env python3
"""Generate the LIBERO-MAX tasks: tasks/libero-max-<suite>-<goal>-<event>-iNN-privileged and ...-standard.

    python3 scripts/libero-max/generate.py            # every case in cases.json (verified by freeze.sh)
    python3 scripts/libero-max/generate.py --check    # exit 1 if tasks/ differs from what this would write

Inputs: cases.json (the chosen LIBERO-MAX cases with their frozen event parameters, select_cases.py), frozen/<case>/
{instance.json, oracle.npy, report.json} (freeze.sh), the templates in templates/, the shared sources in shared/ (copied
byte for byte) and the standard client's base image and pins (scripts/eai_standard/). Each task directory is written
from scratch and finished with scripts/task_conventions.py (normalize, PROTOCOL v1.0.1); a libero-max-* directory this
does not write is removed. Re-running reproduces the tasks exactly.

The event parameters come from LIBERO-MAX's manifest and live only in cases.json (and the instances made from it), so
they can be replaced by independently drawn ones without touching this generator.
"""

import filecmp
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from task_conventions import normalize  # noqa: E402   (protocol v1.0.1 conventions)

TASKS_DIR = ROOT / "tasks"
SHARED = HERE / "shared"
TEMPLATES = HERE / "templates"
FROZEN = HERE / "frozen"
VERSION = (ROOT / "images/libero-max/VERSION").read_text().strip()
IMAGE = f"ghcr.io/mll-lab-nu/eai-libero-max:{VERSION}"
_EAI = ROOT / "scripts/eai_standard"
_ENV = dict(ln.split("=", 1) for ln in (_EAI / "client.env").read_text().splitlines() if "=" in ln and ln[0] != "#")
CLIENT_IMAGE = _ENV["CLIENT_IMAGE"].strip()
CLIENT_PIP = " ".join(
    ln.split("#", 1)[0].strip()
    for ln in (_EAI / _ENV.get("CLIENT_REQUIREMENTS", "client-requirements.txt").strip()).read_text().splitlines()
    if ln.split("#", 1)[0].strip()
)
AUTHOR, ORG = "Changhe Chen", "MLL Lab"
HOSTS = [
    "chatgpt.com", "*.chatgpt.com", "auth.openai.com", "api.openai.com", "*.openai.com", "api.anthropic.com",
    "*.anthropic.com", "openrouter.ai", "*.openai.azure.com", "*.cognitiveservices.azure.com",
]  # fmt: skip
SUITE_MAX_STEPS = {"libero_spatial": 220, "libero_object": 280, "libero_goal": 300, "libero_10": 520}
SUITE_SHORT = {"libero_spatial": "spatial", "libero_object": "object", "libero_goal": "goal", "libero_10": "long"}
STD_CAP = 9000  # standard: technical episode cap (the grading replay must fit the collect hook's wait)
# The collect hook's wait for the grading replay's verdict (finalize.sh RCB_COLLECT_WAIT_S; "Collect budget" in
# docs/benchmarks/libero-max.md): STD_CAP steps x 0.5 s on a busy host + 180 s to build the scene + 240 s of video
# (lmx_tool.VIDEO_BUDGET_S) = 4920 s, 480 s to spare. The hook's timeout adds 180 s (the PID file) and 120 s.
COLLECT_WAIT_S = 5400
COLLECT_TIMEOUT_S = 180 + COLLECT_WAIT_S + 120
if f"RCB_COLLECT_WAIT_S:-{COLLECT_WAIT_S}}}" not in (SHARED / "standard/finalize.sh").read_text():
    raise SystemExit("shared/standard/finalize.sh: RCB_COLLECT_WAIT_S's default differs from COLLECT_WAIT_S")
IMAGE_HW = 256
MS_STEP, MS_FRAME = 20, 70  # measured in eai-libero-max on the reference machine (docs/benchmarks/libero-max.md)

PRIV_ENV_DOCKERFILE = f"""# LIBERO-MAX privileged task: the LIBERO-MAX image, the task's tooling and its frozen instance.
FROM {IMAGE}
COPY instance.json /app/instance.json
COPY lmx_tool.py /opt/tools/lmx_tool.py
ENV PYTHONPATH=/opt/tools:/opt/libero-max/overlay:/opt/libero-max/src
RUN mkdir -p /app/output
WORKDIR /app
"""
PRIV_TESTS_DOCKERFILE = f"""# Separate verifier sandbox: the same image with the verifier's own copies of the tooling and the frozen instance;
# only the declared artifacts (/app/output/) arrive from the agent.
FROM {IMAGE}
COPY test.sh grade.py lmx_tool.py instance.json /tests/
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests:/opt/libero-max/overlay:/opt/libero-max/src
WORKDIR /tests
"""
STD_ENV_DOCKERFILE = f"""# Standard mode: the agent container has no simulator and no LIBERO code -- only Python and the client.
FROM {CLIENT_IMAGE}
RUN pip install --no-cache-dir {CLIENT_PIP}
COPY rcb_client.py rcb1.py /opt/tools/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
"""
STD_TESTS_DOCKERFILE = f"""# Separate verifier sandbox: grades the sim service's own artifacts; needs nothing but Python.
FROM {CLIENT_IMAGE}
COPY test.sh grade.py /tests/
RUN chmod +x /tests/test.sh
"""


def compose(task_text: str, episode: str) -> str:
    return f"""# Standard mode: the simulator runs in the `sim` sidecar (the agent cannot open it); the agent only reaches port 8000.
# No `expose`/`ports` on sim: under Harbor's egress control it shares main's network namespace (localhost:8000).
# CPU only: MuJoCo physics and OSMesa rendering (~{MS_FRAME} ms per {IMAGE_HW}x{IMAGE_HW} image); no GPU reservation.
services:
  main:
    depends_on: [sim]
  sim:
    image: {IMAGE}
    volumes:
      - ./sim:/srv:ro
    command: python /srv/server.py
    restart: on-failure:6                               # a crash resumes the same episode, never a reset (rcb_service.py)
    tmpfs:
      - /tmp                                            # robosuite writes its log there
    environment:
      RCB_INSTANCE: /srv/instance.json
      RCB_TASK_TEXT: {json.dumps(task_text)}
      RCB_EPISODE: {json.dumps(episode)}
      RCB_WALL_CLOCK_S: "3600.0"
      RCB_MAX_CONTROL_STEPS: "{STD_CAP}"
      RCB_IMAGE_HW: "{IMAGE_HW}"
      # The default is the standard configuration (one episode, no reset); this service offers no resets.
      RCB_RESET_BUDGET: "0"
      PYTHONPATH: /srv:/opt/libero-max/overlay:/opt/libero-max/src
"""


def sentence(text: str) -> str:
    t = " ".join(text.split())
    t = t[0].upper() + t[1:]
    return t if t.endswith(".") else t + "."


def slug(text: str, n: int = 40) -> str:
    words = re.sub(r"[^a-z0-9]+", " ", text.lower()).split()
    out = []
    for w in words:
        if len("-".join(out + [w])) > n:
            break
        out.append(w)
    return "-".join(out)


def nums(v, fmt="{:g}") -> str:
    return "(" + ", ".join(fmt.format(round(float(x), 3)) for x in v) + ")"


def event_text(change_type: str, ch: dict) -> tuple[str, str]:
    """(short words, what happens) for a LIBERO-MAX change."""
    obj = f"`{ch.get('object')}`"
    if change_type == "target_relocation":
        return (
            "target relocation",
            f"{obj} is moved {ch['distance_m']:g} m across the table, direction {nums(ch['direction_xy'])}",
        )
    if change_type == "receptacle_relocation":
        return (
            "receptacle relocation",
            f"the receptacle {obj} is moved {ch['distance_m']:g} m, direction {nums(ch['direction_xy'])}",
        )
    if change_type == "obstacle_insertion":
        return (
            "obstacle insertion",
            f"{obj} appears as an obstacle, offset {nums(ch['offset_m'])} m from `{ch['relative_to']}`",
        )
    if change_type == "distractor_burst":
        names = ", ".join(f"`{p['object']}`" for p in ch["placements"])
        return "distractor burst", f"{len(ch['placements'])} other objects appear on the table ({names})"
    if change_type == "camera_shift":
        return "camera shift", (
            f"the `agentview` camera moves by {nums(ch['delta_position_m'])} m, turns {ch['yaw_degrees']:g}° and its field "
            f"of view changes by {ch['delta_fovy_degrees']:+g}°"
        )
    if change_type == "sensor_noise_onset":
        return "sensor-noise onset", (
            f"the camera images get noise (std {ch['noise_std']:g} on 0..255) and a blocked patch "
            f"({ch['occlusion_fraction'] * 100:.0f}% of the image)"
        )
    if change_type == "illumination_switch":
        return "illumination switch", f"the lighting is scaled by {ch['scale']:g}"
    if change_type == "visual_theme_switch":
        return "visual-theme switch", (
            f"the image colours change (channels permuted {nums(ch['rgb_permutation'], '{:.0f}')}, scaled "
            f"{nums(ch['rgb_multiplier'])})"
        )
    raise ValueError(change_type)


ARTICULATED = {  # LIBERO's thresholds (libero/envs/objects/articulated_objects.py), per goal and articulated object
    ("open", "cabinet"): "its drawer's slide joint is out by more than 0.14 m (it travels 0.16 m)",
    ("close", "cabinet"): "its drawer's slide joint is all the way in, past its closed position (q > 0); a drawer left "
    "out by a few millimetres is not closed",
    ("open", "microwave"): "its door's hinge is open by more than 1.3 rad (74 degrees)",
    ("close", "microwave"): "its door's hinge is within 0.005 rad of shut",
    ("turnon", "stove"): "its knob is turned at least 0.5 rad (29 degrees) counter-clockwise, seen from above, from off",
    ("turnoff", "stove"): "its knob is turned back fully, past its off position (q < 0)",
}
STATE_WORD = {"open": "open", "close": "closed", "turnon": "on", "turnoff": "off"}
PRED_NAME = {"open": "Open", "close": "Close", "turnon": "TurnOn", "turnoff": "TurnOff"}


def articulated(pred: str, a: str) -> str:
    kind = next((k for p, k in ARTICULATED if p == pred and k in a), None)
    if kind is None:
        raise ValueError(f"no wording for predicate {pred} of {a}")
    return ARTICULATED[(pred, kind)]


def goal_text(goal: list) -> str:
    """LIBERO's success check, predicate by predicate, with its real thresholds (libero/envs/predicates and
    object_states: On, In, in_box, under; Open, Close, TurnOn, TurnOff)."""
    lines = []
    for g in goal:
        pred, a = str(g[0]).lower(), g[1]
        if pred in STATE_WORD:
            lines.append(f"- `{a}` is {STATE_WORD[pred]} (LIBERO's {PRED_NAME[pred]}: {articulated(pred, a)})")
            continue
        b = g[2]
        if pred == "on" and b.endswith("_region"):
            lines.append(
                f"- `{a}` is on `{b}` (LIBERO's On for a region: `{a}`'s origin lies inside the region's footprint and "
                "between 0.5 cm below and 10 cm above the region's top, and it touches the region's object)"
            )
        elif pred == "on":
            lines.append(
                f"- `{a}` is on `{b}` (LIBERO's On: `{a}`'s origin is no lower than `{b}`'s, less than 3 cm from it "
                f"horizontally, and the two touch)"
            )
        elif pred == "in":
            lines.append(
                f"- `{a}` is in `{b}` (LIBERO's In: `{a}`'s origin lies inside the region's box, whose floor counts 1 cm "
                "lower, and it touches the region's object)"
            )
        else:
            raise ValueError(f"no wording for predicate {g}")
    return "\n".join(lines)


def render(template: str, values: dict) -> str:
    text = (TEMPLATES / template).read_text()
    for k, v in values.items():
        text = text.replace("{{" + k + "}}", str(v))
    if "{{" in text:
        raise ValueError(f"{template}: unfilled placeholder near {text[text.index('{{') :][:40]!r}")
    return text


def reset_dir(d: Path) -> None:
    """A task directory is written from scratch: what is not rendered here does not belong (no results/, PROTOCOL D3)."""
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)


def put(path: Path, text: str | None = None, src: Path | None = None, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if src is not None:
        shutil.copyfile(src, path)
    else:
        path.write_text(text)
    path.chmod(mode)


def entity_words(name: str) -> str:
    """A BDDL entity as words: `basket_1_contain_region` -> `basket`, `wooden_cabinet_1_top_side` -> `wooden-cabinet-top`."""
    w = re.sub(r"_\d+", "", name)
    w = re.sub(r"_(contain_region|region|side)$", "", w)
    for drop in ("main_table_", "kitchen_table_", "living_room_table_", "study_table_", "floor_"):
        w = w.replace(drop, "")
    return w.replace("_", "-")


def names_for(cases: list) -> dict:
    """case_id -> task base name `libero-max-<suite>-<goal>-<event>-iNN`, the goal from the BDDL goal: placements as
    `<objects>-<on|in>-<target>`, articulated goals as `<object>-<open|closed|on|off>` (just the state when the object is
    the placement's target), joined by `-and-` (NN counts repeats of the same base)."""
    out, seen = {}, {}
    for c in cases:
        rep = json.loads((FROZEN / c["case_id"] / "report.json").read_text())
        goal = rep["goal"]
        place = [g for g in goal if str(g[0]).lower() not in STATE_WORD]
        goal_words, target = "", None
        if place:
            objs = "-and-".join(entity_words(g[1]) for g in place)
            target = entity_words(place[0][2])
            goal_words = f"{objs}-{str(place[0][0]).lower()}-{target}"
        for g in (g for g in goal if str(g[0]).lower() in STATE_WORD):
            state, obj = STATE_WORD[str(g[0]).lower()], entity_words(g[1])
            goal_words += f"-{state}" if obj == target else f"{'-and-' if goal_words else ''}{obj}-{state}"
        event = c["scenario"]["change_type"].replace("_", "-")
        base = f"libero-max-{SUITE_SHORT[c['task_suite_name']]}-{goal_words}-{event}"
        n = seen.get(base, 0)
        seen[base] = n + 1
        out[c["case_id"]] = f"{base}-i{n:02d}"
    return out


def make(case: dict, name: str, out: Path) -> tuple[Path, Path]:
    fz = FROZEN / case["case_id"]
    rep = json.loads((fz / "report.json").read_text())
    ch = case["scenario"]["change"]
    words, detail = event_text(case["scenario"]["change_type"], ch)
    instruction = sentence(rep["language"])
    ctl = rep["controller"]
    episode = (
        f'Ends when the task succeeds (reason "success"), after {STD_CAP} control steps ("failed"), when your time is up '
        '("timeout"), or on a simulator error ("error").'
    )
    values = {
        "name": name,
        "inst": name.rsplit("-", 1)[1],
        "case_id": case["case_id"],
        "suite": case["task_suite_name"],
        "event": case["scenario"]["change_type"],
        "event_words": words,
        "event_detail": detail,
        "trigger_m": f"{case['scenario']['trigger']['distance_m']:g}",
        "trigger_object": case["scenario"]["trigger"]["value"],
        "pro_category": case["substrate_variant"]["category"],
        "task_index": case["task_index"],
        "init_index": case["init_state_index"],
        "instruction": instruction,
        "instruction_toml": json.dumps(instruction)[1:-1],
        "goal_text": goal_text(rep["goal"]),
        "robot_base": nums(rep["robot_base"]["pos"]),
        "pos_scale": f"{ctl['output_max'][0]:g}",
        "rot_scale": f"{ctl['output_max'][3]:g}",
        "max_steps": SUITE_MAX_STEPS[case["task_suite_name"]],
        "std_cap": STD_CAP,
        "collect_wait": COLLECT_WAIT_S,
        "collect_timeout": COLLECT_TIMEOUT_S,
        "robot_seconds": round(STD_CAP / ctl["control_freq"]),
        "seed": case["policy_seed"],
        "image": IMAGE,
        "image_hw": IMAGE_HW,
        "ms_step": MS_STEP,
        "ms_frame": MS_FRAME,
        "author": AUTHOR,
        "org": ORG,
        "allowed_hosts": ", ".join(json.dumps(h) for h in HOSTS),
        "n_actions": rep["live"]["control_steps"],
        "event_step": rep["live"]["event_step"],
        "live_sha": rep["live"]["state_sha"][:12],
    }

    p = out / f"{name}-privileged"
    reset_dir(p)
    put(p / "task.toml", render("task.toml", values))
    put(p / "instruction.md", render("instruction.md", values))
    put(p / "README.md", render("README.md", values))
    put(p / "environment/Dockerfile", PRIV_ENV_DOCKERFILE)
    put(p / "environment/lmx_tool.py", src=SHARED / "lmx_tool.py")
    put(p / "environment/instance.json", src=fz / "instance.json")
    put(p / "tests/Dockerfile", PRIV_TESTS_DOCKERFILE)
    put(p / "tests/test.sh", src=SHARED / "test.sh", mode=0o755)
    put(p / "tests/grade.py", src=SHARED / "grade.py")
    put(p / "tests/lmx_tool.py", src=SHARED / "lmx_tool.py")
    put(p / "tests/instance.json", src=fz / "instance.json")
    put(p / "solution/solve.sh", src=SHARED / "solve_privileged.sh", mode=0o755)
    put(p / "solution/oracle_replay.py", src=SHARED / "oracle_privileged.py")
    put(p / "solution/oracle.npy", src=fz / "oracle.npy")

    s = out / f"{name}-standard"
    reset_dir(s)
    put(s / "task.toml", render("standard/task.toml", values))
    put(s / "instruction.md", render("standard/instruction.md", values))
    put(s / "README.md", render("standard/README.md", values))
    put(s / "environment/Dockerfile", STD_ENV_DOCKERFILE)
    put(s / "environment/docker-compose.yaml", compose(instruction, episode))
    put(s / "environment/rcb_client.py", src=SHARED / "standard/rcb_client.py")
    put(s / "environment/rcb1.py", src=SHARED / "standard/rcb1.py")
    for f in ("server.py", "rcb_service.py", "rcb1.py", "finalize.sh"):
        put(s / "environment/sim" / f, src=SHARED / "standard" / f)
    put(s / "environment/sim/lmx_tool.py", src=SHARED / "lmx_tool.py")
    put(s / "environment/sim/instance.json", src=fz / "instance.json")
    put(s / "tests/Dockerfile", STD_TESTS_DOCKERFILE)
    put(s / "tests/test.sh", src=SHARED / "test.sh", mode=0o755)
    put(s / "tests/grade.py", src=SHARED / "standard/grade.py")
    put(s / "solution/solve.sh", src=SHARED / "standard/solve.sh", mode=0o755)
    put(s / "solution/oracle_replay.py", src=SHARED / "standard/oracle_replay.py")
    put(s / "solution/oracle.npy", src=fz / "oracle.npy")
    normalize(p)
    normalize(s)
    return p, s


def render_all(out: Path) -> list[str]:
    cases = json.loads((HERE / "cases.json").read_text())["cases"]
    names = names_for(cases)
    done = []
    for c in cases:
        rep = json.loads((FROZEN / c["case_id"] / "report.json").read_text())
        if not rep.get("ok"):
            raise SystemExit(f"{c['case_id']}: not verified by freeze.sh ({rep.get('why')})")
        done += [d.name for d in make(c, names[c["case_id"]], out)]
    return done


def check() -> int:
    """tasks/ must be exactly what render_all writes (contents and modes), with no other libero-max-* directory."""
    with tempfile.TemporaryDirectory() as tmp:
        names = set(render_all(Path(tmp)))
        have = {d.name for d in TASKS_DIR.glob("libero-max-*") if d.is_dir()}
        bad = sorted(have ^ names)
        for name in sorted(names & have):
            stack = [filecmp.dircmp(TASKS_DIR / name, Path(tmp) / name, ignore=["__pycache__"])]
            while stack:
                c = stack.pop()
                diff = filecmp.cmpfiles(c.left, c.right, c.common_files, shallow=False)[1]
                modes = [
                    f for f in c.common_files if (Path(c.left) / f).stat().st_mode != (Path(c.right) / f).stat().st_mode
                ]
                if c.left_only or c.right_only or c.funny_files or diff or modes:
                    bad.append(name)
                    break
                stack += list(c.subdirs.values())
    for name in sorted(set(bad)):
        print(f"FAIL tasks/{name}: differs from scripts/libero-max/generate.py (re-run it)")
    if not bad:
        print(f"{len(names)} task directories match")
    return 1 if bad else 0


def main(args: list[str]) -> int:
    if args == ["--check"]:
        return check()
    names = render_all(TASKS_DIR)
    for d in sorted(TASKS_DIR.glob("libero-max-*")):
        if d.is_dir() and d.name not in names:
            shutil.rmtree(d)
            print(f"removed stale {d.relative_to(ROOT)}")
    print(f"generated {len(names)} task directories")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
