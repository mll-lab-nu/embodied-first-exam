"""Package one prepared gathered tier/seed without changing its acceptance scope."""
import argparse
import json
from pathlib import Path
import shutil

from topogym.assets.library import RESOURCE_ROOT
from topogym.tasks.blanket_flatten.gathered import REVISION, TWIST_ANGLES, seeded_folder
from topogym.utils.io import make_asset_tree_readable, sha256_file, write_json_atomic
from topogym.world.initial_state import load_numeric_archive


def install(candidate):
    candidate = Path(candidate).resolve()
    report = json.loads((candidate/"report.json").read_text())
    tier = report["config"]["variation_id"]
    if tier not in TWIST_ANGLES or report["status"] not in {"passed", "scene_layout_ready"}:
        raise ValueError("Only completed, explicitly tiered candidates can be installed")
    if report["config"]["enable_rgb"] is not True:
        raise ValueError("A physics-only diagnostic cannot replace the standard RGB scene resource")
    manifest = candidate/"state/manifest.json"
    _, metadata = load_numeric_archive(manifest)
    from topogym.world.initial_state import validate_initial_state_qualification
    validate_initial_state_qualification(metadata["qualification"], "scene_layout")
    profile = metadata["identity"]["parameters"]["gathered_profile"]
    if profile != report["profile"] or profile["twist_angle_deg"] != TWIST_ANGLES[tier]:
        raise ValueError("Candidate profile does not match its tier")
    seed = metadata["identity"]["seed"]
    # A seeded scene variation (prepare --seeded) is frozen apart from the tier archive of the same seed.
    scope = f"{tier}/{seeded_folder()}/seed_{seed}" if report.get("scene_variation") else f"{tier}/seed_{seed}"
    revision = REVISION
    if metadata["backend"]["codec"] == "rigid_pbd_numeric_v2":
        from topogym.world.physics.initial_state_compatibility import ARCHIVE_REVISION, resource_profile
        revision = ARCHIVE_REVISION
        scope = f"{resource_profile(metadata['backend'])}/{scope}"
    relative = Path("variations/blanket_flatten")/revision/scope
    destination = RESOURCE_ROOT/relative
    catalog_path = RESOURCE_ROOT/"catalog.json"
    catalog = json.loads(catalog_path.read_text())
    if destination.exists():
        raise FileExistsError(f"Refusing to replace a frozen scene: {destination}")
    for name in ("manifest.json", "arrays.npz"):
        key = f"blanket_flatten/{revision}/{scope}/{name}"
        if key in catalog["resources"]:
            raise ValueError(f"Resource already registered: {key}")
    shutil.copytree(candidate/"state", destination)
    make_asset_tree_readable(destination)
    for parent in destination.parents:
        if parent == RESOURCE_ROOT or not parent.is_relative_to(RESOURCE_ROOT):
            break
        parent.chmod(0o755)
    for name in ("manifest.json", "arrays.npz"):
        key = f"blanket_flatten/{revision}/{scope}/{name}"
        catalog["resources"][key] = dict(path=str(relative/name), sha256=sha256_file(destination/name),
            source=f"prepared {REVISION} {tier}, seed {seed}{', seeded variation' if report.get('scene_variation') else ''}; "
                   f"scope={metadata['qualification'].get('scope')}",
            license=None)
    write_json_atomic(catalog_path, catalog, mode=0o644)
    return destination/"manifest.json"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    args = parser.parse_args()
    print(install(args.candidate))
