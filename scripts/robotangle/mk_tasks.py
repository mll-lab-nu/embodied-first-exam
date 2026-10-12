#!/usr/bin/env python3
"""Render the RoboTangle tasks (formerly TopoGym; docs/benchmarks/robotangle.md):
tasks/robotangle-<family>-<tier>-i00-privileged and its standard twin -standard (eai-standard/2.4).

usage: python3 scripts/robotangle/mk_tasks.py [--check] [--list] [--assets <dir>] [base ...]
  no base   every base in release.json
  --check   write nothing; exit 1 if a task would change, or if an identity check fails
  --list    print the bases with their evidence
  --assets  a local copy of the pinned HF dataset (scripts/robotangle/assets.py fetch <dir>): also check the frozen
            instances' bytes against the runtime bindings (without it, the pins in assets.json are compared)

Inputs, all in the repository (Python standard library only, plus scripts/task_conventions.normalize):
  release.json   the release (dev/jianwen commit, public simulator source, runtime) and, per base, where its frozen
                 instance comes from and which recorded oracle runs are its evidence
  shared/        the release's task templates (harbor_templates/topogym at release.json template_commit): the tooling
                 rcb_topogym.py verbatim; the graders, the sim service adapter (server.py, finalize.sh) and the 2.4
                 layer with the fixes of the 2026-10-10 review (docs/benchmarks/robotangle.md, "Fixes applied on main");
                 replay.py and the standard oracle player verbatim
  scripts/eai_standard/v2_4/ + scripts/eai_standard/
                 the eai-standard/2.4 layer (docs/STANDARD_MODE.md, issue #89): rcb_limited.py and rcb_client.py
                 from v2_4/, rcb1.py, run.sh and the client pins from scripts/eai_standard/. The release called its
                 layer "2.3"; that number went to the realtime capability (#86), so the layer and the texts say 2.4
  packages/      per task, the upstream texts of the graded package (task.toml, README.md, instruction.md, Dockerfiles,
                 compose files, test.sh; document paths point at this repository's docs/) and its upstream runtime binding; the generator applies the RoboTangle rename
                 (user-facing names only), the image name and the evidence wording to them, and the text fixes of
                 the 2026-10-10 review (review_fixes: the R-hold rule, the row cap, the 2.4 call semantics)
  oracles/       the recorded oracle trajectories of the evidence runs (privileged deliverable; standard episode)
  assets.json    the frozen instances (instance.json + instance_assets/, up to 20 MB per file) are not in git: they are
                 in the private HF dataset eai-v2-internal/robotangle-assets, pinned here by commit and sha256
                 (scripts/robotangle/assets.py). The image carries them (images/robotangle/Dockerfile); a task keeps its
                 runtime_binding.json, which names the instance's canonical sha256 and every asset's sha256, and stages
                 its instance from the image (images/robotangle/stage_instance.py: privileged environment/ and tests/
                 Dockerfiles, the standard sim service's entrypoint), where the tooling checks the binding again.
Nothing at run time imports repository code: the tooling and the sim layer are copies (PROTOCOL D9).
"""
from __future__ import annotations
import argparse, filecmp, hashlib, json, os, pathlib, re, shutil, sys, tempfile, zipfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TASKS = ROOT / "tasks"
SHARED, PKG, ORC = HERE / "shared", HERE / "packages", HERE / "oracles"
sys.path.insert(0, str(ROOT / "scripts"))
import task_conventions as TC  # noqa: E402  the protocol's conventions: every generator ends with normalize(task_dir)

REL = json.loads((HERE / "release.json").read_text())
# Agent egress (owner, 2026-10-10 / 10-11, board 0072): the model APIs and the package registries. The packages' task.toml carry the release's line (open
# egress); rewrite_toml puts the two lines `scripts/set_agent_egress.py allowlist` writes, with that script's HOSTS (one
# list for every task: ci_checks/check-verifier-isolation.sh).
EGRESS_OLD = "# egress: Harbor default (public). `scripts/set_agent_egress.py allowlist` closes it to the model APIs.\n"
_HOSTS = re.search(r"(?ms)^HOSTS = \[(.*?)\]", (ROOT / "scripts/set_agent_egress.py").read_text()).group(1)
EGRESS_NEW = ('network_mode = "allowlist"      # model APIs and package registries (scripts/set_agent_egress.py); PROTOCOL §2.11\n'
              "allowed_hosts = [" + ", ".join(f'"{h}"' for h in re.findall(r'"([^"]+)"', _HOSTS)) + "]\n")
NOP = json.loads((HERE / "nop_records.json").read_text())
ASSETS = json.loads((HERE / "assets.json").read_text())        # the pinned HF dataset (scripts/robotangle/assets.py)
STAGED = "/tmp/robotangle-instance"                             # where the standard sim stages its instance   # nop runs on this release's build (very_easy / easier)
VERSION = (ROOT / "images/robotangle/VERSION").read_text().strip()
IMAGE = f"ghcr.io/mll-lab-nu/eai-robotangle:{VERSION}"
ROBOT = {"aloha": "aloha-2", "panda_robotiq": "franka-robotiq-2f85"}
ROBOT_WORDS = {"(aloha, Genesis)": "(ALOHA 2, Genesis)", "(panda_robotiq, Genesis)": "(Franka Panda + Robotiq 2F-85, Genesis)"}
IMAGE_RX = re.compile(r"(?:[\w.-]+/)+rcb-topogym:[\w.-]+")
EAI = ROOT / "scripts/eai_standard"
LAYER = {"environment/rcb_client.py": EAI / "v2_4/rcb_client.py", "environment/rcb1.py": EAI / "rcb1.py",
         "environment/client-requirements.txt": EAI / "client-requirements.txt",
         "environment/sim/rcb_limited.py": EAI / "v2_4/rcb_limited.py", "environment/sim/rcb1.py": EAI / "rcb1.py",
         "environment/sim/run.sh": EAI / "run.sh"}   # the eai-standard/2.4 layer, copied unchanged (check-tooling-identity.sh)
PROTO = ("eai-standard/2.3", "eai-standard/2.4")   # the release's name of the layer -> its registered version (#89)
sha = lambda b: hashlib.sha256(b).hexdigest()  # noqa: E731


def dash(s: str) -> str:
    return s.replace("_", "-")


def text(s: str) -> str:
    """User-facing rename (README, instruction, task.toml); code identifiers (topogym, rcb_topogym) stay."""
    s = re.sub(r"\btopogym-([a-z0-9-]+-i\d\d-(?:privileged|standard))\b", r"robotangle-\1", s)
    s = IMAGE_RX.sub(IMAGE, s)
    for a, b in ROBOT_WORDS.items():
        s = s.replace(a, b)
    s = s.replace("TopoGym", "RoboTangle").replace(*PROTO)
    s = re.sub(r"\bhis (?=[a-z]+(?:_[a-z0-9]+)*_v\d)", "the ", s)
    return s.replace("his qualification record", "the author's qualification record")


