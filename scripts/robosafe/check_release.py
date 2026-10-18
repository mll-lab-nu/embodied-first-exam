#!/usr/bin/env python3
"""RoboSafeBench's frozen release in tasks/: every rsb-* task directory is the one recorded in release.json.

The served set mixes two frozen releases: the 0.5.4 selection (exported from RoboSafeBench's own release tooling, which
this repository does not carry) and the 0.5.3 tasks, kept out of the core set (apart from `rsb-c04-i00-standard`); no generator here re-renders them (the
privileged twins apart: gen_privileged.py). This check stands in for a generator's check mode
(ci_checks/check-generated-tasks.sh):
    python3 scripts/robosafe/check_release.py check    # standard library only
    python3 scripts/robosafe/check_release.py write    # after a deliberate task change: rewrite release.json
It checks that the rsb-* directories are exactly release.json's tasks; that each task's DIGEST is its recomputed digest
(scripts/task_conventions.py) and the recorded one; that its compose image is its release's image (and `robosafe_version` 0.5.4 exactly for the 0.5.4 release);
that the core set (docs/core_set.toml) lists no task of a base with no 0.5.4 task; and that the files
kept out of git (scripts/robosafe/assets.json) are the ones images/robosafe/context/robosafe-src.sha256 lists; and that
each task's service, grader and solution helpers are byte for byte its release's (shared_problems).

Each shared file has one copy (LAYERS, by layer): embodied_first_exam/benchmarks/robosafebench/<layer>/<name>, the benchmark's shared
task code, or, for a layer other benchmarks share (rcb1.py, the realtime clock and client), its source in scripts/.
The files outside environment/sim/ that many tasks would each carry (the paused standard client, the graders, the
privileged tooling and scrub, and the standard service's rcb_rsb.py / candidate_identity.py the privileged images also
take; IMG) are in the files-only image images/robosafe-files/ (private, like eai-robosafe), built from
embodied_first_exam/benchmarks/robosafebench/: a task's environment/Dockerfile and tests/Dockerfile take them with
`COPY --from=<image@digest>` to the same container paths (FROM_IMAGE), and the task directory holds no copy. Every
other shared file (the sim service, the oracle drivers and helpers, the privileged test.sh and solution; EFE) is copied
into the tasks, and each copy must equal its one copy. The 0.5.4 layers: `standard` (a paused task: the service, the
client, the standard grader, the oracle driver and the public observation helpers), `realtime` (the realtime clock's
own files) and `privileged` (the privileged tooling, grader and solution); the 0.5.3 release's own adapter, grader and
oracle drivers: `0.5.3` and `0.5.3-realtime` (a 0.5.3 task takes every other file from the 0.5.4 layers). To change a
shared file: edit its one copy; an IMG file also needs a new images/robosafe-files version (VERSION,
`scripts/files_image.py build robosafe-files`, push, `pin`). Then run scripts/robosafe/sync_release.py (it copies the
file into the standard and realtime tasks, writes the Dockerfiles' COPY --from lines, normalizes the tasks and rewrites
release.json); for a file of the privileged layer, or rcb_rsb.py / candidate_identity.py, also gen_privileged.py
render, then check_release.py write.
"""
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import files_image  # noqa: E402
import task_conventions as tc  # noqa: E402

RELEASE = HERE / "release.json"
TASKS = tc.bench_root("RoboSafeBench")   # tasks/robosafebench/
IMAGE = {"0.5.3": "ghcr.io/mll-lab-nu/eai-robosafe:0.5.3", "0.5.4": "ghcr.io/mll-lab-nu/eai-robosafe:0.5.4"}


def facts(task: pathlib.Path) -> dict:
    toml = (task / "task.toml").read_text()
    version = re.search(r'^robosafe_version = "([^"]+)"', toml, re.M)
    images = set(re.findall(r"^\s*image:\s*(\S+)", (task / "environment" / "docker-compose.yaml").read_text(), re.M))
    if privileged(task):              # the simulator is the agent's (and the verifier's) own image (gen_privileged.py)
        for d in ("environment", "tests"):
            images |= set(re.findall(r"^FROM\s+(\S+)", (task / d / "Dockerfile").read_text(), re.M))
    images = sorted(images)
    return {"digest": tc.digest(task), "robosafe_version": version and version.group(1),
            "images": [i for i in images if "eai-robosafe" in i or i.startswith("sha256:")]}


