#!/usr/bin/env python3
"""One-off importer (run by the author, never by CI): turns the graded TopoGym packages and oracle runs into the
generator inputs of RoboTangle. Inputs:
  --lab-inputs DIR   a read-only copy of the graded candidate packages and oracle-run artifacts (the paths below
                     the evidence root on the lab host), as listed in --resolve
  --resolve FILE     per task base: the package that holds its frozen instance and the passing oracle run per mode
  --repo DIR --rev REV   the git checkout and the dev/jianwen release commit whose templates the tasks use
Outputs (under scripts/robotangle/ and tasks/): shared/ (the release templates, verbatim), packages/ (the upstream
per-task texts, verbatim), oracles/ (the recorded oracle trajectories, verbatim), release.json, and the frozen
instance of each base in tasks/robotangle-<base>-privileged/environment/. Python standard library only."""
import argparse, hashlib, json, os, pathlib, shutil, subprocess, zipfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TEMPLATES = {  # shared/<path> <- harbor_templates/topogym/<path> at the release commit
    "rcb_topogym.py": "common/rcb_topogym.py",
    "privileged/grade.py": "unlimited/tests/grade.py",
    "standard/grade.py": "limited/tests/grade.py",
    "standard/rcb_client.py": "limited/environment/rcb_client.py",
    "standard/rcb1.py": "limited/environment/rcb1.py",
    "standard/client-requirements.txt": "limited/environment/client-requirements.txt",
    "standard/sim/server.py": "limited/environment/sim/server.py",
    "standard/sim/rcb_limited.py": "limited/environment/sim/rcb_limited.py",
    "standard/sim/rcb1.py": "limited/environment/sim/rcb1.py",
    "standard/sim/replay.py": "limited/environment/sim/replay.py",
    "standard/sim/finalize.sh": "limited/environment/sim/finalize.sh",
    "standard/sim/run.sh": "limited/environment/sim/run.sh",
    "standard/solution/oracle_replay.py": "limited/solution/oracle_replay.py",
    "standard/solution/solve.sh": "limited/solution/solve.sh",
}
TEXTS = ("task.toml", "README.md", "instruction.md", "environment/Dockerfile", "environment/docker-compose.yaml",
         "tests/Dockerfile", "tests/test.sh", "tests/docker-compose.yaml")
sha = lambda b: hashlib.sha256(b).hexdigest()  # noqa: E731


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lab-inputs", type=pathlib.Path, required=True)
    ap.add_argument("--resolve", type=pathlib.Path, required=True)
    ap.add_argument("--repo", type=pathlib.Path, required=True)
    ap.add_argument("--rev", required=True)
    ap.add_argument("--exclude", nargs="*", default=[], help="task bases not shipped in this release")
    a = ap.parse_args()
    git = lambda *x: subprocess.run(["git", "-C", str(a.repo), *x], check=True, capture_output=True).stdout  # noqa: E731
    rev = git("rev-parse", a.rev).decode().strip()
    shared = HERE / "shared"
    for dst, src in TEMPLATES.items():
        p = shared / dst; p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(git("show", f"{rev}:harbor_templates/topogym/{src}"))
    res = json.loads(a.resolve.read_text()); L = a.lab_inputs
    release = json.loads((HERE / "release.json").read_text()) if (HERE / "release.json").exists() else {}
    bases = {}
    for base, rec in res.items():
        if base in a.exclude or not rec.get("instance_root"):
            continue
        ir = L / rec["instance_root"]
        for mode in ("privileged", "standard"):
            src = ir / f"topogym-{base}-{mode}"
            dst = HERE / "packages" / f"{base}-{mode}"
            for t in TEXTS:
                if (src / t).is_file():
                    (dst / t).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src / t, dst / t)
            if mode == "privileged":
                shutil.copy2(src / "environment/runtime_binding.json", dst / "runtime_binding.upstream.json")
                inst = ROOT / "tasks" / f"robotangle-{base}-privileged" / "environment"
                inst.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src / "environment/instance.json", inst / "instance.json")
                if (inst / "instance_assets").exists():
                    shutil.rmtree(inst / "instance_assets")
                shutil.copytree(src / "environment/instance_assets", inst / "instance_assets")
            for sim in ("environment/sim/finalize.sh", "environment/sim/run.sh"):   # template files: must equal the release's
                if (src / sim).is_file() and (src / sim).read_bytes() != (shared / "standard/sim" / pathlib.Path(sim).name).read_bytes():
                    print(f"NOTE {base}-{mode}: {sim} differs from the release template (the template is used)")
        ev = {}
        for mode, e in rec["evidence"].items():
            o = HERE / "oracles" / base; o.mkdir(parents=True, exist_ok=True)
            if e.get("trajectory"):
                data = (L / e["trajectory"]).read_bytes()
                assert sha(data) == e["trajectory_sha256"], (base, mode)
                (o / f"{mode}.npz").write_bytes(data)
            ev[mode] = {k: e.get(k) for k in ("release", "source", "tooling", "attempt", "trajectory_sha256")}
            ev[mode]["success"] = (e.get("reward") or {}).get("success")
            ev[mode]["deterministic"] = (e.get("reward") or {}).get("deterministic")
        bases[base] = dict(family=rec["family"], tier=rec["tier"], instance_package=rec["instance_root"],
                           creation_source=rec.get("creation_source"), evidence=ev)
    release.setdefault("bases", {}).update(bases)
    release["template_commit"] = rev
    (HERE / "release.json").write_text(json.dumps(release, indent=1, sort_keys=True) + "\n")
    print(f"{len(bases)} bases imported from {a.lab_inputs} (templates at {rev[:9]})")


if __name__ == "__main__":
    main()
