#!/usr/bin/env python3
"""RoboOlympics task generator (docs/benchmarks/roboolympics.md): renders tasks/roboolympics-*-standard-realtime from
tasks.toml, sports.toml, templates/ and shared/.

    python3 scripts/roboolympics/gen_tasks.py render [NAME ...]   write the task directories
    python3 scripts/roboolympics/gen_tasks.py check               exit 1 if tasks/ differs from a fresh render (CI:
                                                                  ci_checks/check-generated-tasks.sh)

A task directory is:
  environment/sim/       the sidecar (mounted at /srv): the eai-standard/2.3 layer, copied unchanged from HumanoidBench
                         (scripts/humanoidbench/shared/realtime/rcb_realtime.py, shared/standard/rcb_service.py, rcb1.py),
                         the RoboOlympics adapter and its entry point (shared/sim/rcb_olympics.py, server.py), the
                         RoboOlympics core and renderers it needs (shared/sim/core, shared/sim/renderers) and the sport
                         (shared/sports/<sport>/ as sport/, without its built-in players and its own grader); the players'
                         visual meshes are in the eai-olympiad image (RO_LOD_DIR), checked against lod.json
  environment/           the agent's image: the client (scripts/humanoidbench/shared/realtime/rcb_client.py, rcb1.py) and
                         the client pins (scripts/eai_standard/client-requirements.txt)
  tests/                 the verifier (shared/tests/grade.py)
  solution/              the oracle: oracle/oracle_play.py and the sport's builtin_players.py
Standard library only (CI runs `check` without the simulator); every file is copied or filled from a template, then
scripts/task_conventions.py normalizes the task.
"""
from __future__ import annotations

import ast
import filecmp
import json
import re
import shutil
import sys
import tempfile
import textwrap
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
TASKS_DIR = ROOT / "tasks"
SHARED = HERE / "shared"
TEMPLATES = HERE / "templates"
HB = ROOT / "scripts" / "humanoidbench" / "shared"
CLIENT = ROOT / "scripts" / "eai_standard"
CLIENT_ENV = dict(l.split("=", 1) for l in (CLIENT / "client.env").read_text().splitlines() if "=" in l and not l.startswith("#"))
CLIENT_IMAGE = CLIENT_ENV["CLIENT_IMAGE"].strip()
CLIENT_REQUIREMENTS = CLIENT / CLIENT_ENV.get("CLIENT_REQUIREMENTS", "client-requirements.txt").strip()
LAYER = {"rcb_realtime.py": HB / "realtime" / "rcb_realtime.py", "rcb_service.py": HB / "standard" / "rcb_service.py",
         "rcb1.py": HB / "standard" / "rcb1.py"}
# the sport's files that stay out of the simulator: its built-in players (the oracle's, in solution/), RoboOlympics'
# own grader, and table tennis' duel and low level (these tasks play format match at the high level)
NOT_IN_SIM = {"builtin_players.py", "grade.py", "duel.py", "workers.py", "ipc.py", "robot_model.py", "seat",
              "tt_duel.xml"}
# the agent reaches the model APIs only (scripts/set_agent_egress.py HOSTS; the same list as every allowlist task)
HOSTS = ["chatgpt.com", "*.chatgpt.com", "auth.openai.com", "api.openai.com", "*.openai.com", "api.anthropic.com",
         "*.anthropic.com", "openrouter.ai", "*.openai.azure.com", "*.cognitiveservices.azure.com"]
REVIEW_PR = 106          # the pull request that adds the tasks (their oracle evidence)


def load() -> tuple[dict, list[dict], dict]:
    cfg = tomllib.loads((HERE / "tasks.toml").read_text())
    return cfg["defaults"], cfg["tasks"], tomllib.loads((HERE / "sports.toml").read_text())


def adapter_facts() -> dict:
    """From shared/sim/rcb_olympics.py, without importing it (it needs numpy): BREAK_S and, per sport profile, the
    sport.toml [spec] entries it drops (they describe RoboOlympics' own interface) and the literal ones it adds."""
    tree = ast.parse((SHARED / "sim" / "rcb_olympics.py").read_text())
    out = {"profiles": {}}
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", None) == "BREAK_S":
            out["break_s"] = ast.literal_eval(node.value)
        if isinstance(node, ast.ClassDef):
            p = {}
            for st in node.body:
                if isinstance(st, ast.Assign) and getattr(st.targets[0], "id", None) in ("drop", "rules"):
                    try:
                        p[st.targets[0].id] = ast.literal_eval(st.value)
                    except ValueError:
                        pass
            out["profiles"][node.name] = p
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", None) == "PROFILES":
            out["names"] = {k.value: v.id for k, v in zip(node.value.keys, node.value.values)}
    return out


