"""buzz_wire_3d: legacy_spatial_maze. Difficulty is a design target, not a qualification."""

from topogym.tasks.buzz_wire_3d.common import BuzzWireTask


class BuzzWire3DLegacySpatialMazeTask(BuzzWireTask):
    variation_id = 'buzz_wire_3d_legacy_spatial_maze'
    family_id = 'legacy_spatial_maze'
    model_revision = 'simulator_v1'
    difficulty = None