# ---------------------------------------------------------------- fixes of the 2026-10-10 review (board 0067)
# Applied here, on top of the release's texts and Dockerfiles, until dev/jianwen carries them (docs/benchmarks/robotangle.md,
# "Fixes applied on main"). Every replacement asserts that its source text is still there: a new release that rewords
# it fails the render instead of silently losing the fix.
MAX_STEPS = 200000        # rcb_topogym.MAX_STEPS (RCB_MAX_STEPS): the runaway guard on an episode's / a trajectory's length
MAX_CALL_WALL_S = 900     # v2_4/rcb_limited.MAX_CALL_WALL_S (RCB_MAX_CALL_WALL_S): no compose file overrides it
CHUNK_S, WATCH_S = 10, 30  # the sim service's RCB_MAX_CHUNK_S / RCB_MAX_WATCH_S defaults
BUILD_ALLOWANCE_S = 1800  # scene build, kernel compilation and video encoding inside the verifier's timeout


def swap(s: str, old: str, new: str, what: str, count: int = 1) -> str:
    assert s.count(old) == count, f"{what}: expected {count} x {old[:60]!r}, found {s.count(old)}"
    return s.replace(old, new)


def step_time(instruction: str) -> float:
    return float(re.search(r"One control step takes about ([0-9.]+) s of wall clock", instruction).group(1))


def verifier_timeout(toml: str) -> float:
    return float(re.search(r"(?ms)^\[verifier\]\n.*?^timeout_sec = ([0-9.]+)", toml).group(1))