def fill(template: str, ctx: dict) -> str:
    missing: list[str] = []

    def one(m: re.Match) -> str:
        if m.group(1) not in ctx:
            missing.append(m.group(1))
            return m.group(0)
        return str(ctx[m.group(1)])
    out = re.sub(r"\{\{(\w+)\}\}", one, template)
    if missing:
        raise KeyError(f"template placeholders with no value: {sorted(set(missing))}")
    return out


def flow(text: str) -> str:
    """One paragraph per blank-line-separated block (the TOML texts are wrapped at ~120 columns)."""
    return "\n\n".join(" ".join(p.split()) for p in text.strip().split("\n\n"))


RULES_NOTE = ("The rule texts come from RoboOlympics' `sport.toml`. Where they name RoboOlympics' own interface "
              "(`{'type': 'act', ...}`, `{'type': 'toss', ...}`, `{'type': 'none'}`, `{'type': 'target', ...}`, "
              "`state.*`, `game spec`, `/spec`), read: your `stroke`, `toss`, `rest`, `mallet` and `stop` rows, the "
              "proprio columns and `spec()`; where they say the world freezes for reviews, read: the break.\n")


def rules_md(sport_toml: dict, facts: dict, profile: str) -> str:
    """The rules from the sport's sport.toml: [spec] (without the entries about RoboOlympics' own interface, with the
    adapter's replacements), the tiebreaks and the deviations from the rulebook."""
    p = facts["profiles"].get(profile, {})
    spec = {k: v for k, v in (sport_toml.get("spec") or {}).items() if k not in set(p.get("drop", ()))}
    spec.update({k: v for k, v in p.get("rules", {}).items() if isinstance(v, str)})
    lines = [RULES_NOTE] + [f"- `{k}`: {' '.join(str(v).split())}" for k, v in spec.items()]
    tb = (sport_toml.get("tiebreaks") or {}).get("text")
    if tb:
        lines.append(f"- Winner: {' '.join(tb.split())}")
    rb = sport_toml.get("rulebook") or {}
    if rb.get("name"):
        lines.append(f"- Rulebook: {rb['name']}" + (f", {rb['version']}" if rb.get("version") else ""))
    for d in sport_toml.get("deviations") or []:
        lines.append(f"- Deviation {d['id']} ({d['rule']}): {' '.join(d['text'].split())}")
    return "\n".join(lines)


def context(t: dict, defaults: dict, sports: dict, facts: dict) -> dict:
    s = sports[t["sport"]]
    sport_toml = tomllib.loads((SHARED / "sports" / t["sport"] / "sport.toml").read_text())
    slowdown = int(defaults["slowdown"])
    break_s = float(facts["break_s"])
    actions = re.findall(r"^\| `(\w+)` \|", s["actions"], re.M)
    return {
        **{k: t[k] for k in ("name", "sport", "source", "family", "robot", "format", "action_level", "seed", "level",
                             "sim_cpus")},
        "title": s["title"], "title_lower": s["title"].lower(), "unit": s["unit"],
        "ball": {"tabletennis": "ball", "badminton": "shuttle", "airhockey": "puck"}[t["sport"]],
        "intro": flow(s["intro"]), "intro_line": " ".join(s["intro"].split()),
        "task_text": s["task_text"], "episode_text": s["episode_text"],
        "actions": s["actions"].strip(), "action_list": ", ".join(f"`{a}`" for a in actions),
        "first_action": actions[0], "proprio": flow(s["proprio"]), "cameras": flow(s["cameras"]), "tip": flow(s["tip"]),
        "robot_text": s["robot"], "rules": rules_md(sport_toml, facts, facts["names"][t["sport"]]),
        "refused_example": {"tabletennis": "a stroke whose contact time has already passed",
                            "badminton": "a toss when it is not your serve",
                            "airhockey": "a mallet target while the match stands still"}[t["sport"]],
        "revision": sport_toml["sport"]["revision"], "slowdown": slowdown,
        "wall_s_per_step": f"{0.01 * slowdown:g}", "break_s": f"{break_s:g}", "break_wall_s": f"{break_s * slowdown:g}",
        "agent_timeout_sec": int(defaults["agent_timeout_sec"]), "image": defaults["image"],
        "client_image": CLIENT_IMAGE, "allowed_hosts": json.dumps(HOSTS), "upstream": defaults["upstream"],
        "review_pr": REVIEW_PR,
    }


def write(out: Path, rel: str, text: str) -> None:
    p = out / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text.rstrip("\n") + "\n")
    if rel.endswith(".sh"):
        p.chmod(0o755)


