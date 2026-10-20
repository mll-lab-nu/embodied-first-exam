#!/usr/bin/env python3
"""Embodied First Exam runs on Harbor. `uv tool install --force -e . --with-executables-from harbor` (in a clone) or
`pip install embodied-first-exam` installs `harbor` (Harbor 0.23.0, plus the flags below on `harbor run`) and `efe` (the
same, `efe run ...`). Run from anywhere. The tasks: $EFE_ROOT, else the clone that contains the working directory, else
the clone of an editable install, else a shallow clone of the release tag v<version> made on first use in
~/.cache/embodied-first-exam/<version> (find_root).

  harbor run -a codex -m openai/gpt-6-astra            # core: each core task in its default mode (the default)
  harbor run --core --privileged -a codex -m openai/gpt-6-astra   # the core tasks in another mode (also --standard, --standard-realtime)
  harbor run --all -a codex -m openai/gpt-6-astra      # every task dir
  harbor run --all --privileged -i 'robotwin_2_0_*' -a oracle          # mode flags and -i / -x filter within the set
  harbor run --benchmark roboarc -a codex -m openai/gpt-6-astra   # one benchmark's core tasks
  harbor run -d embodied-first-exam@core -a codex -m openai/gpt-6-astra   # the same sets as a dataset: @core, @all
  harbor run -p tasks/<benchmark>/<task> -a nop       # one task: Harbor's own -p, untouched
  harbor run -p tasks/<benchmark> -a nop              # every task of one benchmark: Harbor's own -p, untouched

Set: --core (default) or --all. core = the tasks of docs/core_set.toml, each in its default_mode; with mode flags, each
core task in those modes (a task without that mode is skipped, and counted). all = every task dir; mode flags filter it.
Modes: any of --privileged, --standard, --standard-realtime.
-d embodied-first-exam[@core|@all] (also `efe`) is --core / --all (no version: core); any other -d is Harbor's.
--benchmark <name> keeps a benchmark: its README label or its folder under tasks/ (repeatable). With any of these flags,
-p <dir> (a task dir, a benchmark folder or tasks/) narrows the set to the task dirs under it, -l <n> keeps the first n of
them, and -c <file> is layered after the wrapper's job config. --list prints the task dirs and runs nothing. The tasks
are stamped in place (scripts/stamp_mtimes.py) and handed to Harbor as one dataset per benchmark folder (Harbor's
local datasets are not searched recursively). A
`harbor run` that names its own tasks (-p, -d, -t, -c) and none of these flags is Harbor's, unchanged; so is every other
subcommand."""
import fnmatch, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

# --- the task tree (board 0209): where the tasks and their scripts/ come from -------------------------------------------
REPO_URL = "https://github.com/mll-lab-nu/embodied-first-exam.git"
_ROOT: list[Path] = []


def is_tree(d: Path) -> bool:
    """A checkout of this repository: the core set, the tasks and the scripts that read them."""
    return (d / "docs/core_set.toml").is_file() and (d / "tasks").is_dir() and (d / "scripts/task_conventions.py").is_file()


def cache_dir() -> Path:
    from importlib.metadata import PackageNotFoundError, version
    try:
        ver = version("embodied-first-exam")
    except PackageNotFoundError:
        ver = "main"
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "embodied-first-exam" / ver


def cached_clone(d: Path) -> Path:
    """`git clone --depth 1` of the tag v<version> (main when there is no such tag) into d, once; SystemExit(2) on failure."""
    tag = "main" if d.name == "main" else f"v{d.name}"
    try:
        r = subprocess.run(["git", "ls-remote", "--exit-code", "--tags", REPO_URL, f"refs/tags/{tag}"], capture_output=True)
    except FileNotFoundError:
        print("efe: the tasks need git (no clone here, no EFE_ROOT)", file=sys.stderr); raise SystemExit(2)
    if r.returncode not in (0, 2):
        print(f"efe: cannot reach {REPO_URL} (git ls-remote exit {r.returncode}); clone it and run from there, or set "
              "EFE_ROOT", file=sys.stderr); raise SystemExit(2)
    if tag != "main" and r.returncode == 2:
        print(f"efe: {REPO_URL} has no tag {tag}: using main instead (delete {d} to clone again later)", file=sys.stderr)
        tag = "main"
    print(f"efe: no clone here and no EFE_ROOT: cloning the tasks ({tag}) into {d}, once", file=sys.stderr)
    d.parent.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix=f".{d.name}-", dir=d.parent)
    try:
        if subprocess.run(["git", "clone", "--depth", "1", "--branch", tag, REPO_URL, tmp]).returncode:
            print(f"efe: git clone of {tag} failed", file=sys.stderr); raise SystemExit(2)
        if not is_tree(d):                                  # else another run made it meanwhile
            try:
                os.rename(tmp, d)
            except OSError as e:
                print(f"efe: cannot place the clone at {d} ({e}); remove {d} and run again", file=sys.stderr)
                raise SystemExit(2)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return d


def find_root(clone: bool = True) -> Path | None:
    """The task tree: $EFE_ROOT; else the checkout that contains the working directory; else the checkout this file is in
    (`uv tool install -e .`); else the cached clone (made here on first use when clone; None when not)."""
    if _ROOT:
        return _ROOT[0]
    cwd = Path.cwd().resolve()
    if os.environ.get("EFE_ROOT"):
        d = Path(os.environ["EFE_ROOT"]).expanduser().resolve()
        if not is_tree(d):
            print(f"EFE_ROOT={d}: not a checkout of {REPO_URL}", file=sys.stderr); raise SystemExit(2)
    else:
        d = next((p for p in (cwd, *cwd.parents, Path(__file__).resolve().parents[1], cache_dir()) if is_tree(p)), None)
        if d is None and clone:
            d = cached_clone(cache_dir())
    if d is not None:
        _ROOT.append(d)
    return d


