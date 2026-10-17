#!/usr/bin/env python3
"""Render the tasks of RoboARC (BENCH below; docs/benchmarks/<BENCH>.md): the MuJoCo release, which replaces the
Genesis release (user decision 2026-10-13: the previous Genesis -i00 tasks are deleted; until then this generator
lived in its own directory as a benchmark of its own):
tasks/<BENCH>-<family>-<NN>-i01-privileged and its standard twin -standard (eai-standard/2.4); NN is the base's number in
its family and the difficulty is task.toml's `difficulty` (roboarc_names.json: old base -> new base, family, number,
difficulty; owner, 2026-10-13).

The benchmark's name is one parameter, BENCH: the task prefix, the image (ghcr.io/mll-lab-nu/eai-<BENCH>,
images/<BENCH>/VERSION) and this directory (scripts/<BENCH>/). Renaming it: BENCH here and in
scripts/robotangle/release_rebuild.py on dev/robotangle_mujoco (--bench), `git mv` of scripts/<BENCH>/,
images/<BENCH>/ and docs/benchmarks/<BENCH>.md, and the registration lines listed in docs/benchmarks/<BENCH>.md
("Registration").

usage: python3 scripts/<BENCH>/mk_tasks.py [--check] [--list] [--assets <dir>] [base ...]
       python3 scripts/<BENCH>/mk_tasks.py --dev <dev.json> --out <dir> base ...
  no base   every base in release.json
  --check   write nothing; exit 1 if a task would change, or if an identity check fails
  --list    print the bases with their evidence
  --assets  a local copy of the pinned HF dataset (the instances/<base>/ layout): also check the frozen instances' bytes
            against the runtime bindings (without it, the pins in assets.json are compared)
  --dev     local dev task dirs, written to --out (never tasks/): dev.json names a locally built image ("image":
            reference, id; "runtime" and "uipc_builds" as its installed_runtime() reports them) and, per base, a local
            frozen instance directory ("instance") and the reference trajectory both modes replay ("reference")

Every base is a MuJoCo base (release.json physics_engine "mujoco"): the numpy / OpenBLAS SIMD masking in every container
that runs a Session, render_bridge.py next to every copy of the tooling and its sha256 in the binding
(render_bridge_sha256); the families the tooling renders with nyx_direct.py (TASKS renderer "direct") ship that file too
(nyx_direct_sha256). A base on a GPU physics profile (release.json gpu_physics: the blanket's CUDA cloth step) keeps
the GPU for its physics as well as for Nyx.

Inputs, all in this directory, written by scripts/robotangle/release_rebuild.py --onto on dev/robotangle_mujoco
(Python standard library only, plus scripts/task_conventions.normalize):
  release.json   the release (dev/robotangle_mujoco commit, simulator source, runtime, tooling) and, per base, where its
                 frozen instance comes from (ported_from: the RoboARC Genesis base whose scene it ports; template:
                 the base whose texts a new variation starts from), its texts' facts (grasp_rules, physics_dt_s) and
                 the oracle runs that are its evidence
  shared/        the tooling rcb_topogym.py with render_bridge.py and nyx_direct.py (dev/robotangle_mujoco's), the
                 graders, the sim service adapter (server.py, replay.py, finalize.sh), the standard oracle player
  scripts/eai_standard/v2_4/ + scripts/eai_standard/   the eai-standard/2.4 layer, copied unchanged
  packages/      per task, the upstream texts (task.toml, README.md, instruction.md, Dockerfiles, compose files, test.sh):
                 the RoboARC base's texts it ports, renamed, with the family's own texts over them for a changed or
                 new design; and the instance's lock (runtime_binding.upstream.json)
  oracles/       the references (privileged.npz; standard.npz is the same file, or, where release.json's standard evidence
                 has "speed_rule", the reference re-timed to the standard service's joint-speed rule)
  assets.json    the frozen instances, not in git: the private HF dataset eai-v2-internal/robotangle-assets (the same
                 dataset as RoboARC's, instances/<base>/), pinned by commit and sha256. The image carries them; a task
                 keeps its runtime_binding.json and stages its instance from the image (/opt/robotangle/stage_instance.py).
Nothing at run time imports repository code: the tooling and the sim layer are copies (PROTOCOL D9).
"""
from __future__ import annotations
import argparse, filecmp, hashlib, json, math, os, pathlib, re, shutil, sys, tempfile, tomllib, zipfile

BENCH = "roboarc"   # the benchmark's name: task prefix, image eai-<BENCH>, scripts/<BENCH>/, docs/benchmarks/<BENCH>.md
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TASKS = ROOT / "tasks"
SHARED, PKG, ORC = HERE / "shared", HERE / "packages", HERE / "oracles"
sys.path.insert(0, str(ROOT / "scripts"))
import task_conventions as TC  # noqa: E402  the protocol's conventions: every generator ends with normalize(task_dir)

# The agent's time cutoff per mode (PROTOCOL §2.12): this benchmark's own number, written into every task's `[agent]
# timeout_sec`, the one source; normalize renders from it the instruction's closing `## Time limit`, the README row and
# the sim service's wall clock. To change it (an owner decision; the pull request states old -> new), edit it here and
# regenerate.
# The packages' task.toml carry the upstream number (21600 s); this one replaces it in both modes (PROTOCOL §2.15).
CUTOFF_SEC = 10800

REL = json.loads((HERE / "release.json").read_text())


def tooling_check() -> list[str]:
    """The tooling files in shared/ are the release's (release.json tooling_sha256, render_bridge_sha256,
    nyx_direct_sha256): a render or a check on any other copy is refused (2026-10-13: a rename had put an older
    rcb_topogym.py under the release, and the bindings were stamped with it)."""
    bad = []
    for key, name in (("tooling_sha256", "rcb_topogym.py"), ("render_bridge_sha256", "render_bridge.py"), ("nyx_direct_sha256", "nyx_direct.py")):
        want = REL.get(key)
        if want and REL.get("bases"):
            f = HERE / "shared" / name
            got = hashlib.sha256(f.read_bytes()).hexdigest() if f.is_file() else "missing"
            if got != want:
                bad.append(f"scripts/{BENCH}/shared/{name}: sha256 {got[:16]}, release.json {key} {want[:16]}")
    return bad


# Agent egress (owner, 2026-10-10 / 10-11, board 0072): the model APIs and the package registries. The packages' task.toml carry the release's line (open
# egress); rewrite_toml puts the two lines `scripts/set_agent_egress.py allowlist` writes, with that script's HOSTS (one
# list for every task: ci_checks/check-verifier-isolation.sh).
EGRESS_OLD = "# egress: Harbor default (public). `scripts/set_agent_egress.py allowlist` closes it to the model APIs.\n"
_HOSTS = re.search(r"(?ms)^HOSTS = \[(.*?)\]", (ROOT / "scripts/set_agent_egress.py").read_text()).group(1)
EGRESS_NEW = ('network_mode = "allowlist"      # model APIs and package registries (scripts/set_agent_egress.py); PROTOCOL §2.11\n'
              "allowed_hosts = [" + ", ".join(f'"{h}"' for h in re.findall(r'"([^"]+)"', _HOSTS)) + "]\n")
ASSETS = json.loads((HERE / "assets.json").read_text())        # the pinned HF dataset (scripts/roboarc/assets.py)
STAGED = "/tmp/robotangle-instance"                             # where the standard sim stages its instance   # nop runs on this release's build (very_easy / easier)
VERSION = (ROOT / "images" / BENCH / "VERSION").read_text().strip()
IMAGE = f"ghcr.io/mll-lab-nu/eai-{BENCH}:{VERSION}"
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
    s = re.sub(r"\btopogym-([a-z0-9-]+-i\d\d-(?:privileged|standard))\b", BENCH + r"-\1", s)
    s = s.replace("docs/benchmarks/robotangle.md", f"docs/benchmarks/{BENCH}.md")   # the released texts' page
    s = IMAGE_RX.sub(IMAGE, s)
    for a, b in ROBOT_WORDS.items():
        s = s.replace(a, b)
    s = s.replace("TopoGym", "RoboARC").replace(*PROTO)
    s = re.sub(r"\bhis (?=[a-z]+(?:_[a-z0-9]+)*_v\d)", "the ", s)
    return s.replace("his qualification record", "the author's qualification record")


# ---------------------------------------------------------------- MuJoCo bases (dev/robotangle_mujoco, the MuJoCo release)
MUJOCO_WORDS = (("(ALOHA 2, Genesis)", "(ALOHA 2, MuJoCo)"),
                ("(Franka Panda + Robotiq 2F-85, Genesis)", "(Franka Panda + Robotiq 2F-85, MuJoCo)"),
                ("RoboARC on Genesis 1.2.1", "RoboARC on MuJoCo 3.14.0"),
                ("`topogym`) on Genesis 1.2.1 physics", "`topogym`) on MuJoCo 3.14.0 physics"),
                ('"genesis",', '"mujoco",'), ("(Genesis initialises once)", "(one simulator per process)"))
