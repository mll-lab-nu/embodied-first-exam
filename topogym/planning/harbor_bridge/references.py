"""Manager-side selection of existing private reference data, never public scene inputs."""
import json
from pathlib import Path

from .contracts import BridgeError, digest, member


def reference_data(root, family, tier, seed):
    root = Path(root)
    from .catalog import TIERS, BELOW_EASY_FAMILIES
    if tier not in TIERS:
        raise BridgeError("Unknown oracle difficulty tier")
    below_easy = tier in {"very_easy", "easier"}
    if below_easy:
        if family not in BELOW_EASY_FAMILIES:
            raise BridgeError(f"No complete robot oracle adapter for {family}/{tier}")
        if seed != 0:
            raise BridgeError("Below-easy reference recipes currently bind seed 0")
        # The shared dispatcher imports all seven controllers. Include their
        # authored static routes; no original-tier witness is substituted.
        includes = ["topogym/planning/interlocked_claws/easier_reference_route.json"]
        for name in includes:
            member(root, name)
        if family != "fiber_bundling":
            return {}, includes
    files, includes = {}, []
    prefix = "topogym/planning/harbor_bridge/reference_data/"
    base = root / prefix

    def add(name, expected=None):
        relative = family + "/" + tier + "/" + name
        source = member(base, relative)
        manifest = json.loads(member(base, "manifest.json").read_text())
        record = manifest["files"][relative]
        actual = digest(source)
        if (manifest.get("schema_version") != 1 or actual != record["sha256"]
                or source.stat().st_size != record["bytes"]
                or expected is not None and actual != expected):
            raise BridgeError(f"Missing or changed reference data: {source}")
        files[prefix + relative] = str(source)
        return source

    if below_easy:
        add("selection.json")
        includes = ["topogym/planning/interlocked_claws/easier_reference_route.json"]
        return files, includes
    if family == "cast_keyhole":
        includes = [f"topogym/planning/cast_keyhole/references/F{i}.json" for i in (1, 2, 3)]
    if family in {"buzz_wire_3d", "fiber_bundling", "horseshoe_ring", "hedgehog_in_cage", "interlocked_claws", "rope_threading"} and seed != 0:
        raise BridgeError(f"Selected {family} reference data currently bind seed 0")
    if family == "fiber_bundling":
        add("selection.json")
    elif family == "buzz_wire_3d":
        recipe = json.loads(add("recipe.json").read_text())
        expected = "selection.json" if tier == "easy" else "policy_actions.json"
        if recipe.get("variation") != tier or recipe.get("seed") != seed or recipe["input"]["file"] != expected:
            raise BridgeError("Buzz reference recipe differs from the selected tier/seed")
        add(expected, recipe["input"]["sha256"])
        if tier == "medium":
            # Retain the historical staged guide for explicit development recipes;
            # the default full medium oracle uses the complete action sequence.
            add("medium_traverse_guide.json", "4511df68f53ded79077a12998ddfe76f1cbf65f6ac552b412fbdefa4bf16cd0f")
    elif family == "horseshoe_ring":
        path = add("recipe.json")
        recipe = json.loads(path.read_text())
        for name, item in recipe["selection"][0]["parameters"].items():
            add(name + ".json", item["sha256"])
    elif family == "hedgehog_in_cage" and tier != "medium":
        add("pickup.json")
        includes = ["topogym/planning/hedgehog_in_cage/reference_routes.json"]
    elif family == "interlocked_claws":
        add("witness.json")
        includes = ["topogym/planning/interlocked_claws/reference_routes.json"]
    elif family == "rope_threading":
        relay_base = "topogym/planning/rope_threading/reference_relays/"
        includes = [relay_base + n for n in ("manifest.json", f"{tier}_seed{seed}.npz", f"{tier}_evidence.json")]
        includes.append("topogym/planning/rope_threading/hard_plans.json")
    for name in includes:
        member(root, name)
    return files, includes
