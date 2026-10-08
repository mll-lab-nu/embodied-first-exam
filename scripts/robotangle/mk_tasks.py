#!/usr/bin/env python3
"""Render the RoboTangle tasks (formerly TopoGym; docs/benchmarks/robotangle.md):
tasks/robotangle-<family>-<tier>-i00-privileged and its standard twin -standard (eai-standard/2.3).

usage: python3 scripts/robotangle/mk_tasks.py [--check] [--list] [base ...]
  no base   every base in release.json
  --check   write nothing; exit 1 if a task would change, or if an identity check fails
  --list    print the bases with their evidence

Inputs, all in the repository (Python standard library only, plus scripts/task_conventions.normalize):
  release.json   the release (dev/jianwen commit, public simulator source, runtime) and, per base, where its frozen
                 instance comes from and which recorded oracle runs are its evidence (scripts/robotangle/import_evidence.py)
  shared/        the release's task templates (harbor_templates/topogym at release.json template_commit), verbatim:
                 the tooling rcb_topogym.py, the graders, the standard client, the sim service, the standard oracle player
  packages/      per task, the upstream texts of the graded package (task.toml, README.md, instruction.md, Dockerfiles,
                 compose files, test.sh) and its upstream runtime binding; the generator applies the RoboTangle rename
                 (user-facing names only), the image name and the evidence wording to them
  oracles/       the recorded oracle trajectories of the evidence runs (privileged deliverable; standard episode)
  tasks/robotangle-<base>-privileged/environment/instance.json + instance_assets/
                 the frozen instance, the one input kept in the task itself; copied to tests/ and to the standard
                 twin's environment/sim/
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
NOP = json.loads((HERE / "nop_records.json").read_text())   # nop runs on this release's build (very_easy / easier)
VERSION = (ROOT / "images/robotangle/VERSION").read_text().strip()
IMAGE = f"ghcr.io/mll-lab-nu/eai-robotangle:{VERSION}"
ROBOT = {"aloha": "aloha-2", "panda_robotiq": "franka-robotiq-2f85"}
ROBOT_WORDS = {"(aloha, Genesis)": "(ALOHA 2, Genesis)", "(panda_robotiq, Genesis)": "(Franka Panda + Robotiq 2F-85, Genesis)"}
DOCS = [("docs/rcb/STANDARD_MODE_2_3.md", "docs/benchmarks/robotangle.md"), ("docs/rcb/STANDARD_MODE_2_2.md", "docs/STANDARD_MODE_2_2.md"),
        ("docs/rcb/benchmarks/topogym.md", "docs/benchmarks/robotangle.md"), ("docs/rcb/PROTOCOL.md", "docs/PROTOCOL.md"),
        ("docs/rcb/TAXONOMY.md", "docs/TAXONOMY.md"), ("docs/rcb/LIMITED_MODE_PROTOCOL.md", "docs/LIMITED_MODE_PROTOCOL.md")]
IMAGE_RX = re.compile(r"(?:[\w.-]+/)+rcb-topogym:[\w.-]+")
# eai-standard/2.3 layer kept byte-identical to the release (normalize would respell its rcb-limited/2.x COMPAT entries);
# docs/benchmarks/robotangle.md, "Protocol requests"
KEEP_BYTES = ("environment/sim/rcb_limited.py",)
sha = lambda b: hashlib.sha256(b).hexdigest()  # noqa: E731


def dash(s: str) -> str:
    return s.replace("_", "-")


def text(s: str) -> str:
    """User-facing rename and paths (README, instruction, task.toml); code identifiers (topogym, rcb_topogym) stay."""
    s = re.sub(r"\btopogym-([a-z0-9-]+-i\d\d-(?:privileged|standard))\b", r"robotangle-\1", s)
    s = IMAGE_RX.sub(IMAGE, s)
    for a, b in DOCS:
        s = s.replace(a, b)
    for a, b in ROBOT_WORDS.items():
        s = s.replace(a, b)
    s = s.replace("TopoGym", "RoboTangle")
    s = re.sub(r"\bhis (?=[a-z]+(?:_[a-z0-9]+)*_v\d)", "the ", s)
    return s.replace("his qualification record", "the author's qualification record")


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
    rows.append(f"- Release: dev/jianwen `{REL['release_commit'][:9]}` (task templates `{REL['template_commit'][:9]}`), "
                f"image `{IMAGE}` (BUILD_ONLY, images/robotangle/).")
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
    s = re.sub(r'(?m)^oracle_evidence = .*\n', "", s)
    if {"privileged", "standard"} <= set(rec["evidence"]):   # a passing oracle run in both modes (docs/benchmarks/robotangle.md)
        s = re.sub(r'(?m)^oracle = .*\n', 'oracle = "full"\n', s, count=1)
    else:
        s = re.sub(r'(?m)^oracle = .*\n', f'oracle = "none"\noracle_evidence = {toml_str(evidence_text(base, rec))}\n', s, count=1)
    return s


def rewrite_readme(s: str, base: str, mode: str, rec: dict) -> str:
    s = text(s)
    s = re.sub(r"(?ms)^## Reference solution\n.*?(?=^## )", "## Reference solution\n" + ref_solution(mode, rec) + "\n\n", s)
    nop = nop_words(base, mode, rec)
    s = re.sub(r"(?ms)^(## Verification\n.*?)(?=^## )", lambda m: m.group(1).rstrip() + "\n\n" + nop + "\n\n", s)
    return s.rstrip() + "\n\n### Provenance\n" + provenance(base, rec) + "\n"


def binding(base: str, inst_dir: pathlib.Path) -> bytes:
    lock = json.loads((PKG / f"{base}-privileged" / "runtime_binding.upstream.json").read_text())
    canon = json.dumps(json.loads((inst_dir / "instance.json").read_text()), sort_keys=True, separators=(",", ":"), allow_nan=False)
    assert lock["instance_sha256"] == sha(canon.encode()), f"{base}: instance.json is not the bound instance"
    assets = {p.relative_to(inst_dir).as_posix(): sha(p.read_bytes()) for p in sorted((inst_dir / "instance_assets").rglob("*")) if p.is_file()}
    assert lock["asset_files"] == assets, f"{base}: instance_assets differ from the binding"
    lock["tooling_sha256"] = sha((SHARED / "rcb_topogym.py").read_bytes())
    lock["runtime"] = REL["runtime"]
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


def image_lines(s: str) -> str:
    s = re.sub(r"(?m)^FROM\s+" + IMAGE_RX.pattern, "FROM " + IMAGE, s)
    return re.sub(r"(?m)^(\s*image:\s*)" + IMAGE_RX.pattern, lambda m: m.group(1) + IMAGE, s)


def render(base: str, out: pathlib.Path, inst_src: pathlib.Path) -> list[pathlib.Path]:
    rec = REL["bases"][base]
    dirs = []
    for mode in ("privileged", "standard"):
        t = out / f"robotangle-{base}-{mode}"; up = PKG / f"{base}-{mode}"; dirs.append(t)
        rd = lambda n: (up / n).read_text()  # noqa: E731
        put(t / "task.toml", rewrite_toml(rd("task.toml"), base, rec).encode())
        put(t / "README.md", rewrite_readme(rd("README.md"), base, mode, rec).encode())
        put(t / "instruction.md", text(rd("instruction.md")).replace("RoboTangle", "RoboTangle (simulator package `topogym`)", 1).encode())
        for n in ("environment/Dockerfile", "environment/docker-compose.yaml", "tests/Dockerfile", "tests/docker-compose.yaml"):
            if (up / n).is_file():
                put(t / n, image_lines(rd(n)).encode())
        put(t / "tests/test.sh", (up / "tests/test.sh").read_bytes(), exe=True)
        lock = binding(base, inst_src)
        tool = (SHARED / "rcb_topogym.py").read_bytes()
        if mode == "privileged":
            for d in ("environment", "tests"):
                copy_tree(inst_src / "instance_assets", t / d / "instance_assets")
                put(t / d / "instance.json", (inst_src / "instance.json").read_bytes())
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
            for n in ("rcb_client.py", "rcb1.py", "client-requirements.txt"):
                put(t / "environment" / n, (SHARED / "standard" / n).read_bytes())
            for n in ("server.py", "rcb_limited.py", "rcb1.py", "replay.py", "finalize.sh", "run.sh"):
                put(t / "environment/sim" / n, (SHARED / "standard/sim" / n).read_bytes())
            copy_tree(inst_src / "instance_assets", t / "environment/sim/instance_assets")
            put(t / "environment/sim/instance.json", (inst_src / "instance.json").read_bytes())
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
        keep = {k: (t / k).read_bytes() for k in KEEP_BYTES if (t / k).is_file()}
        TC.normalize(t)
        for k, b in keep.items():
            (t / k).write_bytes(b)
    return dirs


def snapshot(d: pathlib.Path) -> dict:
    return {p.relative_to(d).as_posix(): (p.read_bytes(), os.stat(p).st_mode & 0o777) for p in sorted(d.rglob("*")) if p.is_file()}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true"); ap.add_argument("--list", action="store_true")
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
            inst = TASKS / f"robotangle-{b}-privileged" / "environment"
            if not (inst / "instance.json").is_file():
                bad.append(f"{b}: no frozen instance at {inst}"); continue
            staged = tmp / "in" / b
            copy_tree(inst / "instance_assets", staged / "instance_assets"); put(staged / "instance.json", (inst / "instance.json").read_bytes())
            for t in render(b, tmp / "out", staged):
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