STEP_RX = re.compile(r"One control step takes about ([0-9.]+) s of wall clock")
# The released texts of the families graded with grading replays (topogym_rules.grading_replay_words, README's
# determinism sentence) say their physics runs on the GPU and is not bit-deterministic; on MuJoCo it runs on the CPU in
# float64 (a cloth's step on a deterministic GPU solver) and a fresh-process replay reproduces the run on the same host.
# The grading-replay rule itself (the hold, its tolerances) is unchanged in the tooling and stays in the text.
def determinism_words(gpu: bool) -> tuple:
    phys = ("Its cloth step runs on the GPU on a deterministic solver and the rest on the CPU (MuJoCo, float64)" if gpu else
            "This family's physics runs on the CPU (MuJoCo, float64)")
    return (("This family's physics runs on the GPU, which is not bit-deterministic, so a replay can differ slightly from "
             "your own run:", phys + ", so a replay reproduces your own run on the same host; the rule is kept as a margin:"),
            ("This family's physics runs on the GPU, which is not bit-deterministic, so that replay can differ slightly from "
             "the live episode:", phys + ", so that replay reproduces the live episode on the same host; the rule is kept as "
             "a margin:"),
            ("if this GPU family's episode has not ended", "if this family's episode has not ended"),
            ("(GPU physics is not bit-deterministic; the CPU rigid families' is, on one host)",
             "(the deterministic GPU cloth step and MuJoCo replay bit for bit on one host; the rule does not rely on it)" if gpu
             else "(MuJoCo on the CPU replays bit for bit on one host; the rule does not rely on it)"))
README_GPU_RX = re.compile(r"The physics runs on the GPU, which is not bit-deterministic: the\s+final-state hashes \(`deterministic`\) "
                           r"are diagnostic")


def tooling_constant(name: str):
    """A module-level constant of the shipped tooling (shared/rcb_topogym.py), read from its source: `NAME = <literal>`
    or `NAME = dict(k=<literal>, ...)`. The texts state what the tooling grades (owner, 2026-10-12: text and grader
    can never diverge)."""
    import ast
    for node in ast.parse((SHARED / "rcb_topogym.py").read_text()).body:
        if isinstance(node, ast.Assign) and [getattr(t, "id", None) for t in node.targets] == [name]:
            v = node.value
            if isinstance(v, ast.Call) and getattr(v.func, "id", None) == "dict" and not v.args:
                return {k.arg: ast.literal_eval(k.value) for k in v.keywords}
            return ast.literal_eval(v)
    raise KeyError(f"shared/rcb_topogym.py has no constant {name}")


CONTACT_RX = re.compile(r"A success with deep interpenetration \(a task contact deeper than (?P<deep>[0-9.]+) mm, or deeper than "
                        r"(?P<sus>[0-9.]+) mm for at least (?P<win>[0-9.]+) s: (?P<ticks>\d+) consecutive physics ticks; for a "
                        r"finger contact with a held piece (?P<hdeep>[0-9.]+) mm, or (?P<hsus>[0-9.]+) mm for (?P<hwin>[0-9.]+) s\)")
BREAKDOWN_RX = re.compile(r"(task contact deeper than )([0-9.]+)( mm(?:\)|: the episode| is a simulator breakdown))")


def contact_text(s: str, rec: dict) -> str:
    """The contact-review sentence with the values of the shipped tooling's CONTACT_RULE and BREAKDOWN_PENETRATION_M (owner
    decision 2026-10-12, option a: the released texts said 1 mm where the MuJoCo tooling grades 2 mm). The window in
    physics ticks: window_s over the base's physics tick (release.json physics_dt_s, recorded from its instance), else
    the released count, which assumes the released 2.5 ms tick."""
    c, mm = tooling_constant("CONTACT_RULE"), (lambda v: f"{v * 1000:g}")
    def sub(m: re.Match) -> str:
        if rec.get("physics_dt_s"):
            ticks = max(1, math.ceil(c["window_s"] / float(rec["physics_dt_s"]) - 1e-12))
        else:
            assert float(m["win"]) == c["window_s"], "the released tick count assumes the released window"
            ticks = int(m["ticks"])
        return (f"A success with deep interpenetration (a task contact deeper than {mm(c['deep_m'])} mm, or deeper than "
                f"{mm(c['sustained_m'])} mm for at least {c['window_s']:g} s: {ticks} consecutive physics ticks; for a finger "
                f"contact with a held piece {mm(c['held_deep_m'])} mm, or {mm(c['held_sustained_m'])} mm for {c['window_s']:g} s)")
    s, n = CONTACT_RX.subn(sub, s)
    assert n <= 1, "more than one contact-review sentence"
    if n:
        s = BREAKDOWN_RX.sub(lambda m: m[1] + mm(tooling_constant("BREAKDOWN_PENETRATION_M")) + m[3], s)
    return s


GRASP_RX = re.compile(r"(?m)^((?:- )?(?:Grasping|Grippers): )((?:assisted grasping \(|physical grasping)[^\n]*)\.$")


def grasp_text(s: str, rec: dict) -> str:
    """A MuJoCo base's grasping rule in the words the tooling's Session.grasp_rules() emits for its instance (release.json
    grasp_rules, read in the release image by release_rebuild.py): on MuJoCo the weld also lets go above the robot's
    slip force averaged over its window, and the Robotiq after losing finger contact (owner decision 2026-10-12)."""
    if not (is_mujoco(rec) and rec.get("grasp_rules")):
        return s
    s, n = GRASP_RX.subn(lambda m: m[1] + rec["grasp_rules"] + ".", s)
    assert n <= 2, f"{n} grasping sentences"
    return s


SAFETY_OLD = ('Every response\'s `meta["safety"]` reports, since the\n  previous call, forcing (the arms\' pressing loads and forcing '
              'events), the deepest task contact, the longest time above\n  its sustained limit and the review events (rigid families), '
              'the lowest rope / cord volume ratio (soft families) and the\n  table-guard stops, against the limits above.')
SAFETY_NEW = ('Every response\'s `meta["safety"]` reports, since the\n  previous call, what the robot itself can feel: its forcing '
              'record (the largest force an arm or a part it holds pressed\n  with, the drive load meanwhile, the longest forcing run '
              'and the forcing events, naming only "a held part" and "the\n  environment"), the table-guard stops of its gripper '
              'targets and its IK jumps. Task contacts, review events and\n  soft-body readings are the grader\'s evidence and are not '
              'reported.')


REGIONS_RX = re.compile(r"(?m)^- (?:Grasp regions|Soft grasp patches)[ (:].*$")
GRASP_ROW_RX = re.compile(r"(?m)^\| Grasping \| [^|\n]* \|$")
DIFFICULTY_GRASP_RX = re.compile(r"(?m)^((?:Two|A) \d+-dof .* Grasping: )(?:assisted grasping \([a-z0-9_]+\)|physical grasping)\.$")


def instance_facts(s: str, rec: dict, mode: str) -> str:
    """A MuJoCo base's statements of its instance's grasp, from the instance (release.json, read in the release image by
    release_rebuild.py: grasp = the [metadata] grasp words, grasp_regions = the grader-details line per mode, grasp_rules):
    a port whose grasp model changed on MuJoCo (rope_threading: the released IPC soft band -> contact_weld_v1) must not keep
    the released line. Records without these facts keep the released lines."""
    if not is_mujoco(rec):
        return s
    if rec.get("grasp"):
        s = re.sub(r'(?m)^grasp = ".*"$', lambda m: f"grasp = {json.dumps(rec['grasp'])}", s)
    new = rec.get("grasp_regions", {}).get(mode)
    if new:                 # only a line of the other grasp form (soft patches <-> rigid regions): a released line of the
        form = new.split(" ")[0]           # same form keeps its own words (e.g. hedgehog cast_cage's rod "box handle")
        s, n = REGIONS_RX.subn(lambda m: m[0] if m[0][2:].split(" ")[0] == form else "- " + new, s)
        assert n <= 2, f"{n} grasp-region lines"
    if rec.get("grasp_rules"):
        head = rec["grasp_rules"].split(":")[0]
        s = GRASP_ROW_RX.sub(lambda m: f"| Grasping | {head} |", s)
        s = DIFFICULTY_GRASP_RX.sub(lambda m: m[1] + head + ".", s)
    return s


FEM_RX = re.compile(r"(?m)^- The (rope|cord)'s Young's modulus is ([0-9.]+) kPa\.[^\n]*$")
CHAIN_ANCHOR = "- Robot safety (this benchmark's tooling):"


def chain_words(c: dict, name: str, young_kpa: float | None) -> str:
    """The rope / cord sentence of a MuJoCo chain base, from its profile and frozen scene (release.json chain, read in the
    release image by release_rebuild.py): rigid capsule links on joints, their springs, bend stops, plasticity, speed
    clamp and tension guard as the profile has them. It replaces the released FEM sentence (Young's modulus, inverted
    volume elements), whose rule never fires on a chain (topogym/world/mujoco/profiles.py)."""
    size = f"{c['link_mm']:g} mm long, {2 * c['radius_mm']:g} mm thick" if c.get("link_mm") and c.get("radius_mm") else None
    links = f"a chain of {c['links']} rigid capsule links" if c.get("links") else "a chain of rigid capsule links"
    if c["kind"] == "rope":
        spring = (f"; each joint bends and twists against a spring set by the {name}'s material"
                  + (f" (Young's modulus {young_kpa:g} kPa)" if young_kpa else "") + ", with damping")
        stop = (f", and stops bending at {c['bend_stop_rad']:g} rad, where neighbouring links touch"
                if c.get("bend_stop_rad") else "")
    else:
        k = float(c.get("stiffness_nm_rad") or 0.)
        spring = (f" on ball joints that bend and twist against springs (about {k:.2g} N m/rad per joint), with damping" if k > 0
                  else " on ball joints that bend and twist freely (no spring), with damping")
        stop = ""
    plastic = c.get("plastic")
    plastic = (f"; past {plastic['yield_angle_deg']:g} deg a joint's rest angle follows its bend (the {name} stays bent)"
               if plastic else "")
    out = (f"- The {name} is {links}" + (f" ({size})" if size else "") + (" joined end to end" if c["kind"] == "rope" else "")
           + spring + stop + plastic + f". The links do not deform: nothing about the {name}'s shape or volume ends the "
           "episode.")
    sc = c.get("speed_clamp")
    if sc:
        who = {"slotted_chain": "A part of the chain (a link, bead, end disc or the ring)", "cord": "A cord link or the handle"
               }.get(c.get("entity"), "A link")
        out += (f" {who} moving faster than {sc['v_m_s']:g} m/s or spinning faster than {sc['w_rad_s']:g} rad/s is slowed by "
                "extra damping (a speed clamp); this is not reported and does not end the episode.")
    tg = c.get("tension_guard")
    if tg and young_kpa and c.get("radius_mm") and c.get("link_mm"):
        r, l = c["radius_mm"] / 1000, c["link_mm"] / 1000
        t = tg["t_on"] * young_kpa * 1000 * math.pi * r ** 4 / 4 / l ** 2
        out += (f" Pulled harder than about {t:.3g} N, the {name}'s links get extra rotational inertia (a tension guard), "
                "which only removes energy and is not reported.")
    return out


