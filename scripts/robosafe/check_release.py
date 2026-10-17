#!/usr/bin/env python3
"""RoboSafeBench's frozen release in tasks/: every rsb-* task directory is the one recorded in release.json.

From 0.5.4 the served set mixes two frozen releases: the 0.5.4 selection (exported from RoboSafeBench's own release
tooling, which this repository does not carry, so gen_tasks.py / gen_realtime.py cannot re-render it) and the 0.5.3
tasks kept as the easy set. This check stands in for the generators' check mode (ci_checks/check-generated-tasks.sh):
    python3 scripts/robosafe/check_release.py check    # standard library only
    python3 scripts/robosafe/check_release.py write    # after a deliberate task change: rewrite release.json
It checks that the rsb-* directories are exactly release.json's tasks; that each task's DIGEST is its recomputed digest
(scripts/task_conventions.py) and the recorded one; that its compose image is its release's image (and `robosafe_version` 0.5.4 exactly for the 0.5.4 release);
that the easy set (docs/easy_set.toml) holds every base with no 0.5.4 task and no base with one; and that the files
kept out of git (scripts/robosafe/assets.json) are the ones images/robosafe/context/robosafe-src.sha256 lists; and that
each task's service, grader and solution helpers are byte for byte its release's (shared_problems): the 0.5.4 tasks'
the ones in scripts/robosafe/shared/, the 0.5.3 tasks' those in scripts/robosafe/shared-0.5.3/ (the 0.5.3 adapter,
grader and oracle drivers, kept since board 0151) and otherwise scripts/robosafe/shared/ (the layer, the clients).
scripts/robosafe/sync_release.py copies them into the tasks, normalizes them and rewrites release.json.
"""
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import task_conventions as tc  # noqa: E402

RELEASE = HERE / "release.json"
SHARED_053 = HERE / "shared-0.5.3"        # the 0.5.3 release's own adapter, grader and oracle drivers
IMAGE = {"0.5.3": "ghcr.io/mll-lab-nu/eai-robosafe:0.5.3", "0.5.4": "ghcr.io/mll-lab-nu/eai-robosafe:0.5.4"}


def facts(task: pathlib.Path) -> dict:
    toml = (task / "task.toml").read_text()
    version = re.search(r'^robosafe_version = "([^"]+)"', toml, re.M)
    images = sorted(set(re.findall(r"^\s*image:\s*(\S+)", (task / "environment" / "docker-compose.yaml").read_text(), re.M)))
    return {"digest": tc.digest(task), "robosafe_version": version and version.group(1),
            "images": [i for i in images if "eai-robosafe" in i or i.startswith("sha256:")]}


def tasks() -> list:
    return sorted(p for p in (ROOT / "tasks").glob("rsb-*") if p.is_dir())


def problems() -> list:
    rel = json.loads(RELEASE.read_text())
    bad = []
    have = {p.name: p for p in tasks()}
    want = rel["tasks"]
    bad += [f"{n}: in tasks/ but not in release.json" for n in sorted(set(have) - set(want))]
    bad += [f"{n}: in release.json but not in tasks/" for n in sorted(set(want) - set(have))]
    for name in sorted(set(have) & set(want)):
        task, rec = have[name], want[name]
        f = facts(task)
        if (task / "DIGEST").read_text().strip() != f["digest"]:
            bad.append(f"{name}: DIGEST is not the task's digest")
        if f["digest"] != rec["digest"]:
            bad.append(f"{name}: digest {f['digest']} differs from release.json ({rec['digest']})")
        if rec["release"] not in IMAGE or (f["robosafe_version"] == "0.5.4") != (rec["release"] == "0.5.4"):
            bad.append(f"{name}: robosafe_version {f['robosafe_version']!r}, release {rec['release']!r}")
        if f["images"] != [IMAGE.get(rec["release"])]:
            bad.append(f"{name}: compose image {f['images']}, expected {IMAGE.get(rec['release'])}")
    easy = {b for b, e in tc.easy_set().items() if e.get("benchmark") == "RoboSafeBench"}
    by_base = {}
    for name, rec in want.items():
        by_base.setdefault(tc.base_of(pathlib.Path(name)), set()).add(rec["release"])
    for base, releases in sorted(by_base.items()):
        if ("0.5.4" in releases) == (base in easy):
            bad.append(f"{base}: {'in' if base in easy else 'not in'} the easy set, releases {sorted(releases)}")
    bad += [f"{b}: in the easy set but no rsb-* task has this base" for b in sorted(easy - set(by_base))]
    bad += [p for name in sorted(set(have) & set(want)) for p in shared_problems(have[name], want[name]["release"])]
    bad += assets_problems()
    return bad