def privileged(task: pathlib.Path) -> bool:
    return task.name.endswith("-privileged")


def tasks() -> list:
    return sorted(p for p in TASKS.glob("rsb-*") if p.is_dir())


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
    # the release's own split: a base with no 0.5.4 task is never in the core set (docs/core_set.toml); a 0.5.4 base
    # may be out of it (solved by the reference run)
    try:
        core = tc.core_set()
    except (ValueError, OSError) as e:
        return bad + [f"docs/core_set.toml: {e}"]
    by_base = {}
    for name, rec in want.items():
        by_base.setdefault(tc.base_of(pathlib.Path(name)), {})[name] = rec["release"]
    for base, dirs in sorted(by_base.items()):
        if "0.5.4" not in dirs.values():
            bad += [f"{n}: in the core set, but its base has no 0.5.4 task" for n in sorted(dirs) if n in core]
    canon = canon_problems(want)
    if canon:                         # without its canonical copies no task's shared files can be checked
        return bad + canon
    bad += [p for name in sorted(set(have) & set(want)) for p in shared_problems(have[name], want[name]["release"])]
    bad += assets_problems()
    return bad


SIM = "environment/sim/"
SRC = ROOT / "embodied_first_exam" / "benchmarks" / "robosafebench"   # the one copy of the benchmark's shared task code: <layer>/<name>
IMG, EFE = "files image", "embodied_first_exam"   # LAYERS: in SRC and in the files image / in SRC, copied into the tasks
FILES = "robosafe-files"              # images/robosafe-files/FILES.json: the image that carries the IMG files (files_image.py)
# the canonical task of each layer: a task of that release and kind, whose environment/sim/ the unit tests import
CANON = {"standard": TASKS / "rsb-a01-i02-standard", "realtime": TASKS / "rsb-c04-i00-standard-realtime",
         "privileged": TASKS / "rsb-a01-i02-privileged", "0.5.3": TASKS / "rsb-a01-i00-standard",
         "0.5.3-realtime": TASKS / "rsb-a05-i00-standard-realtime"}
# layer -> {file name: IMG, EFE, or the repository path of a layer other benchmarks share (its one source)}
LAYERS = {
    "standard": {"server.py": EFE, "rcb_service.py": EFE, "rcb1.py": "scripts/eai_standard/rcb1.py",
                 "rcb_rsb.py": IMG, "replay.py": EFE, "picture_delivery.py": EFE, "candidate_identity.py": IMG,
                 "rcb_client.py": IMG, "grade.py": IMG, "oracle_replay.py": EFE, "solve.sh": EFE,
                 "public_observation_delivery.py": EFE, "public_observation_plan.py": EFE},
    "realtime": {"rcb_realtime.py": "scripts/humanoidbench/shared/realtime/rcb_realtime.py", "rcb_rsb_rt.py": EFE,
                 "rcb_client.py": "scripts/humanoidbench/shared/realtime/rcb_client.py", "grade.py": IMG,
                 "oracle_rt.py": EFE, "solve.sh": EFE},
    "privileged": {"rcb_rsb_privileged.py": IMG, "scrub.py": IMG, "grade.py": IMG, "test.sh": EFE, "gen.py": EFE,
                   "solve.sh": EFE},
    "0.5.3": {"server.py": EFE, "rcb_rsb.py": EFE, "replay.py": EFE, "grade.py": IMG, "oracle_replay.py": EFE},
    "0.5.3-realtime": {"rcb_rsb_rt.py": EFE, "oracle_rt.py": EFE},
}
# the task files the image build puts in place (COPY --from the files image): task path -> container path, by kind
FROM_IMAGE = {
    "standard": {"environment/rcb_client.py": "/opt/tools/rcb_client.py", "tests/grade.py": "/tests/grade.py"},
    "standard-realtime": {"tests/grade.py": "/tests/grade.py", "tests/grade_rsb.py": "/tests/grade_rsb.py"},
    "privileged": {"environment/scrub.py": "/tmp/scrub.py", "environment/rcb_rsb.py": "/opt/tools/rcb_rsb.py",
                   "environment/candidate_identity.py": "/opt/tools/candidate_identity.py",
                   "environment/rcb_rsb_privileged.py": "/opt/tools/rcb_rsb_privileged.py",
                   "tests/grade.py": "/tests/grade.py", "tests/rcb_rsb.py": "/tests/rcb_rsb.py",
                   "tests/candidate_identity.py": "/tests/candidate_identity.py",
                   "tests/rcb_rsb_privileged.py": "/tests/rcb_rsb_privileged.py"},
}