def chain_text(s: str, rec: dict) -> str:
    """The released FEM sentence of a chain family replaced by its chain's own (chain_words), or the sentence added
    before the robot-safety line of a text that has none (a new design drafted without it)."""
    c = rec.get("chain") if is_mujoco(rec) else None
    if not c:
        return s
    s = (s.replace("Simulator breakdown (an invalid soft-body solver state)",
                   "Simulator breakdown (a MuJoCo instability: a non-finite or diverging acceleration, position or velocity)")
          .replace("every vertex of its simulated volume", "every vertex of its links (capsules)")
          # knot_untying's release check (topogym_rules.knot_release_words): the rope's volume mesh is carried rigidly by
          # its capsule links on MuJoCo (rope_chain.RopeChain.fem_state); the check bounds that mesh, not FEM tetrahedra
          .replace("The release check bounds every rope tetrahedron against",
                   "The release check bounds the rope's volume mesh (carried rigidly by its capsule links), element by element, against")
          .replace("(refined per tetrahedron where they are close)",
                   "(refined per element of the volume mesh its capsule links carry where they are close)"))
    ent = c.get("entity") or "rope"        # the scene object list: the chain is not an FEM body on MuJoCo
    s = s.replace(f"`{ent}` (deformable, fem)", f"`{ent}` (a chain of rigid capsule links)")
    m = FEM_RX.search(s)
    if m:
        return FEM_RX.sub(lambda m: chain_words(c, m[1], float(m[2])), s, count=1)
    if "rigid capsule links" not in s and CHAIN_ANCHOR in s:
        name = "rope" if c["kind"] == "rope" else "cord"
        return s.replace(CHAIN_ANCHOR, chain_words(c, name, None) + "\n" + CHAIN_ANCHOR, 1)
    return s


def safety_text(s: str) -> str:
    """The standard instruction's meta["safety"] paragraph stays the released one (SAFETY_OLD): the service publishes
    main's declared fields again, with part names (user decision 2026-10-13; the sim service's robot_felt,
    SAFETY_PUBLISHED). A text still carrying the reduced paragraph of 2026-10-12 (SAFETY_NEW) gets the released one back."""
    return s.replace(SAFETY_NEW, SAFETY_OLD)


def is_mujoco(rec: dict) -> bool:
    """A base whose frozen instance runs on MuJoCo (release.json physics_engine)."""
    return rec.get("physics_engine") == "mujoco"


def mujoco_text(s: str, rec: dict) -> str:
    """A MuJoCo base's texts name the engine it runs on, and the wall time per control step measured on MuJoCo
    (release.json step_s: its reference's oracle run) where the released text stated Genesis'."""
    if not is_mujoco(rec):
        return s
    for a, b in MUJOCO_WORDS + determinism_words(bool(rec.get("gpu_physics"))):
        s = s.replace(a, b)
    s = README_GPU_RX.sub(lambda m: ("The physics (a deterministic GPU cloth step, the rest on the CPU) replays bit for bit on "
                                     "one host; the\nfinal-state hashes (`deterministic`) are still diagnostic" if rec.get("gpu_physics")
                                     else "The physics runs on the CPU and is bit-deterministic on one host; the\nfinal-state "
                                     "hashes (`deterministic`) are still diagnostic"), s)
    s = s.replace("RoboARC on MuJoCo 3.14.0 (CUDA physics, Nyx RGB)", "RoboARC on MuJoCo 3.14.0 ("
                  + ("CPU physics, CUDA cloth step" if rec.get("gpu_physics") else "CPU physics") + ", Nyx RGB)")
    if rec.get("step_s"):
        s = STEP_RX.sub(f"One control step takes about {rec['step_s']:g} s of wall clock", s)
    return s


# ---------------------------------------------------------------- fixes of the 2026-10-10 review (board 0067)
# Applied here, on top of the release's texts and Dockerfiles, until dev/jianwen carries them (docs/benchmarks/roboarc.md,
# "Fixes applied on main"). Every replacement asserts that its source text is still there: a new release that rewords
# it fails the render instead of silently losing the fix.
MAX_STEPS = 200000        # rcb_topogym.MAX_STEPS (RCB_MAX_STEPS): the runaway guard on an episode's / a trajectory's length
MAX_CALL_WALL_S = 900     # v2_4/rcb_limited.MAX_CALL_WALL_S (RCB_MAX_CALL_WALL_S): no compose file overrides it
CHUNK_S, WATCH_S = 10, 30  # the sim service's RCB_MAX_CHUNK_S / RCB_MAX_WATCH_S defaults
BUILD_ALLOWANCE_S = 1800  # scene build, kernel compilation and video encoding inside the verifier's timeout


# The flat condition in the user's words (2026-10-13), the grader's gate after it; where the scene has the fence (its
# `fence` object), cloth resting on it does not count. The task code says the same since 6120a57e2a (the blanket's
# goal_description / blanket_fold common.py); this brings the released texts of the ported tiers in line.
FLAT_OLD = "Keep every cloth point at most 30 mm above the tabletop and no more than 8 mm below it."
FLAT_NEW = ("The sheet must lie flat on the tabletop, fully in contact with the table surface{fence}: keep every cloth "
            "point at most 30 mm above the tabletop and no more than 8 mm below it.")   # = the task code's (goal_description)
FOLD_FLAT_OLD = ("Flat: every point of the blanket within 35 mm of its height in the target fold, and no point more than "
                 "30 mm above the target's highest point.")
FOLD_FLAT_NEW = ("Flat: the folded cloth must lie flat on the tabletop, its bottom layer fully in contact with the table "
                 "surface: every point of the blanket within 35 mm of its height in the target fold, and no point more than "
                 "30 mm above the target's highest point.")   # = blanket_fold's own words (common.py)
GOAL_DIR = "environment/goal"   # a package's goal-state images (fold: the target shape is shown, never given as coordinates)


# The world frame without the table height or the robot base's position (user 2026-10-13: "in the wild nobody tells you
# how tall the table is"; the base sits on the table top, so its z is the table height). Text only: the axes stay.
FRAME_PRIV = re.compile(r"- World frame: robot base at \([^)]*\)(?:, table top at z = [-0-9.]+)?, \+z up\. Quaternions are \*\*WXYZ\*\*\.")
FRAME_PRIV_NEW = ("- World frame: +z up. Quaternions are **WXYZ**. The ee_pose action and the proprio TCP pose are given in this "
                  "world frame.")
FRAME_STD = re.compile(r"world frame \(robot base at \([^)]*\),\s*\+z up\)")
FRAME_STD_NEW = ("world frame (origin at the robot's root link on its mounting, +z up; the frame of the proprio TCP pose and the "
                 "camera extrinsics)")   # standard mode's frame (user 2026-10-13, option B): the service's world frame has its origin
#                                          at the robot's root link; named "world" as main's other services name theirs
FRAME_STD_RX = ((re.compile(r"world frame \(\+z up; the frame of the proprio TCP pose\)"), FRAME_STD_NEW),   # 10-13 first wording
                (re.compile(r"`spec\[\"world\"\]` the frame conventions\."), "`spec[\"world\"]` the frame conventions (the world "
                 "frame: origin at the robot's root link on its mounting, +z up; no positions of the scene are given)."))
FRAME_LEAKS = ("robot base at", "table top at z")


def frame_words(s: str, where: str, mode: str = "privileged") -> str:
    """The frame lines without the table height and the base position (privileged: the sim's world frame, +z up; standard:
    the service's world frame, whose origin is the robot's root link); no text may still name either."""
    s = FRAME_STD.sub(FRAME_STD_NEW, FRAME_PRIV.sub(FRAME_PRIV_NEW, s))
    if mode == "standard":
        for rx, new in FRAME_STD_RX:
            s = rx.sub(new, s)
        # the texts written on dev (package_text) say "robot frame" / robot_T_cam for the same frame: one name in what ships
        s = s.replace("robot frame", "world frame").replace("robot_T_cam", "world_T_cam")
    left = [w for w in FRAME_LEAKS if w in s]
    assert not left, f"{where}: still names {left} (the table height is never disclosed)"
    return s


# R5 (dev 84c360ff28, user 2026-10-13): the static-contact guard, the Robot safety line's sentence from
# topogym_rules for MuJoCo instances; the released texts predate it. Standard mode reports the stops in clipped[].
R5_ANCHOR = "stalls at that torque."
R5_SENTENCE = (" An arm with any part more than 5 mm deep in a fixed object (a fixture, the table) is stopped where it is: its "
               "joint targets become its measured joints for that control step, so it stops pushing ({report}).")
