"""Shared three-tier scene recipe; motion and robot difficulty remain unqualified."""
from dataclasses import asdict

from topogym.assets.geometry.blanket_gathered import GatheredProfile, preparation_target
from topogym.tasks.base import merge_parameters
from .common import BlanketFlattenTask


TWIST_ANGLES = {"easy": 0., "medium": 135., "hard": 270.}
REVISION = "gathered_scene_v1"


def scene_parameters(difficulty):
    """Same material, mesh, placement and pleats; only the twist angle changes."""
    profile = asdict(GatheredProfile(twist_angle_deg=TWIST_ANGLES[difficulty]))
    profile["panel_fractions"] = list(profile["panel_fractions"])
    return dict(
        gathered_profile=profile,
        center_xy_m=[-.1356786, .15],
        table_friction={"static_mu": .5, "kinetic_mu": .4, "contact_tolerance_m": .001},
        material={"bending_compliance": 1e-5, "bending_relaxation": 0., "air_resistance": .05},
        initialization_mode="frozen", initial_state_acceptance="scene_layout",
    )


class GatheredBlanketTask(BlanketFlattenTask):
    model_revision = REVISION
    fixed_parameters = ("gathered_profile",)

    def __init__(self, config=None, seed=0):
        config = dict(config or {})
        if config.get("initialization_mode", "frozen") == "frozen" and not (
                config.get("initial_state_path") or config.get("initial_state_resource")):
            from topogym.assets.library import resource_path
            from topogym.utils.io import sha256_file
            resource = self.scene_resource(seed, config)
            try:
                path = resource_path(resource)
            except ValueError as error:
                if not str(error).startswith("Unknown packaged resource:"):
                    raise
                # Definitions remain inspectable before a representative is
                # prepared. declare() gives the actionable missing-scene error.
            else:
                config.update(initial_state_resource=resource, initial_state_sha256=sha256_file(path))
        super().__init__(config, seed=seed)

    def scene_resource(self, seed, config=None):
        """Tier archives live at seed_<N>; an instance whose seeded scene variation
        (colour, pattern, centre) differs from the tier is frozen under seeded_v<version>/."""
        folder = f"{seeded_folder()}/" if self.seeded_draw(config) else ""
        from topogym.world.physics.initial_state_compatibility import ARCHIVE_REVISION, resource_profile
        return f"blanket_flatten/{ARCHIVE_REVISION}/{resource_profile()}/{self.difficulty}/{folder}seed_{seed}/manifest.json"

    @classmethod
    def seeded_draw(cls, config):
        from topogym.tasks.base import _parameter_at
        from topogym.tasks.scene_variation import axes
        merged = merge_parameters(cls.defaults, config or {})
        return any(_parameter_at(merged, axis["path"]) != _parameter_at(cls.defaults, axis["path"])
                   for axis in axes(cls))

    def initial_state_recipe(self):
        """The offline preparation that births this scene (scripts/prepare_blanket_initial_states.py --tier): controller,
        fold profile and default preparation configuration."""
        from topogym.world.physics.cloth_preparation import ClothPreparation, PreparationConfig
        return ClothPreparation, GatheredProfile(**self.config["gathered_profile"]), PreparationConfig()

    def frozen_initial_state(self):
        # Archives are explicit fixed representatives. Arbitrary seeds/configs
        # require their own preparation; never quietly reuse another seed.
        if self.generated_initial_state is None and not (
                self.config["initial_state_path"] or self.config["initial_state_resource"]):
            option = "--seeded" if self.seeded_draw(self.config) else f"--tier {self.difficulty}"
            raise ValueError(f"No frozen Blanket {self.difficulty} scene for seed {self.seed}; "
                f"run scripts/prepare_blanket_initial_states.py {option} --seed {self.seed} "
                "--acceptance scene_layout --output <new-directory>, then install_blanket_initial_state.py "
                "--candidate <new-directory>, or supply initial_state_path and initial_state_sha256")
        return super().frozen_initial_state()

    def declare(self, asset_dir, table_height_m):
        if self.config["initialization_mode"] not in {"flat_for_preparation", "frozen"}:
            raise ValueError("Gathered Blanket requires flat preparation or a frozen initial state")
        return super().declare(asset_dir, table_height_m)

    def preparation_target(self, uv, length=.60, width=.48, gather=1., twist=1.):
        return preparation_target(uv, length, width, gather, twist,
                                  GatheredProfile(**self.config["gathered_profile"]))


def seeded_folder():
    from topogym.tasks.scene_variation import SCENE_VARIATION_VERSION
    return f"seeded_v{SCENE_VARIATION_VERSION}"


def tier_defaults(difficulty):
    return merge_parameters(BlanketFlattenTask.defaults, scene_parameters(difficulty))