def row_cap(base: str) -> int:
    """The longest trajectory the privileged verifier accepts: its two replays must fit [verifier] timeout_sec at 1.5 x
    the step time the instruction states (the second replay also renders the video), after BUILD_ALLOWANCE_S; rounded
    down to 1000 rows, never above rcb_topogym's own guard. The loader accepted 200000 rows for every task; by the
    instructions' step times knot_untying (about 1.2 s per step) fits about 18000 rows twice into 45000 s, and a verifier
    that runs out of time leaves no reward (arithmetic from the stated step times, not a measured run)."""
    up = PKG / f"{base}-privileged"
    budget = verifier_timeout((up / "task.toml").read_text()) - BUILD_ALLOWANCE_S
    cap = min(MAX_STEPS, int(budget / (3 * step_time((up / "instruction.md").read_text()))) // 1000 * 1000)
    traj = ORC / base / "privileged.npz"
    if traj.is_file():      # the reference trajectory must fit, with room
        with zipfile.ZipFile(traj) as z, z.open("actions.npy") as f:
            f.read(8); n = int.from_bytes(f.read(2), "little"); header = f.read(n).decode("latin1")
        rows = int(re.search(r"'shape': \((\d+),", header).group(1))
        assert 1.5 * rows <= cap, f"{base}: the reference trajectory has {rows} rows, the cap is {cap}"
    return cap


R_HOLD_OLD = ("Success needs both replays to succeed AND at least one of them to reach the goal with the thresholds above "
              "within your own rows (not only in the hold).")
R_HOLD_NEW = ("Success needs both replays to succeed; each of them may complete its confirmation within that hold (whether "
              "one reached the goal with the thresholds above within your own rows is recorded, `strict_goal_reached`, not "
              "required).")
ROWS_OLD = ("so a replay whose confirmation ends a few ticks later needs more rows: you may append copies of the final row "
            "(holding still) before saving.")
ROWS_NEW = ("so a replay whose confirmation ends a few ticks later completes it in that hold; copies of the final row "
            "(holding still) appended before saving give it more room.")
VERIFY_OLD = ("at least one replay must\nreach the goal with the instance's own thresholds within the trajectory's rows.")
VERIFY_NEW = ("every replay may confirm\nwithin that hold (R-hold, 2026-10-05). Whether one reached the goal with the "
              "instance's own thresholds within the\ntrajectory's rows is reported (`strict_goal_reached`), not required.")


def time_per_call(step: float, hz: int) -> str:
    """The standard instruction's "Time per call" for eai-standard/2.4 (v2_4/rcb_limited.py call_begin / poll_stop / the
    operations endpoints, v2_4/rcb_client.py _post). The release's paragraph described 2.2's client timeouts."""
    chunk = CHUNK_S * hz * step
    fit = f"A `submit` of the maximum {CHUNK_S} s chunk takes about {chunk:.0f} s here"
    if 2 * chunk > MAX_CALL_WALL_S:
        fit += " (close to that limit on a slower host)"
    if 2 * WATCH_S * hz * step <= MAX_CALL_WALL_S:
        fit += f", and any watch up to {WATCH_S} s fits (both with a 2x margin)."
    else:
        n = int(MAX_CALL_WALL_S / (2 * step))
        fit += (f"; a `get_obs(seconds=...)` watch fits up to about {n} control steps ({n / hz:.2f} s, a 2x margin), and a "
                "longer one is cut short the same way.")
    return (
        "## Time per call\n"
        f"- One control step takes about {step:g} s of wall clock here. A request returns when all of its steps have run, or\n"
        f"  earlier: a call that has run for {MAX_CALL_WALL_S} s (`spec[\"max_call_wall_s\"]`) is stopped by the service at the next control\n"
        "  step and returns what it executed (`res.stopped` is `\"max_call_wall_s\"`; `res.meta[\"executed_rows\"]`, or\n"
        "  `res.meta[\"control_steps_watch\"]` for a watch, says how far it got; the robot holds its last target). Check\n"
        f"  `res.stopped` before you send the next rows. {fit}\n"
        "- The client waits longer than that (1800 s for `submit`, 1020 s for `get_obs`), so a client timeout or a connection\n"
        "  error means the connection or the service failed, not that the call is still on its way. Do NOT send the request\n"
        "  again blindly (it could run twice): `r.operation_status()` tells what became of the last one. Its `status` is\n"
        "  `completed` or `error` (with `rows_before` and `committed_rows`, the episode's control steps before and after it,\n"
        "  and `stopped`), `interrupted` (the service restarted during it and resumes the same episode in the state after the\n"
        "  last completed call: `spec[\"on_service_error\"]`, `r.wait_ready()`), or `admitted` (not finished); an HTTP 404 error\n"
        "  there means the service never admitted the request, so nothing ran. The service answers one request at a time, so\n"
        "  this query waits while a call is running: repeat it if it times out. If your client hangs up, the service stops\n"
        "  the call at the next control step. A request that arrives after its deadline is refused (408), and one whose\n"
        "  operation id was already admitted is refused (409); neither moves the robot. A control step that hangs for more\n"
        "  than 60 s past the call's limit ends the episode as an infrastructure error, not as your failure.\n")


SERVICE_DEADLINE = ("\n  This service also ends the episode itself (`meta[\"reason\"]` is `timeout`; it is graded as it stands) when its own\n"
                    "  count of that limit, `meta[\"time_left_s\"]`, reaches 0. That count has run since the service first started, a little\n"
                    "  before your session, so plan by `time_left_s`.\n")


def review_fixes(s: str, name: str, base: str, mode: str) -> str:
    """The text fixes for one rendered file (name: instruction.md | README.md)."""
    up = PKG / f"{base}-privileged" / "instruction.md"
    step = step_time(up.read_text()); hz = int(re.search(r"Control runs at (\d+) Hz", up.read_text()).group(1))
    if mode == "privileged":
        if R_HOLD_OLD in s:        # the GPU families (a tolerant hold): the grader's rule since tooling v16 is R-hold
            s = swap(swap(s, R_HOLD_OLD, R_HOLD_NEW, f"{base} {name} R-hold"), ROWS_OLD, ROWS_NEW, f"{base} {name} R-hold rows")
        if name == "README.md" and VERIFY_OLD in s:
            s = swap(s, VERIFY_OLD, VERIFY_NEW, f"{base} README Verification")
        assert "within your own rows (not only in the hold)" not in s and "at least one replay must" not in s, f"{base} {name}"
        if name == "instruction.md":
            cap = row_cap(base)
            s = swap(s, "There is no step budget; your\n  wall-clock budget is",
                     f"There is no step budget, but a trajectory may have at most\n  {cap} rows ({cap / hz / 60:.1f} min of simulated time): "
                     "the verifier has to replay it twice within its own time limit, so `s.step` stops\n  after that many control steps "
                     "since the last reset, and a longer trajectory is rejected as invalid (reward 0). Your\n  wall-clock budget is",
                     f"{base} step budget")
            # the agent's limit is stated once, by the closing `## Time limit` section normalize writes (PROTOCOL §2.12)
            s, n = re.subn(r"Your\n  wall-clock budget is \d+ min \(\d+ s\)\. ", "The time limit\n  (`## Time limit`) is your only budget. ", s)
            assert n == 1, f"{base}: the privileged budget sentence"
    elif name == "instruction.md":
        assert step_time(s) == step, f"{base}: the two modes state different step times"
        # the agent's limit is stated once, in `## Time limit` (PROTOCOL §2.12); what is RoboTangle's own stays here: this service
        # ends the episode on its own wall clock (server.py deadline_reached, counted from the service's first start)
        s, n = re.subn(r'- \*\*Your wall-clock budget is \d+ min \(\d+ s\)\*\* \(`meta\["time_left_s"\]` counts it down\); ',
                       "- **Your only budget is the time limit (`## Time limit`)**; ", s)
        assert n == 1, f"{base}: the standard budget sentence"
        s, n = re.subn(r"(One control step takes about [0-9.]+ s of wall clock here\.)\n(?=- There is nothing to hand in)",
                       lambda m: m.group(1) + SERVICE_DEADLINE, s)
        assert n == 1, f"{base}: the standard budget bullet's end"
        s = swap(s, "steps are unlimited. Actions and\n  simulated time are reported as cost.",
                 f"there is no step budget, but the\n  episode ends after {MAX_STEPS} control steps, watches included ({MAX_STEPS / hz / 60:.0f} min "
                 "of simulated time; a technical cap,\n  `spec[\"max_control_steps\"]`: `meta[\"reason\"]` is `step_guard`, and the episode is graded as it stands). "
                 "Actions and simulated time are reported as cost.", f"{base} step guard")
        m = re.search(r"(?ms)^## Time per call\n.*?(?=^## )", s)
        assert m and "the client gives up waiting after 1800 s" in m.group(0), f"{base}: Time per call"
        s = s[:m.start()] + time_per_call(step, hz) + "\n" + s[m.end():]
    return s


def limits_env(name: str, s: str, base: str, mode: str) -> str:
    """Privileged Dockerfiles: the row cap for the agent's tooling and the verifier (rcb_topogym reads RCB_MAX_STEPS),
    and the verifier's own timeout for its grader (it skips the review-frame pass when the time left would not cover it)."""
    if mode != "privileged" or name not in ("environment/Dockerfile", "tests/Dockerfile"):
        return s
    env = f"ENV RCB_MAX_STEPS={row_cap(base)}"
    if name == "tests/Dockerfile":
        env += f" RCB_VERIFIER_BUDGET_S={verifier_timeout((PKG / f'{base}-privileged' / 'task.toml').read_text()):.0f}"
    line = "ENV PYTHONPATH=/opt/tools:/opt/topogym\n" if name == "environment/Dockerfile" else "ENV PYTHONPATH=/tests:/opt/topogym\n"
    return swap(s, line, line + "# the longest trajectory the verifier replays within its timeout (scripts/robotangle/mk_tasks.py row_cap)\n" + env + "\n",
                f"{base} {name}")


def toml_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def run_words(e: dict) -> str:
    return f"{e['release']} (source {e['source']}, tooling {e['tooling']}; lab run {pathlib.Path(e['attempt']).name.removeprefix('attempt-')})"


def evidence_text(base: str, rec: dict) -> str:
    ev = rec["evidence"]
    if not ev:
        return ("Oracle pending: the author is fixing this tier's oracle; it follows in a later pull request. "
                "Human review (PROTOCOL §2.7); nop pending.")
    runs = "; ".join(f"{m}: {run_words(ev[m])}" for m in ("privileged", "standard") if m in ev)
    note = rec.get("note")
    return (f"Human review (PROTOCOL §2.7). No oracle run on this build (dev/jianwen {REL['release_commit'][:9]}, source "
            f"{REL['runtime']['source']['sha256'][:8]}, tooling {REL['tooling_sha256'][:8]}). Positive examples: the "
            f"author's oracle scored 1 in both modes on {runs}" + (f"; {note}" if note else "") +
            ". solution/ replays the recorded trajectories.")


def since_evidence(rec: dict) -> str:
    """What changed between the evidence build and this release (release.json; docs/benchmarks/robotangle.md, Evidence)."""
    end = " The oracle was not re-run on this build (docs/benchmarks/robotangle.md, Evidence)."
    if rec["family"] == "blanket_flatten" and REL.get("blanket_change"):
        return REL["blanket_change"] + end
    shared = REL.get("release_change", "")
    if rec.get("note"):          # graded on an earlier build than merged-v18 / its equivalent (the documented equivalence)
        return f"Between that build and merged-v18: {rec['note']}. After merged-v18, {shared}." + end
    return f"This family's task, geometry and asset files are unchanged from that build to this release; {shared}." + end


def ref_solution(mode: str, rec: dict) -> str:
    ev = rec["evidence"].get(mode)
    if not ev:
        return ("None in this release: the author is fixing this tier's oracle (it follows in a later pull request). "
                "`oracle = \"none\"`, human review (PROTOCOL §2.7).")
    same = since_evidence(rec)
    if mode == "privileged":
        return (f"`solution/solve.sh` copies `solution/trajectory.npz` (sha256 `{ev['trajectory_sha256'][:16]}…`) to "
                f"`/app/output/`: the trajectory the author's oracle (the RoboTangle planner on dev/jianwen) produced on "
                f"{run_words(ev)}, where the verifier scored it 1 in two fresh-process replays. " + same)
    return ("`solution/solve.sh` streams the recorded rows of the author's standard-mode oracle episode "
            "(`solution/oracle_qpos.npy`, one `joint_position` row per 25 ms control step, `hold`) through the client "
            f"(`solution/oracle_replay.py`). That episode scored 1 (live and fresh replay) on {run_words(ev)}. " + same)


def nop_words(base: str, mode: str, rec: dict) -> str:
    if rec["tier"] in ("easy", "medium", "hard"):
        return ("`nop` scored 0 on this base in both modes on the merged-v18 candidate build (lab `align_v18/cand_v18`, the "
                "pipeline's Harbor nop checks, 2026-10-05; frozen instance state identical); not yet re-run on this build.")
    run = NOP["runs"].get(base.removesuffix("-i00"), {}).get(mode)
    built = NOP["build"].split()[1]                       # "release <commit> image ..." (scripts/robotangle/nop_records.json)
    here = REL["release_commit"].startswith(built)
    if run and run["clean"] and run["reward"] == 0:
        return (f"`nop` scored 0 on {'this release' if here else 'the previous release'}'s build ({built}; {NOP['date']}, "
                f"{NOP['host']}; image {NOP['build'].split(' sha256:')[1][:12]}…, with the audited libuipc wheel)"
                + ("." if here else "; not yet re-run on this build."))
    if run:
        return (f"`nop`: no valid run yet. On the build of {built} an RTX 4090 (compute capability 8.9) refused this task's "
                "frozen PBD state, which was prepared on an RTX PRO 6000 Blackwell (compute capability 12.0, 188 SMs). "
                + (REL.get("blanket_nop_note") or "") + " Pending (docs/benchmarks/robotangle.md, GPU portability).")
    return f"`nop`: pending (`harbor run -p tasks/robotangle-{base}-{mode} -a nop`, docs/benchmarks/robotangle.md)."


def provenance(base: str, rec: dict) -> str:
    rows = [f"- Frozen instance: built by TopoGym source `{rec['creation_source']}` (graded package "
            f"`{rec['instance_package']}/topogym-{base}-privileged` on the lab host); bound to this release's runtime "
            f"(source `{REL['runtime']['source']['sha256'][:8]}`, tooling `{REL['tooling_sha256'][:8]}`). An exact-restore "
            "preflight on this build is pending (docs/benchmarks/robotangle.md, Pending)."]
    rows.append(f"- Frozen instance files (`instance.json`, `instance_assets/`): not in this directory. They are in the private HF "
                f"dataset `{ASSETS['repo']}` at `{ASSETS['revision'][:12]}`, under `instances/{base}/` "
                "(scripts/robotangle/assets.json pins each file's sha256). The image carries them, and "
                "`/opt/robotangle/stage_instance.py` copies this task's instance next to its `runtime_binding.json`, "
                "which names the instance's canonical sha256 and every asset's sha256. The tooling checks them again at "
                "every session start.")
    rows.append(f"- Release: dev/jianwen `{REL['release_commit'][:9]}` (task templates `{REL['template_commit'][:9]}`), "
                f"image `{IMAGE}` (images/robotangle/).")
    rows.append("- Name: RoboTangle is the published name of TopoGym (2026-10-07). Code identifiers keep the old name: the "
                "simulator package `topogym`, the tooling `rcb_topogym.py`, `TOPOGYM_*` variables.")
    return "\n".join(rows)


def rewrite_toml(s: str, base: str, rec: dict) -> str:
    s = text(s)
    s = re.sub(r'(?m)^simulator = "topogym"', 'simulator = "robotangle"', s)
    s = re.sub(r'(?m)^robot = "([a-z_]+)"', lambda m: f'robot = "{ROBOT.get(m.group(1), m.group(1))}"', s)
    s = re.sub(r'(?m)^author_name = "jianwen"', 'author_name = "Jianwen Lyu"', s)
    s = s.replace('authors = [{ name = "jianwen" }]', 'authors = [{ name = "Jianwen Lyu" }]')
    s = s.replace('"topogym",', '"robotangle",')
    s = re.sub(r'(?m)^tooling_version = "\d+"', f'tooling_version = "{REL["tooling_version"]}"', s)
    s = swap(s, EGRESS_OLD, EGRESS_NEW, f"{base} agent egress")
    s = re.sub(r'(?m)^oracle_evidence = .*\n', "", s)
    if {"privileged", "standard"} <= set(rec["evidence"]):   # a passing oracle run in both modes (docs/benchmarks/robotangle.md)
        s = re.sub(r'(?m)^oracle = .*\n', 'oracle = "full"\n', s, count=1)
    else:
        s = re.sub(r'(?m)^oracle = .*\n', f'oracle = "none"\noracle_evidence = {toml_str(evidence_text(base, rec))}\n', s, count=1)
    return s


CHANGE_0067 = {
    "privileged": (
        "- 2026-10-10 (review fixes): texts and limits; the pass rule is unchanged. For the families graded with a tolerant "
        "hold (blanket_flatten, knot_untying, lock_picking, rope_threading) the instruction and this README said that one "
        "replay had to reach the goal within the trajectory's own rows; the grader has applied R-hold since tooling v16 "
        "(2026-10-05: every replay may confirm within the hold; `strict_goal_reached` is reported, not required), and the "
        "texts now say so. New row cap: a trajectory may have at most the number of rows the instruction states "
        "(`RCB_MAX_STEPS` in both Dockerfiles; 200000 before, for every task), sized so that the verifier's two replays fit "
        "its timeout (by the step time the instruction states; a verifier that runs out of time leaves no reward); a "
        "longer trajectory is now `bad_trajectory`. The grader skips the review-frame pass when its time is short (the verdict and the events are "
        "committed before it), and an instance this host cannot reconstruct is `infra_error` 1 with `instance_mismatch` "
        "(it was a plain 0). The image, scene and frozen instance are unchanged, so the task keeps its name."),
    "standard": (
        "- 2026-10-10 (review fixes): the sim service and its 2.4 layer; the pass rule is unchanged. Malformed request "
        "fields (null or non-numeric `dt`, `video_fps`, `seconds`; a non-string `note`; `cameras` that is not a list of "
        "names) get a 400 before anything executes; they ended the episode with a 500 booked as an infrastructure error, a "
        "bad `note` after its chunk had run. A crash during a call is resumed like any other crash; the restart ended the "
        "episode as `call_watchdog` whenever it came back after the call's deadline, and now does so only when the "
        "watchdog's own output shows that it fired. After a crash in the first call the tick ledger is cut with the "
        "journal. An instance this host cannot reconstruct is `infra_error` 1 (startup record, replay, grader), and the "
        "startup record is final at once instead of after the collect hook's timeout. final.json is written as soon as the "
        "replay's verdict is committed, before the video is closed and the review frames are rendered. A live failure "
        "whose replay crashed is the agent's 0, not a grader error. The instruction's \"Time per call\" describes 2.4 "
        "(`max_call_wall_s`, `r.operation_status()`, 408 / 409), and the 200000-step runaway guard (`step_guard`) is "
        "stated there and in `/spec` (`max_control_steps`). The image, scene and frozen instance are unchanged, so the task "
        "keeps its name."),
}


def changes(mode: str) -> list[str]:
    """The README Change Log (PROTOCOL §2.8: published tasks fixed in place)."""
    grader = ("The standard grader counts a fresh replay that crashed without writing its verdict (e.g. CUDA out of memory) "
              "as a grader error; it counted as instance_mismatch." if mode == "standard" else "The graders are unchanged.")
    return [
        "- 2026-10-08: base image 0.2.19 -> 0.2.21, now public. The simulator, the frozen instances and the audited libuipc "
        "wheel are unchanged: on compute capability 8.9 and 12.x (e.g. RTX 4090, L40S, RTX PRO 6000) the physics runs the "
        "same libuipc code as before. New: the NVIDIA Vulkan ICD and EGL vendor files, and a second libuipc build of the "
        "audited recipe for compute capability 8.6 (RTX A6000 class), which the tooling selects at Session start on every "
        "other GPU, so knot_untying and rope_threading run there too. The runtime binding names both builds, and the tooling "
        "hash changes with the selection. The compose files reserve one GPU without `runtime: nvidia`, which with the "
        f"image's NVIDIA_VISIBLE_DEVICES=all could expose every GPU (Nyx needs exactly one). {grader} The scene, frozen "
        "instance and pass rule are unchanged, so the task keeps its name.",
        "- 2026-10-08 (2): the instance now also starts on a CPU of another instruction-set class. The asset generators run "
        "on numpy and OpenBLAS, whose SIMD kernels depend on the CPU: on a host without AVX-512 (e.g. AWS L4 / L40S "
        "instances) the pinned generator writes the frozen asset files with other bytes (floating-point noise up to 1e-8 m, "
        "face order), and the Session refused the instance (IPC and stored PBD states also refused their archive). Such a "
        "host now realizes the frozen recipe (`instance_realized`): the same asset files from the generator the runtime "
        "binding pins, archives that differ from this scene only in those bytes, and the frozen state, exactly or within "
        "the pose tolerance; the live episode and the fresh replay realize it alike. The graders"
        + (" and the sim service" if mode == "standard" else "") + " record `instance_realized` and `assets_exact`. A host "
        "that reproduces the frozen bytes runs exactly as before. The tooling hash changes; the image, scene, frozen instance "
        "and pass rule are unchanged, so the task keeps its name.",
        "- 2026-10-08 (3): base image 0.2.21 -> 0.2.22. The image adds, for the eight IPC instances (knot_untying, "
        "rope_threading), the rope volume mesh each was frozen with (`instance_assets/frozen_assets/rope_volume.npz`, the sha256 "
        "its asset identity records), and the tooling uses it instead of regenerating it: tetgen's interior points depend on "
        "the CPU's floating-point rounding, and on CPUs without AVX-512 knot_untying medium and hard got another mesh, which "
        "their frozen settled state does not fit. Nothing else in the image changes. The scene, frozen instance and pass rule are unchanged, so the task "
        "keeps its name.",
        CHANGE_0067[mode],
    ] + ([
        "- 2026-10-10 (2): `tests/grade.py`: after a live success, a replay process that died without a result (e.g. CUDA out "
        "of memory in the collect hook) is `infra_error` 1 together with `grader_error` 1; it was `grader_error` 1 with "
        "`infra_error` 0, which a reader of `infra_error` alone (PROTOCOL §2.6) took for the agent's 0. A `final.json` that "
        "is not a JSON object is `infra_error` 1 (it left no reward). Reward 0 in both cases, as before; the pass rule is "
        "unchanged, so the task keeps its name.",
    ] if mode == "standard" else [])


def rewrite_readme(s: str, base: str, mode: str, rec: dict) -> str:
    s = text(s).replace("from `tests/instance.json`", "from the frozen instance (`/tests/instance.json`, staged from the image and "
                        "checked against `tests/runtime_binding.json`)")
    s = re.sub(r"(?ms)^## Reference solution\n.*?(?=^## )", "## Reference solution\n" + ref_solution(mode, rec) + "\n\n", s)
    nop = nop_words(base, mode, rec)
    s = review_fixes(s, "README.md", base, mode)
    cap = (f"\nA trajectory may have at most {row_cap(base)} rows (`RCB_MAX_STEPS`: two replays must fit the verifier's "
           "timeout; a longer one is\n`bad_trajectory`)." if mode == "privileged" else "")
    s = re.sub(r"(?ms)^(## Verification\n.*?)(?=^## )", lambda m: m.group(1).rstrip() + cap + "\n\n" + nop + "\n\n", s)
    return (s.rstrip() + "\n\n### Provenance\n" + provenance(base, rec) + "\n\n### Change Log\n"
            + "\n".join(changes(mode) + change_r2(base, mode) + change_r3(mode) + [CHANGE_EGRESS]) + "\n")


# ---------------------------------------------------------------- fixes of the round-2 review (2026-10-10, board 0067 R2)
# Text fixes on top of review_fixes, with the same rule: every replacement asserts that its source text is still there.
GRIP_OLD = "native drive target (m, limits 0 .. 0.8; open/closed targets in robot_spec)"
GRIP_NEW = ("native drive target (rad, limits 0 .. 0.8: 0 = open, 0.8 = closed, the Robotiq 2F-85's driver joint; "
            "open/closed targets in robot_spec)")
EXPOSED_OLD = ("The success implementation and internal measurements are not exposed;\n"
               "  the task requirements above still apply in full.")
EXPOSED_NEW = ("The success implementation is not exposed, and of the simulator's internal\n"
               "  measurements only the safety readings of `meta[\"safety\"]` are (listed under Action types, below); the task\n"
               "  requirements above still apply in full.")
WAIT_S = 3600             # v2_4/rcb_client.Robot.__init__'s default timeout (600 s until 2026-10-10)
WAIT_OLD = ("(default connection budget: 600 seconds,", "(default timeout 600 s)")
WAIT_NEW = (f"(default connection budget: {WAIT_S} seconds,", f"(default timeout {WAIT_S} s)")
# the call's image budget of the standard service (review round 3), read from its source so that the texts state what is enforced
_SERVER = (SHARED / "standard" / "sim" / "server.py").read_text()
MAX_FRAMES, DEPTH_FRAME = (int(re.search(rf"^{k} = (\d+)", _SERVER, re.M).group(1)) for k in ("MAX_FRAMES", "DEPTH_FRAME"))
FRAMES_AT = "- Both action types: no gripper target goes lower than"
FRAMES_NEW = (f"- One call returns at most {MAX_FRAMES} images (`spec[\"max_frames_per_call\"]`: cameras x frames; a frame with\n"
              f"  `depth=\"frames\"` counts {DEPTH_FRAME}). A request that would exceed it is answered 400 before anything moves: ask for\n"
              "  fewer cameras, a lower `video_fps` or a shorter call. Rows that take longer than planned (the speed limit, `ee_pose`)\n"
              "  stop adding frames at that number; the motion is executed in full and `meta[\"frames_skipped\"]` counts them.\n")
OPENING_NEW = ("\n  The proprio group `gripper_opening` (`res.group(\"gripper_opening\")`) is the measured gap between each gripper's finger\n"
               "  pads in metres (0 = the pads touch); the gripper entries of `joint_pos` are in the unit of the gripper command above.")


def panda(base: str) -> bool:
    return 'robot = "panda_robotiq"' in (PKG / f"{base}-privileged" / "task.toml").read_text()


def native(base: str) -> bool:
    return "_native_gripper" in (PKG / f"{base}-standard" / "instruction.md").read_text()


def review_fixes_r2(s: str, base: str, mode: str) -> str:
    """Round-2 text fixes of an instruction.md. The Robotiq 2F-85's native drive coordinate is its driver joint angle
    (topogym/robot/panda_robotiq: gripper_position_rad, limits 0 .. 0.8 rad, GraspDescription open 0 / closed 0.8); the
    release's texts gave it in metres. ALOHA's native coordinate is the finger rail in metres, as its texts say."""
    assert (GRIP_OLD in s) == (panda(base) and native(base)), f"{base} {mode}: the gripper unit text and the robot disagree"
    if GRIP_OLD in s:
        s = swap(s, GRIP_OLD, GRIP_NEW, f"{base} {mode} Robotiq unit")
    if mode == "standard":
        s = swap(s, EXPOSED_OLD, EXPOSED_NEW, f"{base} safety readings")
        for a, b in zip(WAIT_OLD, WAIT_NEW):
            s = swap(s, a, b, f"{base} Robot() wait")
        s = swap(s, "`meta[\"clipped\"]` says so.\n- `ee_pose`", "`meta[\"clipped\"]` says so." + OPENING_NEW + "\n- `ee_pose`",
                 f"{base} gripper_opening")
        s = swap(s, FRAMES_AT, FRAMES_NEW + FRAMES_AT, f"{base} image budget")      # round 3
    return s


def change_r2(base: str, mode: str) -> list[str]:
    """The round-2 Change Log entry; none for a task whose files did not change (privileged tasks of the ALOHA families)."""
    unit = ("The instruction gave the Robotiq gripper's native drive target in metres; it is the driver joint angle in "
            "rad (0 = open, 0.8 = closed). ") if panda(base) and native(base) else ""
    if mode == "privileged":
        return [f"- 2026-10-10 (review round 2): text only. {unit}Nothing else changes, so the task keeps its name."] if unit else []
    opening = ("The proprio group `gripper_opening` is now the measured gap between the finger pads in metres "
               "(`Session.gripper_width`); it repeated the gripper's native drive coordinate "
               + ("(rad, 0 = open .. 0.8 = closed)" if panda(base) else "(the finger rail position, m)") +
               " under a description that called it an opening. `/spec` now describes the gripper entries of `joint_pos` "
               "and `joint_vel` as that drive coordinate. " if native(base) else
               "The proprio group `gripper_opening` is unchanged here (this instance commands opening widths); its `/spec` "
               "description is more precise. ")
    return ["- 2026-10-10 (review round 2): the sim service, the client and the texts; the pass rule is unchanged. A request "
            "field holding a JSON integer beyond the float range (`dt`, `video_fps`, `seconds`) gets a 400 and moves nothing; "
            "it ended the episode with a 500 booked as an infrastructure error. " + opening + unit +
            "The Rules said that internal measurements are not exposed, while the instruction documents the safety "
            "readings of `meta[\"safety\"]`; the sentence now says so (what is exposed is unchanged). The client's `Robot()` "
            f"waits up to {WAIT_S} s for the service (600 s before) and prints its progress, and `cameras=\"name\"` is one "
            "camera, not its characters. The image, scene, frozen instance, tooling and grader are unchanged, so the task "
            "keeps its name."]


CHANGE_EGRESS = (
    "- 2026-10-10 (owner decision, board 0072): the agent's network egress is restricted to the model APIs (`[agent] "
    "network_mode = \"allowlist\"`, the hosts of `scripts/set_agent_egress.py`; since 2026-10-11 these include the package registries, PyPI and the Debian / Ubuntu archives, so that `pip install` and `apt-get install` work); it was open before (Harbor's default), and "
    "agents could download upstream sources, reference solutions and robot models from their own shell: the image's "
    "simulator package names the address of an upstream demonstration (`reference_scene.json` `source_url`; "
    "docs/benchmarks/robotangle.md, Network policy), which one trial downloaded. The image, scene, frozen instance, "
    "tooling and pass rule are unchanged, so the task keeps its name; results from before this date were obtained with "
    "open egress and are withdrawn (RoboTangle is run again from scratch).")


def change_r3(mode: str) -> list[str]:
    """The round-3 Change Log entry (standard tasks: the service, the 2.4 layer and the client)."""
    if mode != "standard":
        return []
    return ["- 2026-10-10 (review round 3): the sim service, its 2.4 layer and the client; the pass rule is "
            "unchanged. A camera named more than once in `cameras` is rendered and returned once. A service that "
            "has given up on the episode (it could not start it, or could not resume it after its crashes) answers "
            "every request with 409 and the reason, and `Robot()` / `wait_ready()` raise `EpisodeOver` at once; "
            "before, nothing answered and they waited out their timeout (up to an hour). `/spec`'s description of "
            "the proprio group `gripper_opening` says that a gripper closed on cloth reads 0 (it said that a "
            "gripper closed on an object stops above 0, which holds for rigid objects only); the values are "
            f"unchanged. One call returns at most {MAX_FRAMES} images (`/spec` `max_frames_per_call`: cameras x frames, a "
            f"frame with per-frame depth counts {DEPTH_FRAME}): a request that would exceed it is a 400 before anything "
            "runs, and rows that take longer than planned stop adding frames there (`meta[\"frames_skipped\"]`). "
            "Before, a call had no such bound: one long observation at the full frame rate could hold more frames "
            "than the sidecar's memory and get the service killed, so a trial that ended `sim_crashed*` or with "
            "`resource_service_oom` right after such a request before this date was that. The image, scene, frozen "
            "instance, tooling and grader are unchanged, so the task keeps its name."]


def binding(base: str, inst_dir: pathlib.Path | None = None) -> bytes:
    """The task's runtime binding: the upstream lock (instance and asset hashes) with this release's tooling and runtime.
    The frozen instance must be the pinned one in assets.json; with inst_dir (a local copy), its bytes are checked too."""
    lock = json.loads((PKG / f"{base}-privileged" / "runtime_binding.upstream.json").read_text())
    pinned = ASSETS["instances"].get(base, {}).get("instance_sha256")
    assert lock["instance_sha256"] == pinned, f"{base}: the bound instance is not the one pinned in assets.json"
    prefix = f"instances/{base}/"
    pinned_assets = {k[len(prefix):]: v for k, v in ASSETS["files"].items() if k.startswith(prefix + "instance_assets/")}
    # Frozen generated assets (image 0.2.22: knot_untying's rope volume meshes, rcb_topogym._install_frozen_assets), added to
    # the instance after the upstream lock: each is a generated file whose sha256 the instance's asset_identity records.
    frozen = {k: v for k, v in pinned_assets.items() if k.startswith("instance_assets/frozen_assets/")}
    lock["asset_files"] = {**lock["asset_files"], **frozen}
    assert lock["asset_files"] == pinned_assets, f"{base}: instance_assets pinned in assets.json differ from the binding"
    if inst_dir is not None and frozen:
        identity = json.loads((inst_dir / "instance.json").read_text()).get("asset_identity") or {}
        for rel, want in frozen.items():
            assert identity.get(pathlib.PurePosixPath(rel).name) == want, f"{base}: {rel} is not the generated asset it records"
    if inst_dir is not None:
        canon = json.dumps(json.loads((inst_dir / "instance.json").read_text()), sort_keys=True, separators=(",", ":"), allow_nan=False)
        assert lock["instance_sha256"] == sha(canon.encode()), f"{base}: instance.json is not the bound instance"
        assets = {p.relative_to(inst_dir).as_posix(): sha(p.read_bytes()) for p in sorted((inst_dir / "instance_assets").rglob("*")) if p.is_file()}
        assert lock["asset_files"] == assets, f"{base}: instance_assets differ from the binding"
    lock["tooling_sha256"] = sha((SHARED / "rcb_topogym.py").read_bytes())
    lock["runtime"] = REL["runtime"]
    # both libuipc builds the tooling chooses from by the GPU's compute capability (rcb_topogym.select_uipc_build), by their
    # uipc-build.json sha256; the runtime's own uipc_build_sha256 stays the audited build, the image's default
    lock["uipc_builds"] = {name: b["uipc_build_sha256"] for name, b in sorted(REL["uipc_builds"].items())}
    return (json.dumps(lock, indent=2) + "\n").encode()


def put(dst: pathlib.Path, data: bytes, exe: bool = False) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(data)
    os.chmod(dst, 0o755 if exe else 0o644)


def copy_tree(src: pathlib.Path, dst: pathlib.Path) -> None:
    for p in sorted(src.rglob("*")):
        if p.is_file():
            put(dst / p.relative_to(src), p.read_bytes())
        elif p.is_dir():
            (dst / p.relative_to(src)).mkdir(parents=True, exist_ok=True)


GPU_OLD = ("# Nyx renders through Vulkan, so the container needs the NVIDIA graphics libraries as well as compute: `runtime: nvidia`\n"
           "# with NVIDIA_DRIVER_CAPABILITIES=all (`capabilities: [gpu]` alone injects compute only).\n")
GPU_NEW = ("# Nyx renders through Vulkan: the device reservation below passes exactly one GPU (Nyx needs exactly one), and\n"
           "# NVIDIA_DRIVER_CAPABILITIES=all makes the container toolkit mount the driver's graphics libraries, which the image's\n"
           "# Vulkan ICD and EGL vendor files name (images/robotangle/Dockerfile). No `runtime: nvidia`: with the image's\n"
           "# NVIDIA_VISIBLE_DEVICES=all it can expose every GPU of the host.\n")


def gpu_lines(name: str, s: str) -> str:
    """Compose files: one GPU through the device reservation only, as images/robopaint/ (no `runtime: nvidia`)."""
    if not name.endswith("docker-compose.yaml"):
        return s
    assert s.count(GPU_OLD) == 1 and len(re.findall(r"(?m)^\s*runtime: nvidia\n", s)) == 1, f"{name}: unexpected GPU block"
    s = re.sub(r"(?m)^\s*runtime: nvidia\n", "", s.replace(GPU_OLD, GPU_NEW))
    assert "count: 1" in s and "capabilities: [gpu]" in s and "NVIDIA_DRIVER_CAPABILITIES: all" in s, name
    return s


def image_lines(s: str) -> str:
    s = re.sub(r"(?m)^FROM\s+" + IMAGE_RX.pattern, "FROM " + IMAGE, s)
    return re.sub(r"(?m)^(\s*image:\s*)" + IMAGE_RX.pattern, lambda m: m.group(1) + IMAGE, s)


STAGE = "RUN python /opt/robotangle/stage_instance.py {base} {dest} --purge   # the frozen instance, from the image (scripts/robotangle/assets.json), checked against runtime_binding.json"
ENTRY = ('    # The frozen instance comes from the image (scripts/robotangle/assets.json): the entrypoint stages it next to a copy of\n'
         '    # runtime_binding.json and checks it (images/robotangle/stage_instance.py), then runs the command.\n'
         '    entrypoint: ["sh", "-c", "python /opt/robotangle/stage_instance.py {base} ' + STAGED + ' --binding /srv/runtime_binding.json && exec \\"$$@\\"", "stage"]\n')


def staged(name: str, s: str, base: str) -> str:
    """Task files that stage the frozen instance from the image instead of copying it from the task directory."""
    def sub(a: str, b: str) -> str:
        assert s.count(a) == 1, f"{base} {name}: expected one {a!r}"
        return s.replace(a, b)
    if name == "environment/Dockerfile" and "COPY instance.json /app/instance.json\n" in s:
        s = sub("COPY instance.json /app/instance.json\n", "")
        s = sub("COPY instance_assets/ /app/instance_assets/", STAGE.format(base=base, dest="/app"))
    elif name == "tests/Dockerfile" and "instance_assets" in s:
        s = sub("COPY grade.py instance.json rcb_topogym.py test.sh /tests/", "COPY grade.py rcb_topogym.py test.sh /tests/")
        s = sub("COPY instance_assets/ /tests/instance_assets/", STAGE.format(base=base, dest="/tests"))
    elif name == "environment/docker-compose.yaml" and "RCB_INSTANCE: /srv/instance.json" in s:
        s = sub("RCB_INSTANCE: /srv/instance.json", f"RCB_INSTANCE: {STAGED}/instance.json")
        s = sub("    command: sh /srv/run.sh\n", ENTRY.format(base=base) + "    command: sh /srv/run.sh\n")
    return s


def render(base: str, out: pathlib.Path, inst_src: pathlib.Path | None = None) -> list[pathlib.Path]:
    rec = REL["bases"][base]
    dirs = []
    for mode in ("privileged", "standard"):
        t = out / f"robotangle-{base}-{mode}"; up = PKG / f"{base}-{mode}"; dirs.append(t)
        rd = lambda n: (up / n).read_text()  # noqa: E731
        put(t / "task.toml", rewrite_toml(rd("task.toml"), base, rec).encode())
        put(t / "README.md", rewrite_readme(rd("README.md"), base, mode, rec).encode())
        ins = text(rd("instruction.md")).replace("RoboTangle", "RoboTangle (simulator package `topogym`)", 1)
        put(t / "instruction.md", review_fixes_r2(review_fixes(ins, "instruction.md", base, mode), base, mode).encode())
        for n in ("environment/Dockerfile", "environment/docker-compose.yaml", "tests/Dockerfile", "tests/docker-compose.yaml"):
            if (up / n).is_file():
                assert "RCB_MAX_CALL_WALL_S" not in rd(n) and "RCB_MAX_STEPS" not in rd(n), f"{base} {n}: the texts assume the defaults"
                put(t / n, limits_env(n, staged(n, gpu_lines(n, image_lines(rd(n))), base), base, mode).encode())
        put(t / "tests/test.sh", (up / "tests/test.sh").read_bytes(), exe=True)
        lock = binding(base, inst_src)
        tool = (SHARED / "rcb_topogym.py").read_bytes()
        if mode == "privileged":
            for d in ("environment", "tests"):
                put(t / d / "runtime_binding.json", lock)
                put(t / d / "rcb_topogym.py", tool)
            put(t / "tests/grade.py", (SHARED / "privileged/grade.py").read_bytes())
            traj = ORC / base / "privileged.npz"
            if traj.is_file():
                put(t / "solution/trajectory.npz", traj.read_bytes())
                put(t / "solution/solve.sh", (
                    "#!/bin/bash\n# Reference solution (privileged): the trajectory the author's oracle produced and the verifier scored 1\n"
                    "# on the evidence run named in README.md (Reference solution). Uses nothing but the recorded file.\n"
                    "set -euo pipefail\nmkdir -p /app/output\ncp /solution/trajectory.npz /app/output/trajectory.npz\n").encode(), exe=True)
        else:
            for rel, src in LAYER.items():
                put(t / rel, src.read_bytes())
            for n in ("server.py", "replay.py", "finalize.sh"):
                put(t / "environment/sim" / n, (SHARED / "standard/sim" / n).read_bytes())
            put(t / "environment/sim/runtime_binding.json", lock)
            put(t / "environment/sim/rcb_topogym.py", tool)
            put(t / "tests/grade.py", (SHARED / "standard/grade.py").read_bytes())
            put(t / "tests/runtime_binding.json", lock)
            traj = ORC / base / "standard.npz"
            if traj.is_file():
                with zipfile.ZipFile(traj) as z:
                    put(t / "solution/oracle_qpos.npy", z.read("actions.npy"))
                put(t / "solution/oracle_meta.json", (json.dumps({"K": 1, "interpolate": "hold", "rows": "the recorded "
                    "joint_position rows of the evidence episode (README.md, Reference solution)"}, indent=1) + "\n").encode())
                put(t / "solution/oracle_replay.py", (SHARED / "standard/solution/oracle_replay.py").read_bytes())
                put(t / "solution/solve.sh", (SHARED / "standard/solution/solve.sh").read_bytes(), exe=True)
    for t in dirs:
        TC.normalize(t)          # leaves the layer alone: scripts/eai_standard/ is a shared source (task_conventions)
    return dirs


def snapshot(d: pathlib.Path) -> dict:
    return {p.relative_to(d).as_posix(): (p.read_bytes(), 0o755 if os.stat(p).st_mode & 0o100 else 0o644)   # exec bit only
            for p in sorted(d.rglob("*")) if p.is_file()}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true"); ap.add_argument("--list", action="store_true")
    ap.add_argument("--assets", type=pathlib.Path, help="a local copy of the pinned HF dataset (assets.py fetch)")
    ap.add_argument("bases", nargs="*")
    a = ap.parse_args(argv)
    bases = a.bases or sorted(REL["bases"])
    if a.list:
        for b in bases:
            r = REL["bases"][b]
            print(f"{b:34s} instance {r['creation_source']}  " + "  ".join(f"{m}: {e['release']}:{e['source']}" for m, e in r["evidence"].items()) or "oracle pending")
        return 0
    bad = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        for b in bases:
            inst = a.assets / "instances" / b if a.assets else None
            if inst is not None and not (inst / "instance.json").is_file():
                bad.append(f"{b}: no frozen instance at {inst}"); continue
            for t in render(b, tmp / "out", inst):
                cur = TASKS / t.name
                if a.check:
                    if not cur.is_dir() or snapshot(cur) != snapshot(t):
                        bad.append(f"tasks/{t.name}: differs from a fresh render (run scripts/robotangle/mk_tasks.py)")
                else:
                    if cur.exists():
                        shutil.rmtree(cur)
                    shutil.copytree(t, cur, symlinks=False)
        known = {f"robotangle-{b}-{m}" for b in REL["bases"] for m in ("privileged", "standard")}
        stray = sorted(p.name for p in TASKS.glob("robotangle-*") if p.name not in known)
        bad += [f"tasks/{n}: not in scripts/robotangle/release.json" for n in stray]
        tools = {sha(p.read_bytes()) for p in TASKS.glob("robotangle-*/**/rcb_topogym.py")}
        if tools - {sha((SHARED / "rcb_topogym.py").read_bytes())}:
            bad.append("a task's rcb_topogym.py differs from scripts/robotangle/shared/rcb_topogym.py")
    for b in bad:
        print("FAIL", b)
    if not bad:
        print(f"ok robotangle: {2 * len(bases)} task dirs {'match a fresh render' if a.check else 'rendered'} "
              f"(release {REL['release_commit'][:9]}, image {IMAGE})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