def shared(layer: str, name: str) -> pathlib.Path:
    """The one copy of a shared file: embodied_first_exam/benchmarks/robosafebench/<layer>/<name> (also the files image's source), or
    the shared layer's source in scripts/."""
    v = LAYERS[layer][name]
    return SRC / layer / name if v in (IMG, EFE) else ROOT / v


def sim_dir(release: str = "0.5.4", clock: str = "paused") -> pathlib.Path:
    """A canonical task's environment/sim/: the sim service as the tasks of that release and clock run it (the unit
    tests import it from there)."""
    layer = ("0.5.3" if release == "0.5.3" else "") + ("-realtime" if clock == "realtime" else "")
    return CANON[layer.lstrip("-") or "standard"] / SIM


def layers(task: pathlib.Path, release: str = "0.5.4") -> list:
    """Where a task's shared files come from, first match wins."""
    realtime = task.name.endswith("-realtime")
    if privileged(task):              # 0.5.4 only: its own tooling and grader, the standard service's rcb_rsb.py
        return ["privileged", "standard"]
    if release == "0.5.3":
        return ["0.5.3-realtime", "realtime", "0.5.3", "standard"] if realtime else ["0.5.3", "standard"]
    return ["realtime", "standard"] if realtime else ["standard"]


def layer_of(task: pathlib.Path, rel: str, release: str = "0.5.4"):
    """(layer, file name) of the file a task's `rel` must equal (None: no source). A realtime task's tests/grade_rsb.py
    is its release's standard grader."""
    name = pathlib.PurePosixPath(rel).name
    if name == "grade_rsb.py":
        return ("0.5.3" if release == "0.5.3" else "standard"), "grade.py"
    return next(((layer, name) for layer in layers(task, release) if name in LAYERS[layer]), None)


def source_of(task: pathlib.Path, rel: str, release: str = "0.5.4"):
    """The file a task's `rel` must equal (None: no source)."""
    got = layer_of(task, rel, release)
    return got and shared(*got)


def kind(task: pathlib.Path) -> str:
    return "privileged" if privileged(task) else "standard-realtime" if task.name.endswith("-realtime") else "standard"


def image_copies(task: pathlib.Path, release: str = "0.5.4") -> dict:
    """{task path: (file in the files image, container path)} of the files a task's image build takes from the files
    image (FROM_IMAGE): each the one copy of its layer (layer_of)."""
    out = {}
    for rel, dest in FROM_IMAGE[kind(task)].items():
        layer, name = layer_of(task, rel, release)
        if LAYERS[layer][name] != IMG:
            raise ValueError(f"{task.name}/{rel}: {layer}/{name} is not a file of the files image (LAYERS)")
        out[rel] = (f"{layer}/{name}", dest)
    return out


def copy_lines(task: pathlib.Path, release: str = "0.5.4") -> dict:
    """{context: [the Dockerfile's COPY --from lines of the files image]} (scripts/files_image.py copy_line)."""
    out = {"environment": [], "tests": []}
    for rel, (f, dest) in image_copies(task, release).items():
        out[rel.split("/", 1)[0]].append(files_image.copy_line(FILES, f, dest))
    return out


def image_lines(text: str) -> list:
    """The lines of a Dockerfile that take a file from the files image (whatever version they name)."""
    repo = files_image.image(FILES).split("@")[0].rsplit(":", 1)[0]
    return [l for l in text.splitlines() if re.match(rf"COPY\s+--from={re.escape(repo)}[:@]", l)]


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


def canon_problems(want: dict) -> list:
    """Each canonical task is a task of its layer's release and kind (release.json); the shared sources are complete."""
    bad = []
    for layer, task in CANON.items():
        release = "0.5.3" if layer.startswith("0.5.3") else "0.5.4"
        suffix = "-privileged" if layer == "privileged" else "-standard-realtime" if "realtime" in layer else "-standard"
        if want.get(task.name, {}).get("release") != release or not task.name.endswith(suffix):
            bad.append(f"CANON[{layer!r}] {task.name}: not a {release} {suffix[1:]} task of release.json")
    bad += [f"check_release.LAYERS[{layer!r}][{name!r}]: {shared(layer, name).relative_to(ROOT)} missing"
            for layer, d in LAYERS.items() for name in d if not shared(layer, name).is_file()]
    return bad + files_problems()


