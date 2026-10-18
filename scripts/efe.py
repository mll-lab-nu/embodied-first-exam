#!/usr/bin/env python3
"""efe: Embodied First Exam on Harbor. `efe run` picks the task dirs, then runs `harbor run -p tasks -i <task> ...`;
every argument it does not know (agent, model, -n, -k, --ak, -y, ...) goes to Harbor unchanged. Any other subcommand
is Harbor's own (`efe view jobs` = `harbor view jobs`). Install from a clone: `uv tool install -e .` (installs Harbor).

  efe run -a codex -m openai/gpt-6-luna                      # the core set (docs/core_set.toml), every mode
  efe run --all --standard -a claude-code -m anthropic/claude-fable-5-1
  efe run --core --privileged --standard-realtime -a codex -m openai/gpt-6-luna -n 8
  efe run --benchmark "RoboTwin 2.0" -a oracle               # one benchmark (its label, README task table)
  efe run --task robotwin_2_0_stack_blocks_two-standard -a nop   # one task (repeatable, globs work)
  efe list --core --standard                                 # the task dirs only (= efe run ... --dry-run)

Set: --core (default) or --all. Modes: --privileged, --standard, --standard-realtime (any of them; none = every mode).
--task NAME picks task dirs by name and ignores the set."""
import fnmatch, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import task_conventions as tc  # noqa: E402

MODES = {"--privileged": "privileged", "--privilege": "privileged", "--standard": "standard",
         "--standard-realtime": "standard-realtime", "--standard_realtime": "standard-realtime"}


def harbor(args: list[str]) -> int:
    """Harbor's CLI in this process (the same install as efe's), else the `harbor` on PATH."""
    try:
        from harbor.cli.main import app
    except ImportError:
        import os, shutil
        if not shutil.which("harbor"):
            print("harbor not found: uv tool install -e . (or uv tool install harbor==0.23.0)", file=sys.stderr); return 2
        os.execvp("harbor", ["harbor", *args])
    sys.argv = ["harbor", *args]
    return app() or 0


def run(argv: list[str], dry: bool = False) -> int:
    use_all, modes, benches, names, rest = False, set(), [], [], []
    it = iter(argv)
    for a in it:
        if a in ("-h", "--help"):
            print(__doc__); return 0
        if a == "--all":
            use_all = True
        elif a == "--core":
            use_all = False
        elif a in MODES:
            modes.add(MODES[a])
        elif a == "--benchmark":
            benches.append(next(it, ""))
        elif a == "--task":
            names.append(next(it, ""))
        elif a == "--dry-run":
            dry = True
        else:
            rest.append(a)
    tasks = sorted(p.name for p in (ROOT / "tasks").iterdir() if (p / "task.toml").is_file())
    if names:
        pick = [t for t in tasks if any(fnmatch.fnmatchcase(t, n) for n in names)]
    else:
        pick = tasks if use_all else sorted(set(tc.core_set()) & set(tasks))
    if modes:
        pick = [t for t in pick if tc.mode_of(ROOT / "tasks" / t) in modes]
    if benches:
        pick = [t for t in pick if tc.bench_of(ROOT / "tasks" / t) in benches]
    if not pick:
        print("no task matches", file=sys.stderr); return 2
    what = f"--task {' '.join(names)}" if names else ("all" if use_all else "core")
    print(f"{len(pick)} task(s): {what}" + (f", modes {', '.join(sorted(modes))}" if modes else "")
          + (f", benchmark {', '.join(benches)}" if benches else ""), file=sys.stderr)
    cmd = ["run", "-p", str(ROOT / "tasks")] + [x for t in pick for x in ("-i", t)] + rest
    if dry:
        print("\n".join(pick))
        print("harbor run -p tasks " + (f"-i {pick[0]} ... ({len(pick)} -i) " if len(pick) > 1 else f"-i {pick[0]} ")
              + " ".join(rest), file=sys.stderr)
        return 0
    return harbor(cmd)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__); return 0
    if argv[0] == "run":
        return run(argv[1:])
    if argv[0] == "list":
        return run(argv[1:], dry=True)
    return harbor(argv)


if __name__ == "__main__":
    sys.exit(main())