def copy_tree(src: Path, dst: Path, skip=frozenset()) -> None:
    for f in sorted(src.rglob("*")):
        rel = f.relative_to(src)
        if "__pycache__" in rel.parts or any(part in skip for part in rel.parts) or not f.is_file():
            continue
        (dst / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(f, dst / rel)


def render(t: dict, defaults: dict, sports: dict, facts: dict, tasks_dir: Path = TASKS_DIR) -> Path:
    sys.path.insert(0, str(ROOT / "scripts"))
    from task_conventions import normalize
    ctx = context(t, defaults, sports, facts)
    out = tasks_dir / t["name"]
    if out.exists():
        shutil.rmtree(out)
    tpl = lambda name: fill((TEMPLATES / name).read_text(), ctx)  # noqa: E731
    write(out, "task.toml", tpl("task.toml"))
    write(out, "instruction.md", tpl("instruction.md"))
    write(out, "README.md", tpl("README.md"))
    write(out, "environment/docker-compose.yaml", tpl("docker-compose.yaml"))
    write(out, "environment/Dockerfile", tpl("Dockerfile"))
    write(out, "tests/Dockerfile", tpl("tests.Dockerfile"))
    write(out, "tests/test.sh", tpl("test.sh"))
    write(out, "solution/solve.sh", tpl("solve.sh"))
    sim = out / "environment" / "sim"
    copy_tree(SHARED / "sim", sim)
    for name, src in LAYER.items():
        shutil.copyfile(src, sim / name)
    copy_tree(SHARED / "sports" / t["sport"], sim / "sport", skip=NOT_IN_SIM)
    shutil.copyfile(HB / "realtime" / "rcb_client.py", out / "environment" / "rcb_client.py")
    shutil.copyfile(HB / "standard" / "rcb1.py", out / "environment" / "rcb1.py")
    shutil.copyfile(CLIENT_REQUIREMENTS, out / "environment" / "client-requirements.txt")
    shutil.copyfile(SHARED / "tests" / "grade.py", out / "tests" / "grade.py")
    shutil.copyfile(HERE / "oracle" / "oracle_play.py", out / "solution" / "oracle_play.py")
    shutil.copyfile(SHARED / "sports" / t["sport"] / "builtin_players.py", out / "solution" / "builtin_players.py")
    normalize(out)
    return out


def cmd_render(names: list[str]) -> int:
    defaults, tasks, sports = load()
    facts = adapter_facts()
    for t in tasks:
        if not names or t["name"] in names:
            print("rendered", render(t, defaults, sports, facts).relative_to(ROOT))
    return 0


def _diff(c: filecmp.dircmp, prefix: str) -> list[str]:
    out = [f"tasks/{prefix}/{x}: differs from its render" for x in c.diff_files]
    out += [f"tasks/{prefix}/{x}: not rendered" for x in c.left_only] + [f"tasks/{prefix}/{x}: missing" for x in c.right_only]
    for sub, sc in c.subdirs.items():
        out += _diff(sc, f"{prefix}/{sub}")
    return out


def cmd_check() -> int:
    """tasks/ must be what render writes from today's sources, with no stale roboolympics-* directory."""
    defaults, tasks, sports = load()
    facts = adapter_facts()
    failed: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        rendered = {render(t, defaults, sports, facts, Path(tmp)).name for t in tasks}
        for name in sorted(rendered):
            if not (TASKS_DIR / name).is_dir():
                failed.append(f"tasks/{name}: missing")
                continue
            failed += _diff(filecmp.dircmp(TASKS_DIR / name, Path(tmp) / name, ignore=["__pycache__"]), name)
            for f in sorted((Path(tmp) / name).rglob("*")):     # filecmp ignores modes: test.sh, solve.sh
                g = TASKS_DIR / name / f.relative_to(Path(tmp) / name)
                if f.is_file() and g.is_file() and (f.stat().st_mode & 0o111) != (g.stat().st_mode & 0o111):
                    failed.append(f"tasks/{name}/{f.relative_to(Path(tmp) / name)}: executable bit differs")
    failed += [f"tasks/{p.name}: no longer rendered" for p in sorted(TASKS_DIR.glob("roboolympics-*"))
               if p.name not in rendered]
    print("\n".join(f"FAIL {x}" for x in failed) or f"check: {len(rendered)} task dirs are what render writes")
    return 1 if failed else 0


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("render", "check"):
        print(textwrap.dedent(__doc__).strip().splitlines()[2:4][0])
        print("usage: gen_tasks.py render [NAME ...] | check")
        return 2
    return cmd_render(argv[1:]) if argv[0] == "render" else cmd_check()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
