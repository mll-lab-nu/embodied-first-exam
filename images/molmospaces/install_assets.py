#!/usr/bin/env python3
"""The upstream assets of the frozen MolmoSpaces instances, and nothing else (images/molmospaces/).

    python install_assets.py install <instances dir>   # prepare_assets.sh, in the base image with network
    python install_assets.py verify  <instances dir>   # the image build
    python install_assets.py attribution <instances dir> <ATTRIBUTION.md>   # the image build: the shipped assets' licences

install:
1. build every instance once with upstream's own resource manager: its scene post-setup and installers fetch the scenes,
   objects and robots the episodes use (and, with each Objaverse object, its grasps);
2. trace: in a fresh process with the run-time setup (rcb_molmospaces.boot(), no installs), build every instance, run
   control steps and render every camera, under strace: the asset files that process opens are the ones kept;
3. prune: every other file under the asset and cache directories is deleted (grasps, unused objects and scenes);
4. verify, as below, and the state after the probe steps must equal the one traced before pruning.
verify: in a fresh process, every instance; its t = 0 state hash must equal the one recorded in the instance.
attribution: the licence and attribution of every asset the instances load, from upstream's own records
(molmo_spaces.utils.license_utils); it fails if one forbids commercial use (make_instances.py never selects such an
episode, so the image stays publishable).
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

STEPS = 5  # control steps per instance in the traced run


def exercise(inst_dir: Path) -> dict:
    """Build every instance with the run-time setup, step and render; {instance file: [t0 sha, sha after the steps]}."""
    import rcb_molmospaces as M

    out = {}
    for p in sorted(inst_dir.glob("*.json")):
        ep = M.Episode(p)
        t0 = ep.state_sha()
        ep.success()
        for cam in ep.cameras:
            ep.render(cam)
            ep.render_depth(cam)
            ep.camera_info(cam)
        hold = ep.hold_row()
        for _ in range(STEPS):
            ep.step(hold)
        ep.proprio()
        ep.kinematics({"op": "fk", "q": ep.proprio()["joint_pos"]})
        ep.success()
        out[p.name] = [t0, ep.state_sha()]
        ep.close()
    return out


def opened_files(trace: Path, roots: list[Path]) -> set[Path]:
    """The files the traced process opened, as `strace -y` resolves them (the returned descriptor's path: MuJoCo opens
    meshes relative to a directory descriptor, so the path argument alone is not enough)."""
    keep = set()
    pat = re.compile(r"openat.*= \d+<([^>]+)>$")  # whole calls, and "<... openat resumed>" halves
    for line in trace.read_text(errors="replace").splitlines():
        m = pat.search(line)
        if m:
            real = Path(os.path.realpath(m.group(1)))
            if real.is_file() and any(real.is_relative_to(r) for r in roots):
                keep.add(real)
    return keep


def prune(roots: list[Path], keep: set[Path]) -> tuple[int, int]:
    """Delete every regular file not in `keep`, then the symlinks left dangling and the directories left empty."""
    files = [p for r in roots for p in r.rglob("*") if p.is_file() and not p.is_symlink()]
    gone = [p for p in files if p.resolve() not in keep]
    for p in gone:
        p.unlink()
    changed = True
    while changed:  # a link into a directory that only empties later goes in a later pass
        changed = False
        for p in sorted((q for r in roots for q in r.rglob("*")), key=lambda q: -len(q.parts)):
            if p.is_symlink() and not p.exists():
                p.unlink()
                changed = True
            elif p.is_dir() and not p.is_symlink() and not any(p.iterdir()):
                p.rmdir()
                changed = True
    return len(files) - len(gone), len(gone)


def run(inst_dir: Path, strace: Path | None = None) -> dict:
    cmd = [sys.executable, __file__, "exercise", str(inst_dir)]
    if strace:
        cmd = ["strace", "-f", "-qq", "-y", "-e", "trace=openat", "-o", str(strace), *cmd]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, check=True)
    return json.loads(res.stdout.strip().splitlines()[-1])


def check(inst_dir: Path, got: dict, before: dict | None = None) -> None:
    bad = []
    for name, (t0, end) in sorted(got.items()):
        want = json.loads((inst_dir / name).read_text())["t0"]["state_sha"]
        if t0 != want or (before is not None and [t0, end] != before[name]):
            bad.append(
                f"{name}: t0 {t0} (instance {want}); after {STEPS} steps {end}"
                + (f" (before pruning {before[name][1]})" if before else "")
            )
    if bad:
        raise SystemExit("[install_assets] state differs:\n  " + "\n  ".join(bad))
    print(f"[install_assets] {len(got)} instances: t = 0 state hashes as recorded", flush=True)


def attribution(inst_dir: Path) -> str:
    import rcb_molmospaces as M

    M.boot()
    from molmo_spaces.utils.license_utils import DEFAULT_LICENSE, resolve_license
    from molmo_spaces.utils.object_metadata import ObjectMeta

    used, robots = {}, set()
    for p in sorted(inst_dir.glob("*.json")):
        ep = M.Episode(p)
        m = ep.env.current_model
        names = [m.body(b).name for b in range(m.nbody)] + [m.mesh(i).name for i in range(m.nmesh)]
        for uid in {u for n in names for u in re.findall(r"[0-9a-f]{32}", n)}:  # as make_instances.py finds them
            if (ObjectMeta.annotation(uid) or {}).get("isObjaverse"):
                used.setdefault(uid, set()).add(ep.inst["family"])
        robots |= {"rby1"} if "base" in ep.groups else {"franka_fr3", "robotiq_2f85"}
        ep.close()
    lines = [
        "# Licences of the assets in this image",
        "",
        "Generated by images/molmospaces/install_assets.py from upstream MolmoSpaces' own licence records",
        "(molmo_spaces.utils.license_utils). Code: MolmoSpaces (molmo-spaces 0.2.9), Apache-2.0.",
        f"Scenes, AI2-THOR objects and object metadata: {DEFAULT_LICENSE['creator_name']}, {DEFAULT_LICENSE['license']}.",
        "",
        "## Robots",
        *(
            f"- {r}: {(lic := resolve_license('robots', r, r))['attribution']}, {lic['license']} ({lic['uri']})"
            for r in sorted(robots)
        ),
        "",
        "## Objaverse objects",
        "The Objaverse subset is licensed under ODC-BY 1.0; each object is licensed by its creator as below and was",
        "modified by Ai2 (mesh decimation, convex colliders, baked visual effects).",
        "",
        "| object | category | licence | attribution | source | tasks |",
        "|---|---|---|---|---|---|",
    ]
    restricted = []
    for uid in sorted(used):
        lic = resolve_license("objects", "objaverse", uid)
        if lic.get("commercial_use") is False:
            restricted.append(uid)
        cat = ObjectMeta.annotation(uid).get("category")
        tasks = ", ".join(sorted(used[uid]))
        lines.append(f"| {uid} | {cat} | {lic['license']} | {lic['attribution']} | {lic['uri']} | {tasks} |")
    if restricted:
        raise SystemExit(f"[install_assets] non-commercial assets in the instances: {', '.join(restricted)}")
    return "\n".join(lines) + "\n"


def main() -> int:
    cmd, inst_dir = sys.argv[1], Path(sys.argv[2])
    if cmd == "exercise":  # the child process of the steps below
        print(json.dumps(exercise(inst_dir)))
        return 0
    if cmd == "verify":
        check(inst_dir, run(inst_dir))
        return 0
    if cmd == "attribution":  # to a file: upstream prints to stdout while it loads
        Path(sys.argv[3]).write_text(attribution(inst_dir))
        return 0
    import rcb_molmospaces as M

    M.boot(install=True)
    for p in sorted(inst_dir.glob("*.json")):  # 1. install
        M.install(p)
        M.Episode(p).close()
    roots = [Path(os.environ["MLSPACES_ASSETS_DIR"]).resolve(), Path(os.environ["MLSPACES_CACHE_DIR"]).resolve()]
    trace = Path("/tmp/assets.strace")
    before = run(inst_dir, strace=trace)  # 2. trace
    kept, removed = prune(roots, opened_files(trace, roots))  # 3. prune
    trace.unlink()
    print(f"[install_assets] kept {kept} asset files, removed {removed}", flush=True)
    check(inst_dir, run(inst_dir), before)  # 4. verify
    return 0


if __name__ == "__main__":
    sys.exit(main())
