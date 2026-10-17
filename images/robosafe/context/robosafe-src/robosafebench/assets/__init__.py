"""Generated assets: every shape, texture and label of the benchmark is built here from parameters.

    from robosafebench.assets import catalog
    prop = catalog.build("hot_plate", {"state": "on"})

See `docs/ASSETS.md`.
"""
import os

os.environ.setdefault("MUJOCO_GL", "egl")       # head-less rendering; must be set before mujoco is first imported
