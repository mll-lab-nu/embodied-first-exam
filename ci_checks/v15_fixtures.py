"""Synthetic bound packages for scheduler/identity tests. Never physics evidence."""
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]


def bound_task(path, source=ROOT, *, mode="privileged", row=None, reference="example:1"):
    from topogym_versions import identity, release, stamp_task
    from topogym.planning.harbor_bridge.binding import lock_for_task
    path, source = Path(path), Path(source)
    baseline = ROOT / f"tasks/topogym-cast-coil-easy-i00-{mode}"
    shutil.copytree(baseline, path, dirs_exist_ok=True)
    from topogym_versions import shared_files
    template_mode = "limited" if mode == "standard" else "unlimited"
    for relative in shared_files(source, template_mode):
        if relative.endswith("rcb_topogym.py"):
            continue
        dest = path / relative; dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / "harbor_templates/topogym" / template_mode / relative, dest)
    active = release(source)["tooling_version"]       # the active release's tooling (v15 when this fixture was written)
    text = (path / "task.toml").read_text().replace('tooling_version = "14"', f'tooling_version = "{active}"')
    (path / "task.toml").write_text(text.replace(baseline.name, path.name))
    actor = path / ("environment/sim" if mode == "standard" else "environment")
    for folder in ((actor,) if mode == "standard" else (actor, path / "tests")):
        shutil.copy2(source / "harbor_templates/topogym/common/rcb_topogym.py", folder / "rcb_topogym.py")
        if row:
            inst = json.loads((folder / "instance.json").read_text())
            inst.update(variation_id=row["variation_id"], resolved_variation_id=row["resolved_variation_id"],
                        seed=row["scene_seed"], simulator=row["simulator"])
            (folder / "instance.json").write_text(json.dumps(inst))
    (path / "tests/Dockerfile").write_text(f"FROM {reference}\n")
    if mode == "standard":
        (path / "environment/docker-compose.yaml").write_text(f"services:\n  sim:\n    image: {reference}\n")
    else:
        (path / "environment/Dockerfile").write_text(f"FROM {reference}\n")
    runtime = dict(source=identity(source)["source"])
    lock = lock_for_task(path, dict(reference=reference, id="sha256:" + "0" * 64, repo_digests=[]), runtime)
    for folder in (actor, path / "tests"):
        (folder / "runtime_binding.json").write_text(json.dumps(lock))
    stamp_task(path, source)
    return path