R5_REPORT = {"privileged": "the safety readings report these stops as static_guard",
             "standard": "the response does not report these stops"}   # the standard service has no clipped[] entry for them (audit S21)


def r5_words(s: str, mode: str) -> str:
    """The static-contact guard's sentence after the Robot safety line's torque sentence, once (a no-op where it is)."""
    if "deep in a fixed object" in s or R5_ANCHOR not in s:
        return s
    return s.replace(R5_ANCHOR, R5_ANCHOR + R5_SENTENCE.format(report=R5_REPORT[mode]), 1)


CLOCK_OLD = "The episode starts when the service comes up and ends on"


def clock_words(s: str, mode: str) -> str:
    """Standard mode: the service's clock starts at the agent's first request (main's #163 rule; server.py touch()), so the
    body no longer says the episode starts when the service comes up; the Time limit section states the clock."""
    if mode != "standard":
        return s
    s = s.replace(CLOCK_OLD, "The episode ends on", 1)
    assert "service comes up" not in s and "since the service first started" not in s, "standard text still dates the clock from the service start"
    return s


TIERS = ("very_easy", "easier", "easy", "medium", "hard")


NAMES = json.loads((HERE / "roboarc_names.json").read_text())   # owner's mapping: old base -> new base, family, number, difficulty
DIFFICULTY = {v["new"].removeprefix(BENCH + "-"): v["difficulty"] for v in NAMES.values()}


def difficulty_words(s: str, rec: dict, base: str = "") -> str:
    """task.toml `difficulty` (TAXONOMY), in both modes: the owner's value for the base (roboarc_names.json; the names
    carry no difficulty), else the variation's tier: a text templated on another tier kept the template's value, and
    some packages had no key (audits S2 / S3)."""
    tier = DIFFICULTY.get(base) or re.sub(r"^(rd|v2)_|_chain$", "", rec.get("tier") or "")
    if tier not in TIERS:
        return s
    line = f'difficulty = "{tier}"'
    if re.search(r'(?m)^difficulty = ', s):
        return re.sub(r'(?m)^difficulty = "[^"]*"', line, s, count=1)
    s, n = re.subn(r'(?m)^(family = "[^"]*"[^\n]*\n)', lambda m: m.group(1) + line + "\n", s, count=1)
    assert n == 1, "task.toml: no family line to put difficulty after"
    return s


VOLUME_RULES = re.compile(r"(?m)^- (?:Keep the rope volume intact|Invalid rope volume ends the episode)[^\n]*\n")
STIFFNESS = (re.compile(r" \(Young's modulus [0-9.]+ kPa\)"), re.compile(r" \([^()\n]*N m/rad per joint\)"))


def audit_words(s: str, rec: dict, mode: str, readme: bool) -> str:
    """The text audits of 2026-10-13 (tmp/2026-10-13_status/AUDIT_LEAKAGE.md, AUDIT_PACKAGING.md), as rules:
    B4  a chain base has no rope volume, so the released volume rules go (the chain sentence says nothing about volume
        ends the episode);
    B5  a standard text carries no privileged grading line (two replays of a submitted trajectory);
    S19 standard texts state no physical parameter of the task objects (stiffness numbers); privileged keeps them;
    S2  a README's lower oracle row agrees with its key table."""
    if rec.get("chain"):
        s = VOLUME_RULES.sub("", s)
        s = s.replace('as "rope_volume_invalid: <what>" or "forced_breakdown: <what>"', 'as "forced_breakdown: <what>"')
    # a dated decision note inside a quoted source excerpt (blanket_flatten rd's predicate): not for the agent (2026-10-13)
    s = s.replace("        # (user 2026-10-12: that read-out-only union, ~150-190 ms per control step, is dropped; until then the last tick\n"
                  "        # always computed it, complete_metrics). The birth (physics step 0) still reports it: the frozen instances'\n",
                  "        # The birth (physics step 0) still reports it: the frozen instances'\n")
    assert "(user 20" not in s, "a dated user decision note in an agent-facing text"
    s = re.sub(r"(?m)^## Task failure conditions\n\s*\n(?=## )", "", s)   # no empty failure section (audit V6, 2026-10-17)
    if mode == "standard":
        s = re.sub(r"(?m)^- Grading: the verifier replays your trajectory twice[^\n]*\n", "", s)
        for rx in STIFFNESS:
            s = rx.sub("", s)
    if readme and rec.get("oracle") != "none" and rec.get("evidence"):
        s = s.replace('| oracle | none yet (`oracle = "none"`, no `solution/`) |', '| oracle | `full` (`solution/`) |')
    return s


# interlocked_claws, the whole-piece separation goal (easy / medium / hard, Cast ABC, Rotor; user 2026-10-13). Its predicate
# (topogym/tasks/interlocked_claws/terminal.py separation_candidate) checks a gap between the two complete pieces and that
# BOTH are still, for the confirmation time; it checks no goal square and no separator. The texts ported from the Genesis
# release kept the placement families' two grader-details lines ("Goal square in this instance ...", "The separator is
# ... free to move (its speed is not checked) ..."), which contradict the requirement above them. They go; in their place
# stands the separation line of dev's scripts/topogym_rules.py claws_separation_words() (word for word), unless the
# package's text already carries it. A placement text (very_easy / easier, the rd tiers) has no SEPARATION_MARK: no-op.
SEPARATION_MARK = "release and transport into the green region are not required."
SEPARATION_GAP = re.compile(r"Leave at least (\S+ mm) between the complete pieces")
SEPARATION_FALSE = re.compile(r"(?m)^- (?:Goal square in this instance: |The separator is an invisible, fixed vertical plane )[^\n]*\n")
SEPARATION_LINE = ("- Separation as the grader measures it: every vertex of both pieces' visual and collision meshes counts, and "
                   "the gap is measured along ten directions only: the three world axes, each piece's own three body axes, and "
                   "the line between the two pieces' centres (the mean of each piece's vertices). Along at least one of them the "
                   "two pieces must be at least {gap} apart; a separating plane in any other direction "
                   "does not count. The green dashed square on the table is not part of this goal: neither containment in it nor "
                   "a separator plane is checked.\n")


def separation_words(s: str, where: str) -> str:
    """The grader details of a claws separation text say what its predicate checks (instruction.md and README.md)."""
    if SEPARATION_MARK not in s:
        return s
    line = SEPARATION_LINE.format(gap=SEPARATION_GAP.search(s).group(1))
    false = SEPARATION_FALSE.findall(s)
    if line in s:
        assert not false, f"{where}: the separation line next to a goal-square / separator line"
    else:
        assert len(false) == 2, f"{where}: expected the goal-square and the separator line, found {len(false)}"
        s = SEPARATION_FALSE.sub("", s.replace(false[0], line, 1))
    left = [w for w in ("free to move", "speed is not checked", "Goal square", "The separator is") if w in s]
    assert not left and s.count(line) == 1, f"{where}: a separation text still says {left}"
    return s


def family_words(name: str, s: str, rec: dict) -> str:
    """A new base templated on another family's package (slotted / orbits on horseshoe_ring, blanket_fold on
    blanket_flatten): its grader and its standard sim name its own family, never the template's."""
    fam = rec["family"]
    if name == "tests/test.sh":
        s = re.sub(r"--family \S+", f"--family {fam}", s)      # privileged's grader; standard's reads its sim's result
    elif name.endswith("docker-compose.yaml"):
        s = re.sub(r"RCB_TASK: \S+", f"RCB_TASK: {fam}", s)
    return s


def flat_words(s: str, fence: bool) -> str:
    """The cloth families' flat condition led by the user's words (a no-op on texts without it)."""
    new = FLAT_NEW.format(fence=" (cloth resting on the fence does not count)" if fence else "")
    if fence:
        s = s.replace(FLAT_NEW.format(fence=""), new)
    return s.replace(FLAT_OLD, new).replace(FOLD_FLAT_OLD, FOLD_FLAT_NEW)


def goal_images(up: pathlib.Path, t: pathlib.Path, instruction: str) -> None:
    """A package's goal-state images: copied into the agent container at /app/goal/ (both modes); the instruction must
    name each one (an image nobody points to is a mistake)."""
    goal = up / GOAL_DIR
    if not goal.is_dir():
        return
    files = sorted(p for p in goal.iterdir() if p.is_file())
    assert files, f"{up}: empty {GOAL_DIR}"
    for p in files:
        assert f"/app/goal/{p.name}" in instruction, f"{up.name}: instruction.md does not name /app/goal/{p.name}"
        put(t / GOAL_DIR / p.name, p.read_bytes())
    df = t / "environment/Dockerfile"
    s, anchor = df.read_text(), "RUN mkdir -p /app/output\n"
    assert s.count(anchor) == 1, f"{t.name}: environment/Dockerfile has no single {anchor!r}"
    if "COPY goal/ /app/goal/" not in s:
        s = s.replace(anchor, "COPY goal/ /app/goal/\n" + anchor)
    df.write_text(s)


def swap(s: str, old: str, new: str, what: str, count: int = 1) -> str:
    assert s.count(old) == count, f"{what}: expected {count} x {old[:60]!r}, found {s.count(old)}"
    return s.replace(old, new)


def step_time(instruction: str) -> float:
    return float(re.search(r"One control step takes about ([0-9.]+) s of wall clock", instruction).group(1))


