"""Structured episode dataset export (RoboMME-structural HDF5).

Distinct from ``topogym/utils/recording.py`` (which produces mp4 video): this
package writes per-timestep obs/action/info datasets for imitation learning.
"""

from . import h5_schema
from .episode_dataset_writer import EpisodeDatasetWriter, dataset_writer_or_null

# NOTE: ``replay`` is intentionally not eager-imported here. It is run as a
# module (``python -m topogym.data.replay``); importing it in the package
# __init__ triggers a runpy double-import RuntimeWarning. Import it directly:
#   from topogym.data.replay import replay_episode

__all__ = ["EpisodeDatasetWriter", "dataset_writer_or_null", "h5_schema"]
