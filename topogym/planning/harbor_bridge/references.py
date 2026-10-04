"""Manager-side selection of existing private reference data, never public scene inputs."""
import json
from pathlib import Path

from .contracts import BridgeError, digest


def reference_data(root, family, tier, seed):
    root = Path(root)
    if tier not in {"easy", "medium", "hard"}:
        raise BridgeError("These adapters cover only easy / medium / hard")
    files, includes = {}, []
    prefix = "topogym/planning/harbor_bridge/reference_data/"

    def add(name, source, expected=None):
        source = Path(source)
        if not source.is_file() or expected is not None and digest(source) != expected:
            raise BridgeError(f"Missing or changed reference data: {source}")
        files[prefix + family + "/" + tier + "/" + name] = str(source.resolve())

    if family == "cast_keyhole":
        includes = [f"topogym/planning/cast_keyhole/references/F{i}.json" for i in (1, 2, 3)]
    if family in {"fiber_bundling", "horseshoe_ring", "hedgehog_in_cage", "interlocked_claws", "rope_threading"} and seed != 0:
        raise BridgeError(f"Selected {family} reference data currently bind seed 0")
    if family == "fiber_bundling":
        name = {"easy": "easy_02", "medium": "medium_full_01", "hard": "hard_full_01"}[tier]
        add("selection.json", root / "solvability_proof/fiber_bundling/2026-10-03/evidence/runs" / name / "qualification/selection.json")
    elif family == "horseshoe_ring":
        index = json.loads((root / "solvability_proof/horseshoe_ring/recipes.json").read_text())
        path = root / index[tier]
        recipe = json.loads(path.read_text())
        add("recipe.json", path)
        for name, item in recipe["selection"][0]["parameters"].items():
            add(name + ".json", path.parent / item["path"], item["sha256"])
    elif family == "hedgehog_in_cage" and tier != "medium":
        path = {"easy": "2026-09-30_easy/evidence/runs/easy_qualified_native_01",
                "hard": "2026-10-03_hard_s5_post/evidence/runs/native_03"}[tier]
        add("pickup.json", root / "solvability_proof/hedgehog_in_cage" / path / "submitted_pickup.json")
    elif family == "interlocked_claws":
        add("witness.json", root / "solvability_proof/interlocked_claws/2026-10-03/evidence" / tier / "run/submitted_witness.json")
        includes = ["topogym/planning/interlocked_claws/reference_routes.json"]
    elif family == "rope_threading":
        base = "topogym/planning/rope_threading/reference_relays/"
        includes = [base + n for n in ("manifest.json", f"{tier}_seed{seed}.npz", f"{tier}_evidence.json")]
    return files, includes
