"""The two-mode declaration of a sport (sport.toml [modes.high] / [modes.low]) and its cross-checks, without importing
the sport (standard library only): tools/check stage 1 and ci_checks/check-skilleval.py run it on every sport.

    [modes]
    action_levels = ["high", "low"]
    plays = ["program"]
    b9_test = "test_b9_..."                 # robot and mode rule 2: the feasibility test (tests/test_*.py)

    [modes.high]                            # Agent as Athlete: the platform provides the sport's skill API
    skills = ["aim"]                        # the skill API = the high level's act types
    contract = "skill.py"                   # module exporting CONTRACTS = {"aim": SkillContract(...)}
    implementation = "plugin.py:AimLayer"   # our implementation (the low level's API-test reference row)

    [modes.low]                             # Agent as Robotics Engineer: the agent implements the same skill API
    implements = ["aim"]                    # skills of [modes.high] the deliverable implements
    machine = "..."                         # only without a library robot ([body] / [arm]): the declared machine
    toolkit = "seat/toolkit.toml"           # the manifest (skilleval/toolkit.py), shipped to the seat at toolkit_path
    toolkit_path = "/opt/ro/toolkit.toml"
    tools = ["flight_model", "launcher"]    # = the manifest's [[tools]] names
    forbidden = ["aim"]                     # skills never given at this level (in the manifest's [forbidden] skills)
    evaluator = "skill.py"                  # the sport's evaluator hooks (skilleval/evaluate.py)
    reference = "lowlevel/reference"        # our skill from the toolkit only (rule 4); holds the deliverable's file
    boundary = "lowlevel/boundary"          # the boundary baseline (rule 5) = the manifest's [boundary] baseline
    thresholds = { reference_min = 0.9, boundary_max = 0.05 }   # API-test success rates
    [modes.low.deliverable]                 # rule 10
    path = "/app/output/skill/aim.py"
    signature = "aim(x, y, *, state, spec) -> {...}"
    optional = []                           # optional functions, e.g. ["step(*, state, spec) -> command or None"]
    allowed = "..."                         # what the skill may use
    time_limits_s = { load = 30, aim = 2 }
    [modes.low.cases]
    hidden = "lowlevel/cases/hidden.jsonl"  # simulator side only (never in the seat, not in generated tasks)
    public = "lowlevel/cases/public.jsonl"  # the practice subset (skilleval/cases.py practice_view)
    practice_path = "/opt/ro/practice.jsonl"   # where the seat has it ([seat.low] files)
    [modes.low.inloop]                      # optional: the skill in the loop (skilleval/inloop.py, tools/generate.py)
    skills = ["aim"]                        # lowered by the player's own file during the match (default: implements)
    step_every = 2                          # control steps between step() calls (if the deliverable has step)
    free = ["toss"]                         # low-level command types accepted at any time (others: raw_allowed)
    noop = { type = "noop" }                # the command a failed call lowers to (the sport's apply ignores it)
    cpus = 1                                # the seat's skill container
    memory = "2g"
    reference_class = "builtin_players:SkillReference"   # the in-loop tasks' oracle (sends skill calls)
    raw_rule = "while a ball is in play"    # the prompt's words for when raw_allowed refuses the other commands
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cases as cases_mod  # noqa: E402
import toolkit as toolkit_mod  # noqa: E402

SKILL_DIR = "/app/output/skill/"


def declared(d: dict) -> bool:
    m = d.get("modes") or {}
    return isinstance(m.get("high"), dict) or isinstance(m.get("low"), dict)


def _defs(path: Path) -> tuple[set, dict]:
    """(top-level function / class / variable names, literal dict keys of CONTRACTS) of a Python file."""
    tree = ast.parse(path.read_text())
    names, keys = set(), {}
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
            names.add(n.name)
        elif isinstance(n, (ast.Assign, ast.AnnAssign)):
            for t in n.targets if isinstance(n, ast.Assign) else [n.target]:
                if isinstance(t, ast.Name):
                    names.add(t.id)
                    if t.id == "CONTRACTS" and isinstance(n.value, ast.Dict):
                        keys = {k.value for k in n.value.keys if isinstance(k, ast.Constant)}
    return names, keys


def check(sport: str, d: dict, sport_dir: Path) -> list[tuple[str, bool, str]]:
    """Rows (name, ok, detail) for tools/check stage 1 and CI. A sport without [modes.high] / [modes.low] gets one
    passing row (the two modes are declared when a sport is migrated to them)."""
    sport_dir = Path(sport_dir)
    md = d.get("modes") or {}
    hi, lo = md.get("high"), md.get("low")
    if not declared(d):
        return [
            (
                "[modes.high] / [modes.low] two-mode declaration",
                True,
                "not declared (action levels only; docs/framework_zh.md §6.3)",
            )
        ]
    rows = []

    def row(name, ok, detail=""):
        rows.append((name, bool(ok), str(detail)))

    levels = md.get("action_levels") or []
    b9 = md.get("b9_test")
    tests = (
        "\n".join(p.read_text() for p in sorted((sport_dir / "tests").glob("test_*.py")))
        if (sport_dir / "tests").is_dir()
        else ""
    )
    row(
        "[modes] b9_test names a test (robot and mode rule 2)",
        bool(b9) and re.search(rf"^def {re.escape(str(b9))}\(", tests, re.M),
        b9,
    )
    skills = []
    if hi is not None:
        skills = list(hi.get("skills") or [])
        row("[modes.high] needs action level high", "high" in levels, levels)
        row("[modes.high] skills", bool(skills) and all(re.match(r"^[a-z][a-z0-9_]*$", s) for s in skills), skills)
        cf = sport_dir / str(hi.get("contract", ""))
        ok, det = cf.is_file() and cf.suffix == ".py", hi.get("contract")
        if ok:
            names, keys = _defs(cf)
            ok = "CONTRACTS" in names and set(skills) <= keys
            det = f"{hi['contract']}: CONTRACTS keys {sorted(keys)}"
        row("[modes.high] contract module exports CONTRACTS for every skill", ok, det)
        impl = str(hi.get("implementation", ""))
        f, _, obj = impl.partition(":")
        ok = (sport_dir / f).is_file() and bool(obj) and obj in _defs(sport_dir / f)[0]
        row("[modes.high] implementation (file.py:Name) exists", ok, impl)
    if lo is None:
        return rows
    row("[modes.low] needs action level low", "low" in levels, levels)
    impls = list(lo.get("implements") or [])
    row(
        "[modes.low] implements skills of [modes.high]",
        bool(impls) and (hi is None or set(impls) <= set(skills)),
        impls,
    )
    robot = (d.get("body") or {}).get("name") or (d.get("arm") or {}).get("body")
    row(
        "[modes.low] a library robot ([body] / [arm]) or a declared machine",
        bool(robot) != bool(lo.get("machine")),
        robot or lo.get("machine"),
    )
    # ---------------------------------------------------------------- toolkit
    man = sport_dir / str(lo.get("toolkit", ""))
    if not man.is_file():
        row("[modes.low] toolkit manifest exists", False, lo.get("toolkit"))
        return rows
    bad = toolkit_mod.problems(man, sport, "low")
    row("toolkit manifest: schema and sha256 (skilleval/toolkit.py)", not bad, "; ".join(bad) or lo["toolkit"])
    m = toolkit_mod.load(man)
    tool_names = [t.get("name") for t in m.get("tools", [])]
    row(
        "[modes.low] tools = the manifest's [[tools]]",
        sorted(lo.get("tools") or []) == sorted(tool_names),
        f"{lo.get('tools')} vs {tool_names}",
    )
    fb_names = {str(s).split(":")[0].strip() for s in (m.get("forbidden") or {}).get("skills", [])}
    forb = list(lo.get("forbidden") or [])
    row(
        "[modes.low] forbidden covers the implemented skills and is in the manifest",
        set(impls) <= set(forb) and set(forb) <= fb_names,
        f"{forb} (manifest {sorted(fb_names)})",
    )
    if robot:
        src = str((m.get("limits") or {}).get("enforced_by", ""))
        row("toolkit [limits] enforced by the shared limit / servo path (B0)", "bodies/" in src, src)
    # ---------------------------------------------------------------- seat
    seat = ((d.get("seat") or {}).get("low") or {}).get("files") or {}
    want = {t["file"]: t["source"] for t in m.get("tools", []) if t.get("kind") != "interface"}
    want[str(lo.get("toolkit_path", ""))] = lo.get("toolkit")
    missing = {k: v for k, v in want.items() if seat.get(k) != v}
    row(
        "[seat.low] files ship the manifest's tools and the manifest at toolkit_path",
        not missing,
        f"missing or different: {missing}" if missing else f"{len(want)} file(s)",
    )
    blocked = list((m.get("forbidden") or {}).get("modules", []))
    if hi is not None:
        blocked.append(str(hi.get("implementation", "")).partition(":")[0])
    cs = lo.get("cases") or {}
    blocked.append(str(cs.get("hidden", "")))
    leak = sorted(
        src for src in seat.values() for b in blocked if b and (src == b or b.startswith(src.rstrip("/") + "/"))
    )
    row("[seat.low] ships no forbidden module, no platform implementation, no hidden case", not leak, leak or "")
    # ---------------------------------------------------------------- deliverable
    dl = lo.get("deliverable") or {}
    path = str(dl.get("path", ""))
    fn = Path(path).stem
    sig = str(dl.get("signature", ""))
    tl = dl.get("time_limits_s") or {}
    ok = (
        path.startswith(SKILL_DIR)
        and path.endswith(".py")
        and fn in impls
        and sig.startswith(fn + "(")
        and re.search(r"\*\s*,\s*state\s*,\s*spec\s*\)", sig) is not None
        and isinstance(tl.get("load"), (int, float))
        and isinstance(tl.get(fn), (int, float))
        and dl.get("allowed")
    )
    row(
        "[modes.low.deliverable] path under /app/output/skill/, signature fn(..., *, state, spec), allowed, time "
        "limits (load and the call)",
        ok,
        f"{path}: {sig}; {tl}",
    )
    # ---------------------------------------------------------------- evaluator, references, thresholds
    ev = sport_dir / str(lo.get("evaluator", ""))
    ok = ev.is_file() and {"api_case", "platform", "skill_spec"} <= _defs(ev)[0]
    row(
        "[modes.low] evaluator module has api_case, platform, skill_spec (skilleval/evaluate.py hooks)",
        ok,
        lo.get("evaluator"),
    )
    for k in ("reference", "boundary"):
        p = sport_dir / str(lo.get(k, ""))
        row(
            f"[modes.low] {k} skill holds the deliverable's file",
            bool(lo.get(k)) and (p / Path(path).name).is_file(),
            f"{lo.get(k)}/{Path(path).name}",
        )
    bd = m.get("boundary") or {}
    row(
        "[modes.low] boundary = the manifest's [boundary] baseline",
        lo.get("boundary") == bd.get("baseline"),
        f"{lo.get('boundary')} vs {bd.get('baseline')}",
    )
    th = lo.get("thresholds") or {}
    rmin, bmax = th.get("reference_min"), th.get("boundary_max")
    row(
        "[modes.low] thresholds: 0 < reference_min <= 1, boundary_max = the manifest's threshold < reference_min",
        isinstance(rmin, (int, float))
        and isinstance(bmax, (int, float))
        and 0 < rmin <= 1
        and 0 <= bmax < rmin
        and bmax == bd.get("threshold"),
        th,
    )
    # ---------------------------------------------------------------- cases
    hp, pp = sport_dir / str(cs.get("hidden", "")), sport_dir / str(cs.get("public", ""))
    if hp.is_file() and pp.is_file():
        bad = cases_mod.problems(cases_mod.load(hp), cases_mod.load(pp))
        row(
            "[modes.low.cases] hidden and public disjoint, public = practice view only",
            not bad,
            "; ".join(bad) or f"{len(cases_mod.load(hp))} hidden, {len(cases_mod.load(pp))} public",
        )
    else:
        row("[modes.low.cases] hidden and public files exist", False, cs)
    row(
        "[seat.low] files ship the public practice cases at practice_path",
        seat.get(str(cs.get("practice_path", ""))) == cs.get("public"),
        cs.get("practice_path"),
    )
    # ---------------------------------------------------------------- the skill in the loop (optional)
    il = lo.get("inloop")
    if il is not None:
        rows.extend(inloop_rows(il, impls, dl, sport_dir))
    return rows


INLOOP_KEYS = {"skills", "step_every", "free", "noop", "cpus", "memory", "reference_class", "raw_rule"}


def inloop_rows(il, impls: list, dl: dict, sport_dir: Path) -> list[tuple[str, bool, str]]:
    """[modes.low.inloop] (skilleval/inloop.py, tools/generate.py): the skills the match lowers with the player's file
    are implemented ones; step_every a positive integer; free / noop well formed; the container's resources; the
    in-loop oracle (file.py:Name) exists."""
    if not isinstance(il, dict):
        return [("[modes.low.inloop] is a table", False, repr(il))]
    out = []
    unknown = sorted(set(il) - INLOOP_KEYS)
    out.append(("[modes.low.inloop] keys", not unknown, f"unknown: {unknown}" if unknown else sorted(il)))
    sk = list(il.get("skills") or impls)
    out.append(("[modes.low.inloop] skills are implemented ([modes.low] implements)", bool(sk) and set(sk) <= set(impls),
                sk))
    se = il.get("step_every", 2)
    out.append(("[modes.low.inloop] step_every is a positive integer", isinstance(se, int) and se >= 1, se))
    free, noop = il.get("free", []), il.get("noop", {"type": "noop"})
    ok = isinstance(free, list) and all(isinstance(x, str) for x in free) and not set(free) & set(sk) and \
        isinstance(noop, dict) and isinstance(noop.get("type"), str)
    out.append(("[modes.low.inloop] free = low-level command types (not a skill), noop = a command", ok,
                f"free {free}, noop {noop}"))
    cpus, mem = il.get("cpus", 1), str(il.get("memory", "2g"))
    out.append(("[modes.low.inloop] the skill container's cpus (0 < cpus <= 4) and memory (e.g. 2g)",
                isinstance(cpus, (int, float)) and 0 < cpus <= 4 and re.fullmatch(r"\d+[mg]", mem) is not None,
                f"cpus {cpus}, memory {mem}"))
    ref = str(il.get("reference_class", ""))
    f, _, obj = ref.partition(":")
    f = f if f.endswith(".py") else f + ".py"     # "module:Name" as [players] reference_class, or "file.py:Name"
    ok = bool(ref) and (sport_dir / f).is_file() and bool(obj) and obj in _defs(sport_dir / f)[0]
    out.append(("[modes.low.inloop] reference_class (module:Name): the oracle that plays through the skill", ok, ref))
    tl = dl.get("time_limits_s") or {}
    miss = [x for x in sk if not isinstance(tl.get(x), (int, float))]
    out.append(("[modes.low.inloop] every in-loop skill has a time limit (the safety cap of a call)", not miss,
                f"missing: {miss}" if miss else tl))
    return out


def main(argv):
    """python3 skilleval/declare.py SPORT_DIR ...: print the rows, exit 1 on a failure."""
    import tomllib

    rc = 0
    for s in argv:
        p = Path(s)
        for name, ok, det in check(p.name, tomllib.loads((p / "sport.toml").read_text()), p):
            print(f"  {'ok  ' if ok else 'FAIL'} {p.name}: {name}" + (f": {det}" if det else ""))
            rc |= not ok
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
