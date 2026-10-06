"""Prepare the approved corner folds with the existing bounded velocity solver."""
from topogym.world.physics.cloth_preparation import ClothPreparation


class CornerFoldPreparation(ClothPreparation):
    def form(self, origin):
        def target(half, corner):
            p = self.task.preparation_target(self.task.material_uv,
                half_progress=half, corner_progress=corner)
            p[:, 2] -= self.profile.table_clearance_m
            return p+origin
        if self.profile.half_fold:
            self.drive("half_fold", lambda t: target(t, 0.), 10.)
        self.drive("corner_fold", lambda t: target(1., t), 7.)
