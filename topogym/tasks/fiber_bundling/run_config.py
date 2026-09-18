"""Load an exact generated scene for physical probes and robot execution."""
from pathlib import Path

from omegaconf import OmegaConf


def load_run_config(path=None):
    if path is None:
        from hydra import compose, initialize_config_dir
        with initialize_config_dir(version_base="1.3", config_dir=str(Path(__file__).resolve().parents[3]/"configs")):
            cfg = compose(config_name="fiber_bundling_preview")
    else:
        cfg = OmegaConf.load(Path(path))
    if cfg.task.variant != "anchored_terminal_v2":
        raise ValueError("Robot variant runs require the permanently anchored cable")
    OmegaConf.resolve(cfg)
    return cfg