def source_dirs(task: pathlib.Path, release: str = "0.5.4") -> list:
    """Where a task's shared files come from, first match wins: the 0.5.3 release's own (realtime clock's first) for a
    0.5.3 task, then scripts/robosafe/shared/ (the realtime clock's own first) and scripts/robosafe/."""
    realtime = task.name.endswith("-realtime")
    shared = ([HERE / "shared/realtime"] if realtime else []) + [HERE / "shared/standard", HERE / "shared/solution", HERE]
    if release != "0.5.3":
        return shared
    return ([SHARED_053 / "realtime"] + shared[:1] if realtime else []) + [SHARED_053 / "standard",
                                                                          SHARED_053 / "solution"] + shared[realtime:]


def source_of(task: pathlib.Path, rel: str, release: str = "0.5.4"):
    """The file a task's `rel` must equal (None: no source). A realtime task's tests/grade_rsb.py is its release's
    standard grader."""
    name = pathlib.PurePosixPath(rel).name
    if name == "grade_rsb.py":
        return (SHARED_053 if release == "0.5.3" else HERE / "shared") / "standard/grade.py"
    return next((d / name for d in source_dirs(task, release) if (d / name).is_file()), None)


def tracked(task: pathlib.Path) -> list:
    """The task files that have a shared source: every .py and solution/solve.sh, but the resource monitor's."""
    out = []
    for f in sorted(task.rglob("*")):
        rel = f.relative_to(task).as_posix()
        if not f.is_file() or not (rel.endswith(".py") or rel == "solution/solve.sh") or rel == "tests/rcb_limits.py" \
                or rel.startswith("environment/rcb_monitor/"):
            continue
        out.append(rel)
    return out


def shared_problems(task: pathlib.Path, release: str = "0.5.4") -> list:
    """A task's service, grader and solution helpers are its release's files (source_of), byte for byte, so that a fix
    there (and its unit tests) is the code the task runs: after editing one, run scripts/robosafe/sync_release.py."""
    realtime = task.name.endswith("-realtime")
    sim = ["rcb1.py", "rcb_rsb.py", "rcb_service.py", "replay.py", "server.py"]
    need = ["environment/rcb1.py", "environment/rcb_client.py", "solution/solve.sh", "tests/grade.py"]
    if release != "0.5.3":                    # 0.5.4's picture delivery and public observation helpers
        sim += ["candidate_identity.py", "picture_delivery.py"]
        need += ["solution/public_observation_delivery.py", "solution/public_observation_plan.py"]
    need += ["environment/sim/" + f for f in sim]
    need += (["environment/sim/rcb_realtime.py", "environment/sim/rcb_rsb_rt.py", "solution/oracle_rt.py", "tests/grade_rsb.py"]
             if realtime else ["solution/oracle_replay.py"])
    bad = [f"{task.name}/{rel}: missing" for rel in need if not (task / rel).is_file()]
    for rel in tracked(task):
        src = source_of(task, rel, release)
        if src is None:
            bad.append(f"{task.name}/{rel}: no source in scripts/robosafe/shared/ or scripts/robosafe/")
        elif (task / rel).read_bytes() != src.read_bytes():
            bad.append(f"{task.name}/{rel}: differs from {src.relative_to(ROOT)}")
    return bad


def assets_problems() -> list:
    """scripts/robosafe/assets.json (the files kept out of git) agrees with the build context's checksum list."""
    pin = json.loads((HERE / "assets.json").read_text())
    ctx = ROOT / "images/robosafe/context/robosafe-src"
    listed = dict(reversed(l.split(None, 1)) for l in (ctx.parent / "robosafe-src.sha256").read_text().splitlines())
    base = pathlib.Path(pin["context"]).relative_to("images/robosafe/context/robosafe-src").as_posix()
    bad = []
    for rel, sha in sorted(pin["files"].items()):
        path = "./" + base + "/" + rel[len(pin["prefix"]):]
        if listed.get(path, listed.get(path[2:])) != sha:
            bad.append(f"assets.json {rel}: not the sha256 context/robosafe-src.sha256 lists for {path}")
    return bad


def write() -> None:
    old = json.loads(RELEASE.read_text())["tasks"] if RELEASE.exists() else {}
    out = {}
    for task in tasks():
        f = facts(task)
        release = next((r for r, i in IMAGE.items() if f["images"] == [i]), old.get(task.name, {}).get("release"))
        out[task.name] = {"release": release, "digest": f["digest"]}
    RELEASE.write_text(json.dumps({"schema": "rsb.rcb-release/1", "tasks": out}, indent=1, sort_keys=True) + "\n")
    print(f"wrote {RELEASE.relative_to(ROOT)}: {len(out)} tasks")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    if mode == "write":
        write()
        sys.exit(0)
    if mode != "check":
        sys.exit("usage: check_release.py [check|write]")
    bad = problems()
    for b in bad:
        print("FAIL", b)
    if bad:
        sys.exit(1)
    n = len(json.loads(RELEASE.read_text())["tasks"])
    print(f"checked {n} RoboSafeBench task dirs against release.json")