def base_step(base: str) -> float:
    """The wall time per control step the base's texts state: a MuJoCo base's measured one (release.json step_s, see
    mujoco_text), else the released instruction's."""
    rec = REL["bases"][base]
    if is_mujoco(rec) and rec.get("step_s"):
        return float(rec["step_s"])
    return step_time((PKG / f"{base}-privileged" / "instruction.md").read_text())


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
    cap = min(MAX_STEPS, int(budget / (3 * base_step(base))) // 1000 * 1000)
    traj = ORC / base / "privileged.npz"
    if traj.is_file():      # the reference trajectory must fit, with room
        with zipfile.ZipFile(traj) as z, z.open("actions.npy") as f:
            f.read(8); n = int.from_bytes(f.read(2), "little"); header = f.read(n).decode("latin1")
        rows = int(re.search(r"'shape': \((\d+),", header).group(1))
        assert 1.5 * rows <= cap, f"{base}: the reference trajectory has {rows} rows, the cap is {cap}"
    return cap


# The privileged grading rule (2026-10-14, failure analysis item 12): success needs both grading replays to succeed AND at
# least one of them to reach the goal with the instance's own thresholds within the agent's own rows (shared/privileged/
# grade.py, `strict_replay_required` 1): the tolerant hold only confirms, as in standard mode, where the live episode is
# strict. The packages' texts say so (R_HOLD_STRICT, VERIFY_STRICT) and are kept as they are; R-hold (2026-10-05: every
# replay could confirm within the hold) made the hold's relaxed thresholds the effective goal (blanket-flatten: 92 %
# coverage instead of 95 %), and its wording must not come back.
R_HOLD_STRICT = ("Success needs both replays to succeed AND at least one of them to reach the goal with the thresholds above "
                 "within your own rows (not only in the hold).")
VERIFY_STRICT = ("at least one replay must\nreach the goal with the instance's own thresholds within the trajectory's rows.")
R_HOLD_WORDS = ("`strict_goal_reached`, not required", "each of them may complete its confirmation within that hold",
                "every replay may confirm\nwithin that hold")


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


SERVICE_END = ("\n  This service also ends the episode itself (`meta[\"reason\"]` is `timeout`; it is graded as it stands) when its own\n"
               "  count of that limit, `meta[\"time_left_s\"]`, reaches 0. That count starts at your first request to the service, so it\n"
               "  never reaches 0 before your time is up.\n")   # PROTOCOL §2.12: a service that ends the episode on its clock says so


def review_fixes(s: str, name: str, base: str, mode: str) -> str:
    """The text fixes for one rendered file (name: instruction.md | README.md)."""
    up = PKG / f"{base}-privileged" / "instruction.md"
    step = base_step(base); hz = int(re.search(r"Control runs at (\d+) Hz", up.read_text()).group(1))
    if mode == "privileged":
        # the families with a grading hold state the strict rule (R_HOLD_STRICT; README: VERIFY_STRICT), as the grader applies it
        assert not any(w in s for w in R_HOLD_WORDS), f"{base} {name}: R-hold wording"
        if name == "instruction.md" and "final targets for up to" in s:
            s = swap(s, R_HOLD_STRICT, R_HOLD_STRICT[:-2] + "; `s.replay(actions, grading=True)` reports it as "
                     "`[\"grading\"][\"strict_success\"]`).", f"{base} the privileged grading rule")
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
        # the agent's limit is stated once, in `## Time limit` (PROTOCOL §2.12): the service's clock counts from the agent's
        # first request (server.py touch(), main's #163 rule), so its `time_left_s` never runs out before the cutoff. The
        # service still ends the episode at 0 and the body says so (SERVICE_END); the Genesis release's "has run since the
        # service first started" is gone
        s, n = re.subn(r'- \*\*Your wall-clock budget is \d+ min \(\d+ s\)\*\* \(`meta\["time_left_s"\]` counts it down\); ',
                       "- **Your only budget is the time limit (`## Time limit`)**; ", s)
        assert n == 1, f"{base}: the standard budget sentence"
        s, n = re.subn(r" One control step takes about [0-9.]+ s of wall clock here\.\n(?=- There is nothing to hand in)",
                       lambda m: SERVICE_END, s)        # the step time stays once, under "Time per call" (audit S8)
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
    return swap(s, line, line + "# the longest trajectory the verifier replays within its timeout (scripts/roboarc/mk_tasks.py row_cap)\n" + env + "\n",
                f"{base} {name}")


def toml_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def run_words(e: dict) -> str:
    """Where the evidence episode ran: the image build and the date, never a host or a job name (2026-10-13). A record of
    an earlier build of this release says so; that build holds the same frozen instance (the release notes have the hashes)."""
    if "attempt" not in e:
        return f"{e['image']} ({e['date']}; simulator source {e['source']}, tooling {e['tooling']})"
    run = pathlib.Path(e["attempt"]).name.removeprefix("attempt-")
    return f"{e['release']} (source {e['source']}, tooling {e['tooling']}; lab run {run})"


NO_REFERENCE = ("No oracle; human review in PR #N (PROTOCOL §2.7). No reference solution and no positive example yet: nothing "
                "is known to solve this task. Its physics was accepted on the family's acceptance rounds and a smoke stress "
                "round on this instance.")   # release.json oracle "none" (user 2026-10-13); main's wording for the first clause


def evidence_text(base: str, rec: dict) -> str:
    ev = rec["evidence"]
    if rec.get("oracle") == "none":
        return NO_REFERENCE
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
    """What changed between the evidence build and this release (release.json; docs/benchmarks/roboarc.md, Evidence)."""
    end = " The oracle was not re-run on this build (docs/benchmarks/roboarc.md, Evidence)."
    if rec["family"] == "blanket_flatten" and REL.get("blanket_change"):
        return REL["blanket_change"] + end
    shared = REL.get("release_change", "")
    if rec.get("note"):          # graded on an earlier build than merged-v18 / its equivalent (the documented equivalence)
        return f"Between that build and merged-v18: {rec['note']}. After merged-v18, {shared}." + end
    return f"This family's task, geometry and asset files are unchanged from that build to this release; {shared}." + end


NOT_CONFIRMED = {"speed_rule": "It is faster than the standard service's joint-speed rule",
                 "failed": "Its Harbor oracle trial did not score 1, and the cause is not established",
                 "not_run": "No Harbor oracle trial of it has been run yet",
                 "running": "Its Harbor oracle trial was still running when this release was rendered and is not confirmed"}


def ref_solution(mode: str, rec: dict) -> str:
    ev = rec["evidence"].get(mode)
    if is_mujoco(rec) and ev and ev.get("status", "passed") != "passed":     # a reference without a passing Harbor record
        why = NOT_CONFIRMED[ev["status"]]
        if mode == "privileged":
            return (f"`solution/solve.sh` copies `solution/trajectory.npz` (sha256 `{ev['trajectory_sha256'][:16]}…`) to "
                    f"`/app/output/`: the MuJoCo reference, which its author replayed to success with a reproducible end "
                    f"state outside Harbor. {why}, so no score is claimed here.")
        if ev["status"] == "speed_rule":       # 2026-10-13: the rope_threading rd references (888 to 1174 rows above the rule)
            return ("`solution/solve.sh` streams the recorded rows of the reference (`solution/oracle_qpos.npy`) through the "
                    "client, but **this is not a working oracle in standard mode**: the reference was recorded faster than the "
                    "standard service's joint-speed rule (0.04 rad per control step); replayed through the service "
                    "its rows are stretched over more control steps and the episode does not solve the task (the Harbor oracle "
                    "trial of rope-threading-rd-very-easy scored 0 for this reason). A re-timed reference follows. The "
                    "privileged twin's reference is the same rows and is graded without the speed rule.")
        over = (f" Standard oracle not finished; the reference has {ev['rows_over']} rows above the service's joint-speed rule (0.04 rad per "
                "control step) and may be stretched by the service." if ev.get("rows_over") else "")
        return ("`solution/solve.sh` streams the recorded rows of the reference (`solution/oracle_qpos.npy`, one "
                "`joint_position` row per control step, `hold`; the same rows as the privileged reference) through the "
                f"client (`solution/oracle_replay.py`). {why} on this standard service, so no score is claimed here.{over}")
    if is_mujoco(rec) and ev:
        if mode == "privileged":
            route = ("this design's oracle, recorded on MuJoCo" if rec.get("template") or rec.get("design") else
                     "the released route re-recorded on MuJoCo with a held tail")
            return (f"`solution/solve.sh` copies `solution/trajectory.npz` (sha256 `{ev['trajectory_sha256'][:16]}…`) to "
                    f"`/app/output/`: the MuJoCo reference ({route}), which the verifier scored 1 in two fresh-process "
                    f"replays on {run_words(ev)}.")
        if ev.get("speed_rule"):     # 2026-10-14: a standard reference re-timed to the joint-speed rule (oracles/<base>/standard.npz)
            return ("`solution/solve.sh` streams the rows of the standard reference (`solution/oracle_qpos.npy`, one "
                    "`joint_position` row per control step, `hold`) through the client (`solution/oracle_replay.py`): "
                    f"{ev['speed_rule']} That episode scored 1 (live and fresh replay, end state `{ev['end_state']}`) on "
                    f"{run_words(ev)}.")
        return ("`solution/solve.sh` streams the recorded rows of the standard-mode oracle episode "
                "(`solution/oracle_qpos.npy`, one `joint_position` row per 25 ms control step, `hold`; the same rows as the "
                "privileged reference) through the client (`solution/oracle_replay.py`). That episode scored 1 (live and "
                f"fresh replay) on {run_words(ev)}.")
    if rec.get("oracle") == "none":
        return NO_REFERENCE + " `oracle = \"none\"`: there is no `solution/`, and Harbor checks the nop agent only."
    if not ev:
        return ("None in this release: the author is fixing this tier's oracle (it follows in a later pull request). "
                "`oracle = \"none\"`, human review (PROTOCOL §2.7).")
    same = since_evidence(rec)
    if mode == "privileged":
        return (f"`solution/solve.sh` copies `solution/trajectory.npz` (sha256 `{ev['trajectory_sha256'][:16]}…`) to "
                f"`/app/output/`: the trajectory the author's oracle (the RoboARC planner on dev/jianwen) produced on "
                f"{run_words(ev)}, where the verifier scored it 1 in two fresh-process replays. " + same)
    return ("`solution/solve.sh` streams the recorded rows of the author's standard-mode oracle episode "
            "(`solution/oracle_qpos.npy`, one `joint_position` row per 25 ms control step, `hold`) through the client "
            f"(`solution/oracle_replay.py`). That episode scored 1 (live and fresh replay) on {run_words(ev)}. " + same)


def nop_words(base: str, mode: str, rec: dict) -> str:
    n = rec.get("nop")
    if n and n.get("status", "passed") != "passed":
        return f"`nop`: no record yet on this base (`harbor run -p tasks/{BENCH}-{base}-{mode} -a nop`)."
    if n:
        return f"`nop` scored 0 on this base in both modes ({n['run']}; {n['date']})."
    return f"`nop`: pending (`harbor run -p tasks/{BENCH}-{base}-{mode} -a nop`, docs/benchmarks/{BENCH}.md)."


def provenance(base: str, rec: dict) -> str:
    if is_mujoco(rec):
        return mujoco_provenance(base, rec)
    rows = [f"- Frozen instance: built by TopoGym source `{rec['creation_source']}` (graded package "
            f"`{rec['instance_package']}/topogym-{base}-privileged` on the lab host); bound to this release's runtime "
            f"(source `{REL['runtime']['source']['sha256'][:8]}`, tooling `{REL['tooling_sha256'][:8]}`). An exact-restore "
            "preflight on this build is pending (docs/benchmarks/roboarc.md, Pending)."]
    rows.append(f"- Frozen instance files (`instance.json`, `instance_assets/`): not in this directory. They are in the private HF "
                f"dataset `{ASSETS['repo']}` at `{ASSETS['revision'][:12]}`, under `instances/{base}/` "
                "(scripts/roboarc/assets.json pins each file's sha256). The image carries them, and "
                "`/opt/robotangle/stage_instance.py` copies this task's instance next to its `runtime_binding.json`, "
                "which names the instance's canonical sha256 and every asset's sha256. The tooling checks them again at "
                "every session start.")
    rows.append(f"- Release: dev/jianwen `{REL['release_commit'][:9]}` (task templates `{REL['template_commit'][:9]}`), "
                f"image `{IMAGE}` (images/roboarc/).")
    rows.append("- Name: RoboARC is the published name of this benchmark (2026-10-13). Code identifiers keep the simulator's name: the "
                "simulator package `topogym`, the tooling `rcb_topogym.py`, `TOPOGYM_*` variables.")
    return "\n".join(rows)


def mujoco_provenance(base: str, rec: dict) -> str:
    rows = [f"- Frozen instance: a MuJoCo instance (`simulator.physics_engine` \"mujoco\", its scene frozen under "
            f"`instance_assets/mujoco/`), built by TopoGym source `{rec['creation_source']}` ({rec['instance_package']}); "
            f"bound to this release's runtime (source `{REL['runtime']['source']['sha256'][:8]}`, tooling "
            f"`{REL['tooling_sha256'][:8]}`).",
            f"- Frozen instance files (`instance.json`, `instance_assets/`): not in this directory. They are in the private HF "
            f"dataset `{ASSETS['repo']}` at `{ASSETS['revision'][:12]}`, under `instances/{base}/` "
            "(scripts/roboarc/assets.json pins each file's sha256). The image carries them, and "
            "`/opt/robotangle/stage_instance.py` copies this task's instance next to its `runtime_binding.json`, "
            "which names the instance's canonical sha256 and every asset's sha256. The tooling checks them again at "
            "every session start.",
            f"- Release: dev/robotangle_mujoco `{rec['release_commit'][:9]}`, image `{IMAGE}` (images/{BENCH}/).",
            "- Name: RoboARC is the published name of this benchmark (2026-10-13). Code identifiers keep the simulator's name: the "
            "simulator package `topogym`, the tooling `rcb_topogym.py`, `TOPOGYM_*` variables."]
    return "\n".join(rows)


def rewrite_toml(s: str, base: str, rec: dict) -> str:
    s = TC.set_agent_timeout(mujoco_text(text(instance_facts(s, rec, "privileged")), rec), CUTOFF_SEC, base)
    s = re.sub(r'(?m)^simulator = "topogym"', f'simulator = "{BENCH}"', s)
    s = re.sub(r'(?m)^robot = "([a-z_]+)"', lambda m: f'robot = "{ROBOT.get(m.group(1), m.group(1))}"', s)
    s = re.sub(r'(?m)^author_name = "jianwen"', 'author_name = "Jianwen Lyu"', s)
    s = s.replace('authors = [{ name = "jianwen" }]', 'authors = [{ name = "Jianwen Lyu" }]')
    s = s.replace('"topogym",', f'"{BENCH}",')
    s = re.sub(r'(?m)^tooling_version = "\d+"', f'tooling_version = "{REL["tooling_version"]}"', s)
    s = swap(s, EGRESS_OLD, EGRESS_NEW, f"{base} agent egress")
    s = re.sub(r'(?m)^oracle_evidence = .*\n', "", s)
    if {"privileged", "standard"} <= set(rec["evidence"]):   # a passing oracle run in both modes (docs/benchmarks/roboarc.md)
        s = re.sub(r'(?m)^oracle = .*\n', 'oracle = "full"\n', s, count=1)
    else:
        s = re.sub(r'(?m)^oracle = .*\n', f'oracle = "none"\noracle_evidence = {toml_str(evidence_text(base, rec))}\n', s, count=1)
    return s


PORT_TASK = ("- {date}: new task of {bench} (RoboARC on MuJoCo 3.14.0, docs/benchmarks/{bench}.md): the scene, goal "
             "and rules of the Genesis 1.2.1 task `{old}` ({mode} mode), ported to MuJoCo: its own frozen "
             "instance and reference, the numpy / OpenBLAS SIMD masking in every container that runs a Session, and the "
             "render bridge next to the tooling (Nyx frames).")
DESIGN_TASK = ("- {date}: new task of {bench} (RoboARC on MuJoCo 3.14.0, docs/benchmarks/{bench}.md): a new design of "
               "the Genesis 1.2.1 task `{old}` ({mode} mode): {design}. Its own frozen instance, task text, rules, "
               "goal and reference, the numpy / OpenBLAS SIMD masking in every container that runs a Session, and the "
               "render bridge next to the tooling.")
NEW_TASK = ("- {date}: new task of {bench} (RoboARC on MuJoCo 3.14.0, docs/benchmarks/{bench}.md): a new "
            "design of {family}{design}. Its task files start from the Genesis 1.2.1 task `{template}` ({mode} mode), with this design's "
            "own task text, rules and goal, its own frozen instance and its own reference.")


def mujoco_changes(mode: str, rec: dict) -> list[str]:
    """The Change Log of a task of this benchmark: the entry that made it (later fixes add theirs, PROTOCOL §2.8)."""
    date = rec.get("released") or rec["nop"]["date"]   # a base released before keeps its date (V2)
    if rec.get("template"):
        return [NEW_TASK.format(date=date, bench=BENCH, variation=rec["variation"], family=rec["family"],
                                template=rec["template"], design=f": {rec['design']}" if rec.get("design") else "", mode=mode)]
    if rec.get("design"):
        return [DESIGN_TASK.format(date=date, bench=BENCH, design=rec["design"], old=rec["ported_from"], mode=mode)]
    return [PORT_TASK.format(date=date, bench=BENCH, old=rec["ported_from"], mode=mode)]


FIX_STRICT_GOAL = ("- 2026-10-14: the grading rule (tests/grade.py; failure analysis 2026-10-14, item 12). Success needs both replays to "
                   "succeed AND at least one of them to reach the goal with the instance's own thresholds within the trajectory's rows "
                   "(`strict_replay_required` 1; `success_in_hold_only` 1 marks a trajectory whose replays succeeded only in the hold, "
                   "not credited). From 2026-10-05 (R-hold) to this change a replay could also confirm within the hold, with its "
                   "relaxed thresholds, and no strict goal was required: privileged mode has no graded live run, so the hold's "
                   "thresholds were the effective goal. The frozen instance, the reference and the replay are unchanged; results "
                   "graded before this change are re-graded from their recorded trajectories, nothing is re-run "
                   "(scripts/roboarc/regrade.py). Runs: docs/benchmarks/roboarc.md (Grading replays).")
FIX_STRICT_GOAL_NO_HOLD = ("- 2026-10-14: tests/grade.py, the same file in every privileged task, requires again that one grading replay "
                           "reach the goal with the instance's own thresholds within the trajectory's rows (failure analysis "
                           "2026-10-14, item 12; docs/benchmarks/roboarc.md, Grading replays). This family has no grading hold: a "
                           "replay succeeds only within the rows, so every verdict is unchanged. reward.json gains "
                           "`success_in_hold_only` (always 0 here), and `strict_replay_required` is 1.")


def fix_changes(base: str, mode: str) -> list[str]:
    """The Change Log entries of fixes after the release (PROTOCOL §2.8: same name and frozen instance, new digest). The
    standard twins are unchanged; every privileged task's tests/grade.py changed (the families with a grading hold, whose
    packages state the strict rule (R_HOLD_STRICT), change their verdicts)."""
    if mode == "standard":
        return []
    hold = R_HOLD_STRICT in (PKG / f"{base}-privileged" / "instruction.md").read_text()
    return [FIX_STRICT_GOAL if hold else FIX_STRICT_GOAL_NO_HOLD]


def rewrite_readme(s: str, base: str, mode: str, rec: dict) -> str:
    s = grasp_text(contact_text(chain_text(mujoco_text(text(instance_facts(s, rec, mode)), rec), rec), rec), rec).replace("from `tests/instance.json`", "from the frozen instance (`/tests/instance.json`, staged from the image and "
                        "checked against `tests/runtime_binding.json`)")
    s = re.sub(r"(?ms)^## Reference solution\n.*?(?=^## )", "## Reference solution\n" + ref_solution(mode, rec) + "\n\n", s)
    nop = nop_words(base, mode, rec)
    s = review_fixes(s, "README.md", base, mode)
    cap = (f"\nA trajectory may have at most {row_cap(base)} rows (`RCB_MAX_STEPS`: two replays must fit the verifier's "
           "timeout; a longer one is\n`bad_trajectory`)." if mode == "privileged" else "")
    s = re.sub(r"(?ms)^(## Verification\n.*?)(?=^## )", lambda m: m.group(1).rstrip() + cap + "\n\n" + nop + "\n\n", s)
    log = mujoco_changes(mode, rec)      # a new benchmark: the RoboARC task's own history stays with that task
    log += fix_changes(base, mode)
    log += [f"- {c['date']}: {c['text']}" for c in rec.get("changes", ()) if c["mode"] in (mode, "both")]   # later releases (V2)
    return s.rstrip() + "\n\n### Provenance\n" + provenance(base, rec) + "\n\n### Change Log\n" + "\n".join(log) + "\n"


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


def binding(base: str, inst_dir: pathlib.Path | None = None, bridge: bool = False, direct: bool = False) -> bytes:
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
    return companions(lock, bridge, direct)


def companions(lock: dict, bridge: bool, direct: bool) -> bytes:
    """A MuJoCo task's binding names the render bridge next to the tooling (render_bridge_sha256) and, for a family that
    renders with nyx_direct.py, that file (nyx_direct_sha256): the tooling checks both at Session start."""
    if bridge:
        lock["render_bridge_sha256"] = sha((SHARED / "render_bridge.py").read_bytes())
    if direct:
        lock["nyx_direct_sha256"] = sha((SHARED / "nyx_direct.py").read_bytes())
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
           "# Vulkan ICD and EGL vendor files name (images/roboarc/Dockerfile). No `runtime: nvidia`: with the image's\n"
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


STAGE = "RUN python /opt/robotangle/stage_instance.py {base} {dest} --purge   # the frozen instance, from the image (scripts/roboarc/assets.json), checked against runtime_binding.json"
ENTRY = ('    # The frozen instance comes from the image (scripts/roboarc/assets.json): the entrypoint stages it next to a copy of\n'
         '    # runtime_binding.json and checks it (images/roboarc/stage_instance.py), then runs the command.\n'
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


MUJOCO_ENV = (("NPY_DISABLE_CPU_FEATURES", "AVX512F,AVX512CD,AVX512_SKX,AVX512_CLX,AVX512_CNL,AVX512_ICL,AVX512_SPR"),
              ("OPENBLAS_CORETYPE", "Haswell"))   # the containers of a MuJoCo task (dev/robotangle_mujoco docs/rcb/MUJOCO_CORE.md)


def direct_families() -> tuple[str, ...]:
    """The families whose MuJoCo tasks render with nyx_direct.py: the tooling's own settings (rcb_topogym.TASKS renderer
    "direct"), read from the copy this release ships. The tooling sets it in loops (`for _name in (...)`) and in single
    assignments (`TASKS["cast_coil"]["renderer"] = "direct"`); both forms are read, and the count of assignments in the
    file must equal the count understood here: a family missed ships without nyx_direct.py and its service dies at the
    first frame (2026-10-13: slotted_post_ring, orbits, then cast_coil and cast_keyhole)."""
    src = (SHARED / "rcb_topogym.py").read_text()
    loops = re.findall(r'(?ms)^for _name in \(([^)]*)\):\n\s+TASKS\[_name\]\["renderer"\] = "direct"', src)
    singles = re.findall(r'(?m)^TASKS\["([a-z0-9_]+)"\]\["renderer"\] = "direct"', src)
    total = len(re.findall(r'\["renderer"\] = "direct"', src))
    assert total == len(loops) + len(singles), f"rcb_topogym.py sets renderer \"direct\" {total} times, {len(loops) + len(singles)} understood"
    return tuple(n for loop in loops for n in re.findall(r'"([a-z0-9_]+)"', loop)) + tuple(singles)


def nyx_direct(rec: dict) -> bool:
    return rec["family"] in direct_families()


CPU_PHYSICS = (("# The verifier replays in the simulator, which needs the GPU (CUDA physics, Nyx camera images for the replay video).",
                "# The verifier replays in the simulator: MuJoCo physics on the CPU; the GPU renders the Nyx camera images of the replay video."),
               ("# TopoGym runs its physics on the GPU (CUDA) and renders camera images with Nyx.",
                "# RoboARC runs its physics on MuJoCo (CPU) and renders camera images with Nyx on the GPU."))
GPU_PHYSICS = (("# The verifier replays in the simulator, which needs the GPU (CUDA physics, Nyx camera images for the replay video).",
                "# The verifier replays in the simulator, which needs the GPU (the cloth's CUDA step, Nyx camera images for the replay video)."),
               ("# TopoGym runs its physics on the GPU (CUDA) and renders camera images with Nyx.",
                "# RoboARC runs its physics on MuJoCo with the cloth's CUDA step on the GPU, and renders camera images with Nyx."))


def mujoco_lines(name: str, s: str, rec: dict) -> str:
    """A MuJoCo task: the SIMD masking in the images that run a Session (privileged agent and verifier: the RoboARC
    image) and in the standard sim service; render_bridge.py (and nyx_direct.py for its families) copied next to the
    privileged tooling; the compose comments say where the physics runs (the GPU reservation itself is unchanged: Nyx,
    and a GPU physics profile, need it)."""
    def sub(a: str, b: str) -> str:
        assert s.count(a) == 1, f"{name}: expected one {a!r}"
        return s.replace(a, b)
    direct = nyx_direct(rec)
    env = ("# MuJoCo task: numpy / OpenBLAS SIMD masking, so every CPU class generates the frozen bytes\n"
           "ENV " + " ".join(f"{k}={v}" for k, v in MUJOCO_ENV) + "\n")
    if name in ("environment/Dockerfile", "tests/Dockerfile") and f"FROM {IMAGE}\n" in s:
        s = sub(f"FROM {IMAGE}\n", f"FROM {IMAGE}\n" + env)
        if name == "environment/Dockerfile":
            s = sub("COPY rcb_topogym.py /opt/tools/rcb_topogym.py\n",
                    "COPY rcb_topogym.py /opt/tools/rcb_topogym.py\nCOPY render_bridge.py /opt/tools/render_bridge.py\n"
                    + ("COPY nyx_direct.py /opt/tools/nyx_direct.py\n" if direct else ""))
        else:
            s = sub("COPY grade.py rcb_topogym.py test.sh /tests/", "COPY grade.py rcb_topogym.py render_bridge.py "
                    + ("nyx_direct.py " if direct else "") + "test.sh /tests/")
    if name == "environment/docker-compose.yaml" and "\n  sim:\n" in s:
        s = sub("      RCB_TASK: ", "".join(f"      {k}: {v}\n" for k, v in MUJOCO_ENV) + "      RCB_TASK: ")
    if name.endswith("docker-compose.yaml"):
        for a, b in (GPU_PHYSICS if rec.get("gpu_physics") else CPU_PHYSICS):
            s = s.replace(a, b)
        s = s.replace("# TopoGym runs its physics on the GPU (CUDA) and renders camera images with Nyx: the GPU goes to the sidecar.",
                      "# RoboARC renders camera images with Nyx" + (" and steps its cloth on CUDA" if rec.get("gpu_physics")
                                                                        else "") + ": the GPU goes to the sidecar.")
        assert "CUDA physics" not in s and "TopoGym runs its physics" not in s, f"{name}: a Genesis-era GPU comment is left"
    return s


def dev_binding(inst_dir: pathlib.Path, dev: dict, bridge: bool = False, direct: bool = False) -> bytes:
    """--dev: the binding of a local frozen instance (canonical sha256, every asset's sha256) to the dev image's runtime
    and identity, with the same keys as binding()."""
    inst = json.loads((inst_dir / "instance.json").read_text())
    canon = json.dumps(inst, sort_keys=True, separators=(",", ":"), allow_nan=False)
    assets = {p.relative_to(inst_dir).as_posix(): sha(p.read_bytes()) for p in sorted((inst_dir / "instance_assets").rglob("*"))
              if p.is_file() and "__pycache__" not in p.parts}
    lock = dict(schema_version=1, instance_sha256=sha(canon.encode()), asset_files=assets,
                tooling_sha256=sha((SHARED / "rcb_topogym.py").read_bytes()), creation_source=inst["topogym_source"],
                runtime=dev["runtime"], image=dev["image"], uipc_builds=dev["uipc_builds"])
    return companions(lock, bridge, direct)


def render(base: str, out: pathlib.Path, inst_src: pathlib.Path | None = None, dev: dict | None = None) -> list[pathlib.Path]:
    rec = REL["bases"][base]
    dirs = []
    mujoco = is_mujoco(rec)
    assert mujoco, f"{base}: every base of {BENCH} is a MuJoCo base (release.json physics_engine)"
    direct = mujoco and nyx_direct(rec)
    assert not mujoco or (SHARED / "render_bridge.py").is_file() and (not direct or (SHARED / "nyx_direct.py").is_file()), \
        f"{base}: a MuJoCo base needs shared/render_bridge.py (and nyx_direct.py) from the MuJoCo release's tooling"
    reference = pathlib.Path(dev["bases"][base]["reference"]) if dev else None
    for mode in ("privileged", "standard"):
        t = out / f"{BENCH}-{base}-{mode}"; up = PKG / f"{base}-{mode}"; dirs.append(t)
        rd = lambda n: (up / n).read_text()  # noqa: E731
        put(t / "task.toml", difficulty_words(rewrite_toml(rd("task.toml"), base, rec), rec, base).encode())
        fence = "`fence`" in rd("instruction.md")
        put(t / "README.md", audit_words(r5_words(frame_words(flat_words(rewrite_readme(separation_words(rd("README.md"), f"{t.name}/README.md"), base, mode, rec), fence), f"{t.name}/README.md", mode), mode), rec, mode, True).encode())
        ins = grasp_text(contact_text(chain_text(mujoco_text(text(instance_facts(separation_words(rd("instruction.md"), f"{t.name}/instruction.md"), rec, mode)), rec), rec), rec), rec).replace("RoboARC", "RoboARC (simulator package `topogym`)", 1)
        ins = flat_words(review_fixes_r2(review_fixes(ins, "instruction.md", base, mode), base, mode), fence)
        ins = clock_words(r5_words(frame_words(safety_text(ins) if mode == "standard" else ins, f"{t.name}/instruction.md", mode), mode), mode)
        put(t / "instruction.md", audit_words(ins, rec, mode, False).encode())
        for n in ("environment/Dockerfile", "environment/docker-compose.yaml", "tests/Dockerfile", "tests/docker-compose.yaml"):
            if (up / n).is_file():
                assert "RCB_MAX_CALL_WALL_S" not in rd(n) and "RCB_MAX_STEPS" not in rd(n), f"{base} {n}: the texts assume the defaults"
                text_n = limits_env(n, staged(n, gpu_lines(n, image_lines(rd(n))), base), base, mode)
                text_n = text_n.replace("docs/benchmarks/robotangle.md", f"docs/benchmarks/{BENCH}.md")   # the benchmark's page
                put(t / n, family_words(n, mujoco_lines(n, text_n, rec) if mujoco else text_n, rec).encode())
        goal_images(up, t, (t / "instruction.md").read_text())
        put(t / "tests/test.sh", family_words("tests/test.sh", (up / "tests/test.sh").read_text(), rec).encode(), exe=True)
        lock = binding(base, inst_src, mujoco, direct) if dev is None else dev_binding(inst_src, dev, mujoco, direct)
        tool = (SHARED / "rcb_topogym.py").read_bytes()
        extra = ([("render_bridge.py", (SHARED / "render_bridge.py").read_bytes())] if mujoco else []) + \
                ([("nyx_direct.py", (SHARED / "nyx_direct.py").read_bytes())] if direct else [])
        if mode == "privileged":
            for d in ("environment", "tests"):
                put(t / d / "runtime_binding.json", lock)
                put(t / d / "rcb_topogym.py", tool)
                for n, b in extra:
                    put(t / d / n, b)
            put(t / "tests/grade.py", (SHARED / "privileged/grade.py").read_bytes())
            traj = reference or ORC / base / "privileged.npz"
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
            for n, b in extra:
                put(t / "environment/sim" / n, b)
            put(t / "tests/grade.py", (SHARED / "standard/grade.py").read_bytes())
            put(t / "tests/runtime_binding.json", lock)
            traj = reference or ORC / base / "standard.npz"
            if traj.is_file():
                with zipfile.ZipFile(traj) as z:
                    put(t / "solution/oracle_qpos.npy", z.read("actions.npy"))
                put(t / "solution/oracle_meta.json", (json.dumps({"K": 1, "interpolate": "hold", "rows": "the recorded "
                    "joint_position rows of the evidence episode (README.md, Reference solution)"}, indent=1) + "\n").encode())
                put(t / "solution/oracle_replay.py", (SHARED / "standard/solution/oracle_replay.py").read_bytes())
                put(t / "solution/solve.sh", (SHARED / "standard/solution/solve.sh").read_bytes(), exe=True)
    for t in dirs:
        TC.normalize(t)          # leaves the layer alone: scripts/eai_standard/ is a shared source (task_conventions)
        if main_cpus(t):
            TC.normalize(t)      # the texts rendered from [environment] (the resource paragraph) follow the applied cap
    return dirs


def main_cpus(task: pathlib.Path) -> bool:
    """`[environment].cpus` = `[metadata.resources.caps].main.cpus` (scripts/task_resources.toml: the task classes' own
    values, rigid / rope-chain / cloth). normalize sets `memory_mb` from the same cap; Harbor applies both to the agent's
    container, and check-resources wants the declared cap to be the applied one."""
    p = task / "task.toml"; s = p.read_text()
    main = ((tomllib.loads(s).get("metadata", {}).get("resources") or {}).get("caps") or {}).get("main") or {}
    if not main.get("cpus"):
        return False
    want = f"{float(main['cpus']):g}"
    new = re.sub(r"(?ms)(^\[environment\]\n.*?^cpus\s*=\s*)[0-9.]+", lambda m: m.group(1) + want, s, count=1)
    if new != s:
        p.write_text(new)
    return new != s


def snapshot(d: pathlib.Path) -> dict:
    return {p.relative_to(d).as_posix(): (p.read_bytes(), 0o755 if os.stat(p).st_mode & 0o100 else 0o644)   # exec bit only
            for p in sorted(d.rglob("*")) if p.is_file()}


def dev_main(a) -> int:
    """--dev: render the named bases from dev.json into --out (local only; never tasks/, nothing checked against
    release.json's instance pins)."""
    global IMAGE
    if a.out is None or not a.bases or a.check or a.assets:
        raise SystemExit("--dev needs --out and the bases, and takes neither --check nor --assets")
    dev = json.loads(a.dev.read_text())
    resolve = lambda v: (a.dev.parent / v).resolve()  # noqa: E731  (dev.json paths: absolute, or relative to dev.json)
    dev["bases"] = {b: {k: str(resolve(v)) for k, v in r.items()} for b, r in dev["bases"].items()}
    IMAGE = dev["image"]["reference"]
    a.out.mkdir(parents=True, exist_ok=True)
    for b in a.bases:
        for m in ("privileged", "standard"):
            shutil.rmtree(a.out / f"{BENCH}-{b}-{m}", ignore_errors=True)
        for t in render(b, a.out, pathlib.Path(dev["bases"][b]["instance"]), dev):
            print(f"dev task {t}")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true"); ap.add_argument("--list", action="store_true")
    ap.add_argument("--assets", type=pathlib.Path, help="a local copy of the pinned HF dataset (assets.py fetch)")
    ap.add_argument("--dev", type=pathlib.Path, help="dev.json: local dev task dirs (see usage)")
    ap.add_argument("--out", type=pathlib.Path, help="with --dev: where the dev task dirs go")
    ap.add_argument("bases", nargs="*")
    a = ap.parse_args(argv)
    if a.dev is not None:
        return dev_main(a)
    bases = a.bases or sorted(REL["bases"])
    if a.list:
        for b in bases:
            r = REL["bases"][b]
            print(f"{b:34s} instance {r['creation_source']}  " + "  ".join(f"{m}: {e['release']}:{e['source']}" for m, e in r["evidence"].items()) or "oracle pending")
        return 0
    bad = tooling_check()
    if bad and not a.check:
        print("\n".join(bad), file=sys.stderr); return 1
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
                        bad.append(f"tasks/{t.name}: differs from a fresh render (run scripts/roboarc/mk_tasks.py)")
                else:
                    if cur.exists():
                        shutil.rmtree(cur)
                    shutil.copytree(t, cur, symlinks=False)
        known = {f"{BENCH}-{b}-{m}" for b in REL["bases"] for m in ("privileged", "standard")}
        stray = sorted(p.name for p in TASKS.glob(f"{BENCH}-*") if p.name not in known)
        bad += [f"tasks/{n}: not in scripts/roboarc/release.json" for n in stray]
        tools = {sha(p.read_bytes()) for p in TASKS.glob(f"{BENCH}-*/**/rcb_topogym.py")}
        if tools - {sha((SHARED / "rcb_topogym.py").read_bytes())}:
            bad.append("a task's rcb_topogym.py differs from scripts/roboarc/shared/rcb_topogym.py")
    for b in bad:
        print("FAIL", b)
    if not bad:
        print(f"ok {BENCH}: {2 * len(bases)} task dirs {'match a fresh render' if a.check else 'rendered'} "
              f"(release {REL['release_commit'][:9]}, image {IMAGE})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
