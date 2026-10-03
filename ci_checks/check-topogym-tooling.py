#!/usr/bin/env python3
"""Check immutable historical packages and explicit public tooling generations."""
import hashlib
import json
import re
from pathlib import Path
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
SHARED = ("environment/rcb_client.py", "environment/rcb1.py", "environment/sim/server.py",
          "environment/sim/finalize.sh", "environment/sim/run.sh", "environment/sim/rcb1.py",
          "environment/sim/rcb_limited.py", "environment/sim/replay.py", "tests/grade.py")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def current_files(mode):
    template = ROOT / "harbor_templates/topogym" / mode
    expected = {rel: sha(template / rel) for rel in SHARED if (template / rel).is_file()}
    tool = sha(ROOT / "harbor_templates/topogym/common/rcb_topogym.py")
    paths = (("environment/rcb_topogym.py", "tests/rcb_topogym.py") if mode == "unlimited"
             else ("environment/sim/rcb_topogym.py",))
    expected.update({p: tool for p in paths})
    return expected


def frozen_state_identity(task):
    """A packaged blanket PBD initial state restores only while the topogym sources in its backend identity are unchanged
    (topogym/world/physics/pbd_initial_state.py); an edit there needs new states, not a silent refusal at run time."""
    errors = []
    for manifest in sorted(task.glob("**/instance_assets/**/manifest.json")):
        backend = json.loads(manifest.read_text()).get("metadata", {}).get("backend", {})
        wanted = {"state_codec_sha256": "topogym/world/state.py",
                  "table_friction_sha256": "topogym/world/physics/pbd_table_friction.py"}
        if backend.get("codec") == "rigid_pbd_numeric_v1":
            wanted["world_sha256"] = "topogym/world/genesis_world.py"
        for key, rel in wanted.items():
            if key in backend and backend[key] != sha(ROOT / rel):
                errors.append(f"{task.name}/{manifest.relative_to(task)}: {key} != sha256({rel}); the frozen state would not restore")
    return errors


def current_image():
    sys.path.insert(0, str(ROOT / "scripts"))
    from cuda_profiles import image_tag
    return image_tag(ROOT, "cu128")


def image_references(task, *, include_custom=False):
    """The simulator image of every container of a current-tooling dir (the privileged environment and verifier, the
    standard sidecar), which must be the image of images/topogym/VERSION: a dir rendered against an older image keeps
    working until its instance needs a newer library (tooling v9's ipc_options)."""
    refs = []
    dockerfiles = () if include_custom and task.name.endswith(("-standard", "-limited")) else ("environment/Dockerfile", "tests/Dockerfile")
    image_pattern = r"\S+" if include_custom else r"\S*rcb-topogym\S*"
    for rel in dockerfiles:
        path = task / rel
        if path.is_file():
            refs += [(rel, m) for m in re.findall(rf"^FROM\s+({image_pattern})", path.read_text(), re.M)]
    compose = task / "environment/docker-compose.yaml"
    if compose.is_file():
        refs += [("environment/docker-compose.yaml", m) for m in re.findall(rf"image:\s*({image_pattern})", compose.read_text())]
    return refs


def check(tasks):
    frozen = json.loads((ROOT / "ci_checks/topogym_tooling_versions.json").read_text())
    errors, count = [], 0
    for task in sorted(tasks.iterdir()):
        if not task.name.startswith("topogym-") or not (task / "task.toml").is_file():
            continue
        count += 1
        meta = tomllib.loads((task / "task.toml").read_text()).get("metadata", {})
        version = meta.get("tooling_version")
        mode = "limited" if task.name.endswith(("-limited", "-standard")) else "unlimited"
        if version == "13":
            if not task.name.endswith(("-privileged", "-standard")):
                errors.append(f"{task.name}: tooling v13 requires protocol v1.0 task names")
            expected = current_files(mode)
            image = current_image()
            errors.extend(f"{task.name}/{rel}: image {ref} != {image} (images/topogym/VERSION)"
                          for rel, ref in image_references(task) if ref != image)
        elif version in ("3", "4", "5", "6", "7", "8", "9", "10", "11", "12"):
            expected = frozen["v" + version][mode]
            # Independent branches reused version numbers. Identify the local
            # lineage by its tool hash, then validate EVERY shared file.
            image_key = version
            local_keys = {"6": ("v6_local_a01",),
                          "11": ("v11_local_grasp", "v11_local_lock")}.get(version, ())
            for local_key in local_keys:
                local = frozen[local_key][mode]
                rel = "environment/sim/rcb_topogym.py" if mode == "limited" else "environment/rcb_topogym.py"
                if (task / rel).is_file() and sha(task / rel) == local[rel]:
                    expected = local
                    image_key = local_key if local_key in frozen.get("version_images", {}) else version
                    break
            image = frozen.get("version_images", {}).get(image_key)
            pinned = frozen.get("package_images", {}).get(task.name)
            if pinned:
                actual_images = dict(image_references(task, include_custom=True))
                if actual_images != pinned:
                    errors.append(f"{task.name}: image references {actual_images} != frozen package images {pinned}")
            elif image:
                errors.extend(f"{task.name}/{rel}: image {ref} != frozen tooling {version} image {image}"
                              for rel, ref in image_references(task) if ref != image)
        elif "tooling_version" in meta:
            errors.append(f"{task.name}: unknown tooling_version {version!r}")
            continue
        elif task.name in frozen["packages"]:
            expected = frozen["generations"][frozen["packages"][task.name]]
        else:
            errors.append(f"{task.name}: unversioned package has no frozen inventory")
            continue
        if version is not None:
            errors.extend(frozen_state_identity(task))
        for rel, wanted in expected.items():
            path = task / rel
            if not path.is_file() or sha(path) != wanted:
                errors.append(f"{task.name}/{rel}: missing or differs from tooling {version or 'frozen inventory'}")
        actual = {p.relative_to(task).as_posix() for p in task.rglob("*") if p.is_file()
                  and not {"results", "__pycache__"}.intersection(p.relative_to(task).parts)
                  and (p.name == "rcb_topogym.py" or p.relative_to(task).as_posix() in SHARED)}
        for rel in sorted(actual - expected.keys()):
            errors.append(f"{task.name}/{rel}: unexpected tooling copy")
    return count, errors


if __name__ == "__main__":
    count, errors = check(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "tasks")
    for error in errors:
        print("FAIL " + error)
    if not errors:
        print(f"ok TopoGym tooling: {count} packages; frozen inputs and public v13 checked")
    raise SystemExit(bool(errors))