def files_problems() -> list:
    """embodied_first_exam/benchmarks/robosafebench/ is the IMG and EFE files of LAYERS; FILES.json pins the IMG ones
    (files_image.check); normalize's text rules leave them as they are (the files image's have no task copy for
    normalize to rewrite)."""
    import shutil
    import tempfile
    want = {f"{layer}/{name}" for layer, d in LAYERS.items() for name, v in d.items() if v in (IMG, EFE)}
    img = {f"{layer}/{name}" for layer, d in LAYERS.items() for name, v in d.items() if v == IMG}
    have = {p.relative_to(SRC).as_posix() for p in SRC.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    spec = files_image.spec(FILES)
    bad = [f"{SRC.relative_to(ROOT)}/{f}: not a file of check_release.LAYERS" for f in sorted(have - want)]
    if spec["source"] != SRC.relative_to(ROOT).as_posix() or set(spec["files"]) != img:
        bad.append(f"images/{FILES}/FILES.json: source {spec['source']} and files {sorted(spec['files'])} are not "
                   f"{SRC.relative_to(ROOT)} and LAYERS' files-image entries")
    bad += files_image.check(FILES)
    with tempfile.TemporaryDirectory() as d:
        shutil.copytree(SRC, pathlib.Path(d) / "src")
        tc.normalize_text_files(pathlib.Path(d) / "src")
        bad += [f"{SRC.relative_to(ROOT)}/{f}: normalize's text rules would rewrite it (scripts/task_conventions.py "
                "normalize_text_files): apply them to the source" for f in sorted(want & have)
                if (pathlib.Path(d) / "src" / f).read_bytes() != (SRC / f).read_bytes()]
    return bad


def shared_problems(task: pathlib.Path, release: str = "0.5.4") -> list:
    """A task's service, grader and solution helpers are its release's files (source_of), byte for byte, so that a fix
    there (and its unit tests) is the code the task runs: after editing one, run scripts/robosafe/sync_release.py. The
    files of the files image are not in the task: its Dockerfiles take exactly them (copy_lines), from the pinned image."""
    realtime = task.name.endswith("-realtime")
    if privileged(task):                      # gen_privileged.py: the instance copies and the oracle; the rest: the image
        need = ["environment/instance.json", "tests/instance.json", "tests/test.sh", "solution/solve.sh",
                "solution/gen.py", "solution/trajectory.npz"]
    else:
        sim = ["rcb1.py", "rcb_rsb.py", "rcb_service.py", "replay.py", "server.py"]
        need = ["environment/rcb1.py", "solution/solve.sh"]
        if release != "0.5.3":                # 0.5.4's picture delivery and public observation helpers
            sim += ["candidate_identity.py", "picture_delivery.py"]
            need += ["solution/public_observation_delivery.py", "solution/public_observation_plan.py"]
        need += ["environment/sim/" + f for f in sim]
        need += (["environment/rcb_client.py", "environment/sim/rcb_realtime.py", "environment/sim/rcb_rsb_rt.py",
                  "solution/oracle_rt.py"] if realtime else ["solution/oracle_replay.py"])
    bad = [f"{task.name}/{rel}: missing" for rel in need if not (task / rel).is_file()]
    for rel in tracked(task):
        src = source_of(task, rel, release)
        if rel in FROM_IMAGE[kind(task)]:
            bad.append(f"{task.name}/{rel}: in the task, but its Dockerfile takes it from images/{FILES} (remove it)")
        elif src is None:
            bad.append(f"{task.name}/{rel}: no source in check_release.LAYERS")
        elif (task / rel).read_bytes() != src.read_bytes():
            bad.append(f"{task.name}/{rel}: differs from {src.relative_to(ROOT)}")
    for ctx, lines in copy_lines(task, release).items():
        df = task / ctx / "Dockerfile"
        got = image_lines(df.read_text()) if df.is_file() else []
        if sorted(got) != sorted(lines):
            bad.append(f"{task.name}/{ctx}/Dockerfile: its COPY --from lines of images/{FILES} are not "
                       f"{[l.split(' ', 2)[2] for l in lines]} from the pinned {files_image.image(FILES)} "
                       "(run scripts/robosafe/sync_release.py / gen_privileged.py render)")
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
