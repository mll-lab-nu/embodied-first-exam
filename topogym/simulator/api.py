"""Thin task selection and construction, without a second environment loop."""


def env_list(*, details=False):
    from topogym.config.registry import task_catalog
    catalog = sorted(task_catalog(), key=lambda row: row["task_id"])
    if details:
        from topogym.config.registry import available_variations, variation_catalog, variation_registration
        for row in catalog:
            row.update(observation_modes=["JOINT", "EE"],
                       control_modes=["JOINT_ABS", "JOINT_DELTA", "EE_ABS", "EE_DELTA"],
                       variations=list(available_variations(row["task_id"])),
                       variation_details=list(variation_catalog(row["task_id"])),
                       base_variation=variation_registration(row["task_id"])["variation_id"],
                       rewind="current episode only; privileged; discarded future is inaccessible",
                       presentation=dict(renderer="nyx", background="compact_lab", resolution_px=[848, 480], fps=30))
    return catalog if details else [row["task_id"] for row in catalog]


def make(task_id, **configuration):
    from .config import SimulatorConfig
    from .env import Env
    return Env(SimulatorConfig(task_id=task_id, **configuration))