class _Scripts:
    """The task tree's own scripts/<name>.py (task_conventions, stamp_mtimes), imported on first use."""
    def __init__(self, name: str):
        self._name = name

    def __getattr__(self, attr: str):
        import importlib
        d = str(find_root() / "scripts")
        if d not in sys.path:
            sys.path.insert(0, d)
        return getattr(importlib.import_module(self._name), attr)


tc = _Scripts("task_conventions")
# ------------------------------------------------------------------------------------------------------------------------

MODES = {"--privileged": "privileged", "--privilege": "privileged", "--standard": "standard",
         "--standard-realtime": "standard-realtime", "--standard_realtime": "standard-realtime"}
DATASET = ("embodied-first-exam", "efe")
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
    """The task dir names under the -p paths (a task dir, a benchmark folder, tasks/; a relative path that is not one
    here is taken in this clone, so `-p tasks/<benchmark>` works from anywhere); None: no -p given. SystemExit(2): a path
    that is neither."""
    if not paths:
        return None
    out: set[str] = set()
    for a in paths:
        d = Path(a).expanduser()
        if not d.is_dir() and not d.is_absolute() and (find_root() / d).is_dir():
            d = find_root() / d
        if not d.is_dir():
            print(f"-p {a}: no such directory (here or in {find_root()})", file=sys.stderr)
            raise SystemExit(2)
        d = d.resolve()
        if (d / "task.toml").is_file():
            out.add(d.name)
        else:
            out |= {t.parent.name for pat in ("*/task.toml", "*/*/task.toml") for t in d.glob(pat)}
    return out


def stamp(pick: list[str]) -> bool:
    """Give the picked task dirs' files their content-derived mtimes in place before Harbor builds any image from them
    (scripts/stamp_mtimes.py, issue #258: a checkout's shared mtimes let BuildKit put another task's file in an image).
    Files already stamped are skipped. False: a file could not be stamped."""
    stamp_mtimes = _Scripts("stamp_mtimes")
    err = sum(stamp_mtimes.stamp_tree(str(tc.task_dir(t)))["err"] for t in pick)
    if err:
        print(f"stamp_mtimes: {err} file(s) could not be stamped; no image is built from an unstamped task "
              "(docs/protocol/running.md, Building task images)", file=sys.stderr)
    return not err


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


def load_env() -> None:
    """The working directory's and the clone's .env (cp .env.example .env) into the environment: their non-empty keys
    the shell does not set (no clone is made for it)."""
    from dotenv import dotenv_values
    root = find_root(clone=False)
    for f in dict.fromkeys([Path.cwd() / ".env", *([root / ".env"] if root else [])]):
        for k, v in dotenv_values(f).items() if f.is_file() else ():
            if v and not v.startswith("#") and k not in os.environ:   # `KEY=   # note`: dotenv reads the note as the value
                os.environ[k] = v


def dataset_sets(argv: list[str]) -> list[str] | None:
    """argv with -d embodied-first-exam[@core|@all] turned into --core / --all; None: an unknown version."""
    out, it = [], iter(argv)
    for a in it:
        v = a.split("=", 1)[1] if a.startswith("--dataset=") else next(it, "") if a in ("-d", "--dataset") else None
        name, _, ver = (v or "").partition("@")
        if v is None or name not in DATASET:
            out += [a] if v is None or a.startswith("--dataset=") else [a, v]
        elif ver in ("", "core", "all"):
            out.append("--" + (ver or "core"))
        else:
            print(f"-d {v}: the versions are {name}@core and {name}@all", file=sys.stderr)
            return None
    return out


def run(argv: list[str], app=None) -> int:
    """`harbor run` with the set / mode / benchmark flags: picks the task dirs, then `harbor run -c <job config> ...`
    (config_file: one dataset per benchmark folder)."""
    argv = dataset_sets(argv)
    if argv is None:
        return 2
    load_env()
    ours = ("--core", "--all", "--benchmark", "--list")
    if any(a in SOURCES or a.startswith(tuple(s + "=" for s in SOURCES if s.startswith("--"))) for a in argv):
        if not any(a in MODES or a in ours or a.startswith("--benchmark=") for a in argv):
            return harbor(["run", *argv], app)                # the user's own task source: plain Harbor
    which, modes, benches, inc, exc, paths, listing, rest = "core", set(), [], [], [], [], False, []
    n_tasks = None
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
        elif a in ("-i", "--include-task-name") or a.startswith("--include-task-name="):
            inc.append(a.split("=", 1)[1] if "=" in a else next(it, ""))
        elif a in ("-x", "--exclude-task-name") or a.startswith("--exclude-task-name="):
            exc.append(a.split("=", 1)[1] if "=" in a else next(it, ""))
        elif a in ("-l", "--n-tasks") or a.startswith("--n-tasks="):   # Harbor's -l: applied here, to the picked set
            v = a.split("=", 1)[1] if "=" in a else next(it, "")
            if not v.isdigit():
                print(f"{a} {v!r}: the number of tasks to run", file=sys.stderr); return 2
            n_tasks = int(v)
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
    pick = pick[:n_tasks] if n_tasks is not None else pick
    if not pick:
        print("no task matches", file=sys.stderr); return 2
    print(f"{len(pick)} task(s) of " + which + (f", {', '.join(sorted(modes))}" if modes else "")
          + (f", {', '.join(sorted(set(benches)))}" if benches else ""), file=sys.stderr)
    if listing:
        print("\n".join(pick)); return 0
    if not stamp(pick):
        return 2
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
