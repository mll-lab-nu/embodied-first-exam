#!/usr/bin/env python3
"""Embodied First Exam runs on Harbor. `uv tool install --force -e . --with-executables-from harbor` installs `harbor` (Harbor 0.23.0, plus the
flags below on `harbor run`) and `efe` (the same, `efe run ...`). Run from anywhere; the tasks are this clone's.

  harbor run -a codex -m openai/gpt-6-luna            # core: each core task in its default mode (the default)
  harbor run --core --privileged -a codex -m openai/gpt-6-luna   # the core tasks in another mode (also --standard, --standard-realtime)
  harbor run --all -a codex -m openai/gpt-6-luna      # every task dir
  harbor run --all --privileged -i 'robotwin_2_0_*' -a oracle          # mode flags and -i / -x filter within the set
  harbor run --benchmark roboarc -a codex -m openai/gpt-6-luna   # one benchmark's core tasks
  harbor run -p tasks/<benchmark>/<task> -a nop       # one task: Harbor's own -p, untouched
  harbor run -p tasks/<benchmark> -a nop              # every task of one benchmark: Harbor's own -p, untouched

Set: --core (default) or --all. core = the tasks of docs/core_set.toml, each in its default_mode; with mode flags, each
core task in those modes (a task without that mode is skipped, and counted). all = every task dir; mode flags filter it.
Modes: any of --privileged, --standard, --standard-realtime.
--benchmark <name> keeps a benchmark: its README label or its folder under tasks/ (repeatable). With any of these flags,
-p <dir> (a task dir, a benchmark folder or tasks/) narrows the set to the task dirs under it, and -c <file> is layered
after the wrapper's job config. --list prints the task
dirs and runs nothing. The tasks are handed to Harbor as one dataset per benchmark folder (Harbor's local datasets are
not searched recursively). A `harbor run` that names its own tasks (-p, -d, -t, -c) and none of these flags is Harbor's,
unchanged; so is every other subcommand."""
import fnmatch, json, os, sys, tempfile
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


def bench_label(name: str) -> str | None:
    """A --benchmark value as its BENCHMARKS label: the label itself (any case) or its folder under tasks/."""
    by = {**{lab.lower(): lab for lab in tc.BENCHMARK_DIRS}, **{f: lab for lab, f in tc.BENCHMARK_DIRS.items()}}
    return by.get(name) or by.get(name.lower())


def under(paths: list[str]) -> set[str] | None:
    """The task dir names under the -p paths (a task dir, a benchmark folder, tasks/); None: no -p given."""
    if not paths:
        return None
    out: set[str] = set()
    for a in paths:
        d = Path(a).expanduser().resolve()
        if (d / "task.toml").is_file():
            out.add(d.name)
        else:
            out |= {t.parent.name for pat in ("*/task.toml", "*/*/task.toml") for t in d.glob(pat)}
    return out


def config_file(pick: list[str]) -> str:
    """A Harbor job config (-c) with the picked task dirs: one local dataset per benchmark folder, its task_names the
    picked dirs. Harbor reads it when the job is built; the caller removes it afterwards."""
    by: dict[str, list[str]] = {}
    for t in pick:
        by.setdefault(str(tc.task_dir(t).parent), []).append(t)
    cfg = {"datasets": [{"path": d, "task_names": names} for d, names in sorted(by.items())]}
    fd, path = tempfile.mkstemp(prefix="efe-job-", suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(cfg, f, indent=1)
    return path


def run(argv: list[str], app=None) -> int:
    """`harbor run` with the set / mode / benchmark flags: picks the task dirs, then `harbor run -c <job config> ...`
    (config_file: one dataset per benchmark folder)."""
    ours = ("--core", "--all", "--benchmark", "--list")
    if any(a in SOURCES or a.startswith(tuple(s + "=" for s in SOURCES if s.startswith("--"))) for a in argv):
        if not any(a in MODES or a in ours or a.startswith("--benchmark=") for a in argv):
            return harbor(["run", *argv], app)                # the user's own task source: plain Harbor
    which, modes, benches, inc, exc, paths, listing, rest = "core", set(), [], [], [], [], False, []
    it = iter(argv)
    for a in it:
        if a in ("--all", "--core"):
            which = a[2:]
        elif a in MODES:
            modes.add(MODES[a])
        elif a == "--benchmark" or a.startswith("--benchmark="):
            b = a.split("=", 1)[1] if "=" in a else next(it, "")
            lab = bench_label(b)
            if lab is None:
                print(f"--benchmark {b!r}: not a benchmark (a README label or a folder under tasks/: "
                      f"{', '.join(sorted(tc.BENCHMARK_DIRS.values()))})", file=sys.stderr)
                return 2
            benches.append(lab)
        elif a in ("-i", "--include-task-name"):
            inc.append(next(it, ""))
        elif a in ("-x", "--exclude-task-name"):
            exc.append(next(it, ""))
        elif a in ("-p", "--path") or a.startswith("--path="):
            paths.append(a.split("=", 1)[1] if "=" in a else next(it, ""))
        elif a in ("-c", "--config"):
            rest += [a, next(it, "")]                          # the user's config: layered after ours
        elif a in SOURCES or a.startswith(tuple(s + "=" for s in SOURCES if s.startswith("--") and s != "--config")):
            print(f"{a}: names its own tasks; it does not combine with {', '.join((*ours, *MODES))}", file=sys.stderr)
            return 2
        elif a == "--list":
            listing = True
        elif a in ("-h", "--help"):
            print(__doc__); return harbor(["run", "--help"], app)
        else:
            rest.append(a)
    tasks = [t.name for t in tc.iter_tasks()]
    missing: dict[str, list[str]] = {}
    pick = tasks if which == "all" else sorted(set(tc.core_tasks(modes, missing=missing)) & set(tasks))
    for m, ts in sorted(missing.items()):
        print(f"{len(ts)} core task(s) have no {m} mode: skipped", file=sys.stderr)
    scope = under(paths)
    pick = [t for t in pick if (scope is None or t in scope)
            and (not modes or tc.mode_of(Path(t)) in modes)
            and (not benches or tc.bench_of(Path(t)) in benches)
            and (not inc or any(fnmatch.fnmatchcase(t, p) for p in inc))
            and not any(fnmatch.fnmatchcase(t, p) for p in exc)]
    if not pick:
        print("no task matches", file=sys.stderr); return 2
    print(f"{len(pick)} task(s) of " + which + (f", {', '.join(sorted(modes))}" if modes else "")
          + (f", {', '.join(sorted(set(benches)))}" if benches else ""), file=sys.stderr)
    if listing:
        print("\n".join(pick)); return 0
    cfg = config_file(pick)
    try:
        return harbor(["run", "-c", cfg, *rest], app)
    finally:
        os.unlink(cfg)


def main() -> int:
    """The `efe` command: `efe run ...` = `harbor run ...` above, `efe` alone prints this help."""
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.replace("harbor run", "efe run")); return 0
    return run(argv[1:]) if argv[0] == "run" else harbor(argv)


if __name__ == "__main__":
    sys.exit(main())
