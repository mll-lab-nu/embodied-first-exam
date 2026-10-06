"""Frozen one-corner and half-plus-corner variants using the common Blanket task."""
from dataclasses import asdict

from topogym.assets.geometry.blanket_corner_folds import CornerFoldProfile, folded_positions, profile_for
from topogym.tasks.base import merge_parameters
from .common import BlanketFlattenTask
from .gathered import scene_parameters as gathered_parameters


REVISION = "corner_folds_v1"
ARCHIVE_REVISION = "corner_folds_archive_v1"
TIERS = ("very_easy", "easier")


def scene_parameters(difficulty):
    parameters = gathered_parameters("easy")
    parameters.pop("gathered_profile")
    parameters["corner_fold_profile"] = asdict(profile_for(difficulty))
    return parameters


def tier_defaults(difficulty):
    return merge_parameters(BlanketFlattenTask.defaults, scene_parameters(difficulty))


class CornerFoldBlanketTask(BlanketFlattenTask):
    model_revision = REVISION
    family_id = "corner_folds"
    fixed_parameters = ("corner_fold_profile",)

    def __init__(self, config=None, seed=0):
        config = dict(config or {})
        if config.get("initialization_mode", "frozen") == "frozen" and not (
                config.get("initial_state_path") or config.get("initial_state_resource")):
            from topogym.assets.library import resource_path
            from topogym.utils.io import sha256_file
            resource = self.scene_resource(seed)
            try:
                path = resource_path(resource)
            except ValueError as error:
                if not str(error).startswith("Unknown packaged resource:"):
                    raise
            else:
                config.update(initial_state_resource=resource, initial_state_sha256=sha256_file(path))
        super().__init__(config, seed=seed)

    def scene_resource(self, seed):
        from topogym.world.physics.initial_state_compatibility import resource_profile
        return f"blanket_flatten/{ARCHIVE_REVISION}/{resource_profile()}/{self.difficulty}/seed_{seed}/manifest.json"

    def frozen_initial_state(self):
        if not (self.config["initial_state_path"] or self.config["initial_state_resource"]):
            raise ValueError(f"No frozen Blanket {self.difficulty} scene for seed {self.seed}; run "
                f"scripts/prepare_blanket_initial_states.py --tier {self.difficulty} --seed {self.seed} "
                "--acceptance scene_layout --output <new-directory>, then "
                "scripts/install_blanket_initial_state.py --candidate <new-directory>")
        return super().frozen_initial_state()

    def declare(self, asset_dir, table_height_m):
        if self.config["initialization_mode"] not in {"flat_for_preparation", "frozen"}:
            raise ValueError("Corner-fold Blanket requires flat preparation or a frozen initial state")
        return super().declare(asset_dir, table_height_m)

    def preparation_target(self, uv, *, half_progress=1., corner_progress=1.):
        return folded_positions(uv, self.config["length_m"], self.config["width_m"],
            CornerFoldProfile(**self.config["corner_fold_profile"]),
            half_progress=half_progress, corner_progress=corner_progress)
