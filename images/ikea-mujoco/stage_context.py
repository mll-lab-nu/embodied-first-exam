#!/usr/bin/env python3
"""Stage the build context of the eai-ikea-mujoco image (images/ikea-mujoco/) from an IKEA MuJoCo source tree.

usage: python3 images/ikea-mujoco/stage_context.py <source tree> [--out images/ikea-mujoco/context] [--pin]
  <source tree>  a tree with scenes/<task>/: the scene code of images/ikea-mujoco/scenes/<task>/ plus its meshes,
                 scenes/<task>/assets/ (not in git: about 40 MB per task; images/ikea-mujoco/fetch_image_context.sh
                 downloads them from the pinned Hugging Face revision of assets.json and runs this script)
  --pin          (re)write images/ikea-mujoco/assets.json from the source instead of checking against it

Per task (assets.json "tasks") it copies what the scene loads at run time: scene.py, scene.xml, task.json, layout.json,
sw_cutover.json (where present), the scene's own Python modules (ikea_runtime.py, success.py, the mechanism modules;
not the `_*.py` dev scripts) and assets/. Development material (check/, mech_test/, dev/, videos, the direct-force
references) stays out. Every staged file must match its sha256 in assets.json; the image copies context/scenes/ to
/opt/ikea/scenes/ and the pins ("note", "tasks" of assets.json: IMAGE_KEYS) next to it. Python standard library only.
"""
from __future__ import annotations
import argparse, hashlib, json, pathlib, re, shutil, sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PINS = HERE / "assets.json"
TOP = ("scene.py", "scene.xml", "task.json", "layout.json", "sw_cutover.json")
IMAGE_KEYS = ("note", "tasks")   # the part of assets.json the image carries; the dataset pin (repo, revision) stays out


def sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def select(scene: pathlib.Path) -> list[pathlib.Path]:
    files = [scene / n for n in TOP if (scene / n).is_file()]
    files += sorted(p for p in scene.glob("*.py") if not p.name.startswith("_") and p.name not in TOP)
    files += sorted(p for p in (scene / "assets").rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    return files


# H.2 (PROTOCOL v2.0): nothing the agent can read points at upstream material. The scene texts (code, XML, JSON) are
# refused when they name the upstream repositories, their paths, or a URL; provenance lives in provenance.json.
POINTERS = re.compile(r"astra|robobench|roboprobe|untrusted/|assembly27|https?://|controller\.py|mechanics/|diagnostics/|"
                      r"grader/|experiments/|\.usda?\b", re.I)


def pointers(scene: pathlib.Path) -> list[str]:
    bad = []
    for p in select(scene):
        if p.suffix in (".py", ".json", ".xml"):
            for i, line in enumerate(p.read_text(errors="replace").splitlines(), 1):
                if POINTERS.search(line):
                    bad.append(f"{scene.name}/{p.relative_to(scene)}:{i}: {line.strip()[:100]}")
    return bad


def digest(files: dict) -> str:
    return hashlib.sha256("".join(f"{k} {files[k]}\n" for k in sorted(files)).encode()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", type=pathlib.Path)
    ap.add_argument("--out", type=pathlib.Path, default=ROOT / "images/ikea-mujoco/context")
    ap.add_argument("--pin", action="store_true")
    ap.add_argument("--tasks", default=None, help="comma-separated tasks for --pin (default: those in assets.json)")
    a = ap.parse_args()
    pins = json.loads(PINS.read_text()) if PINS.is_file() else {"tasks": {}}
    tasks = a.tasks.split(",") if a.tasks else sorted(pins["tasks"])
    if a.pin:
        pins = {**{k: v for k, v in pins.items() if k not in IMAGE_KEYS},
                "note": "sha256 of every file of the eai-ikea-mujoco build context (images/ikea-mujoco/stage_context.py)",
                "tasks": {}}
        for t in tasks:
            scene = a.source / "scenes" / t
            files = {str(p.relative_to(scene)): sha(p) for p in select(scene)}
            pins["tasks"][t] = {"digest": digest(files), "files": files}
        PINS.write_text(json.dumps(pins, indent=1, sort_keys=True) + "\n")
        print(f"pinned {len(tasks)} tasks in {PINS.relative_to(ROOT)}")
    if a.out.exists():
        shutil.rmtree(a.out)
    bad = []
    for t in tasks:
        scene = a.source / "scenes" / t
        want = pins["tasks"][t]["files"]
        bad += pointers(scene)
        got = {str(p.relative_to(scene)): p for p in select(scene)}
        if set(got) != set(want):
            bad.append(f"{t}: file set differs ({sorted(set(got) ^ set(want))[:5]})")
            continue
        for rel, p in got.items():
            if sha(p) != want[rel]:
                bad.append(f"{t}/{rel}: sha256 differs")
                continue
            dst = a.out / "scenes" / t / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, dst)
    if bad:
        print("context NOT staged:\n  " + "\n  ".join(bad[:20]), file=sys.stderr)
        shutil.rmtree(a.out, ignore_errors=True)
        return 1
    (a.out / "assets.json").write_text(json.dumps({k: pins[k] for k in IMAGE_KEYS}, indent=1, sort_keys=True) + "\n")
    shutil.copyfile(ROOT / "images/ikea-mujoco/mujoco-3.14.0-epa/bytepatch_libmujoco.py", a.out / "bytepatch_libmujoco.py")
    print(f"staged {len(tasks)} scenes in {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
