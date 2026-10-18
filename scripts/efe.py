#!/usr/bin/env python3
"""Embodied First Exam runs on Harbor. `uv tool install --force -e . --with-executables-from harbor` installs `harbor` (Harbor 0.23.0, plus the
flags below on `harbor run`) and `efe` (the same, `efe run ...`). Run from anywhere; the tasks are this clone's.

  harbor run -a codex -m openai/gpt-6-luna            # the core set (docs/core_set.toml), every mode: the default
  harbor run --all -a codex -m openai/gpt-6-luna      # every task
  harbor run --standard -a claude-code -m anthropic/claude-fable-5-1   # --privileged / --standard / --standard-realtime
  harbor run --all --privileged -i 'robotwin_2_0_*' -a oracle          # -i / -x filter within the set
  harbor run -p tasks/<task> -a nop                   # one task: Harbor's own -p, untouched

Set: --core (default) or --all. Modes: any of --privileged, --standard, --standard-realtime; none = every mode.
--benchmark <label> keeps one benchmark (its README label). --list prints the task dirs and runs nothing.
A `harbor run` that names its own tasks (-p, -d, -t, -c) is Harbor's, unchanged; so is every other subcommand."""
import fnmatch, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import task_conventions as tc  # noqa: E402

MODES = {"--privileged": "privileged", "--privilege": "privileged", "--standard": "standard",
         "--standard-realtime": "standard-realtime", "--standard_realtime": "standard-realtime"}
SOURCES = ("-p", "--path", "-d", "--dataset", "-t", "--task", "-c", "--config", "--task-git-url")


def harbor(args: list[str], app=None) -> int:
    if app is None:
        from harbor.cli import main as hm
        app = getattr(hm.app, "__wrapped_app__", hm.app)
    sys.argv = ["harbor", *args]
    return app() or 0


def run(argv: list[str], app=None) -> int:
    """`harbor run` with the set / mode flags: picks the task dirs, then `harbor run -p <clone>/tasks -i <task> ...`."""
    if any(a in SOURCES or a.startswith(tuple(s + "=" for s in SOURCES if s.startswith("--"))) for a in argv):
        if not any(a in MODES or a in ("--core", "--all", "--benchmark", "--list") for a in argv):
            return harbor(["run", *argv], app)                # the user's own task source: plain Harbor
    use_all, modes, benches, inc, exc, listing, rest = False, set(), [], [], [], False, []
    it = iter(argv)
    for a in it:
        if a in ("--all", "--core"):
            use_all = a == "--all"
        elif a in MODES:
            modes.add(MODES[a])
        elif a == "--benchmark":
            benches.append(next(it, ""))
        elif a in ("-i", "--include-task-name"):
            inc.append(next(it, ""))
        elif a in ("-x", "--exclude-task-name"):
            exc.append(next(it, ""))
        elif a == "--list":
            listing = True
        elif a in ("-h", "--help"):
            print(__doc__); return harbor(["run", "--help"], app)
        else:
            rest.append(a)
    tasks = sorted(p.name for p in (ROOT / "tasks").iterdir() if (p / "task.toml").is_file())
    pick = tasks if use_all else sorted(set(tc.core_set()) & set(tasks))
    pick = [t for t in pick if (not modes or tc.mode_of(ROOT / "tasks" / t) in modes)
            and (not benches or tc.bench_of(ROOT / "tasks" / t) in benches)
            and (not inc or any(fnmatch.fnmatchcase(t, p) for p in inc))
            and not any(fnmatch.fnmatchcase(t, p) for p in exc)]
    if not pick:
        print("no task matches", file=sys.stderr); return 2
    print(f"{len(pick)} task(s) of the {'full' if use_all else 'core'} set"
          + (f", {', '.join(sorted(modes))}" if modes else ""), file=sys.stderr)
    if listing:
        print("\n".join(pick)); return 0
    return harbor(["run", "-p", str(ROOT / "tasks"), *[x for t in pick for x in ("-i", t)], *rest], app)


def main() -> int:
    """The `efe` command: `efe run ...` = `harbor run ...` above, `efe` alone prints this help."""
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.replace("harbor run", "efe run")); return 0
    return run(argv[1:]) if argv[0] == "run" else harbor(argv)


if __name__ == "__main__":
    sys.exit(main())
