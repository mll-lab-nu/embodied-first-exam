"""Prepare the approved corner folds with the existing bounded velocity solver."""
import numpy as np

from topogym.world.physics.cloth_preparation import ClothPreparation


class CornerFoldPreparation(ClothPreparation):
    def form(self, origin):
        def target(half, corner):
            p = self.task.preparation_target(self.task.material_uv,
                half_progress=half, corner_progress=corner)
            p[:, 2] -= self.profile.table_clearance_m
            return p+origin
        if self.profile.far_half_fold:
            # The far half turns over as a flat page toward the arms at home, whose grippers hang 27-41 cm above the
            # table at y -0.09..0.06: turned in place, its free edge passes them at about 32 cm (2026-10-07). Fold
            # 15 cm farther from the arms, then bring the finished packet back 10-14 cm above the table, under them.
            away = np.array([0., .15, 0.])
            flat = target(0., 0.)
            self.drive("fold_away", lambda t: flat+t*away, 3.)
            self.drive("half_fold", lambda t: target(t, 0.)+away, 10.)
            self.drive("corner_fold", lambda t: target(1., t)+away, 7.)
            folded = target(1., 1.)+away
            self.drive("fold_return", lambda t: folded-t*away, 4.)
            return
        if self.profile.half_fold:
            self.drive("half_fold", lambda t: target(t, 0.), 10.)
        self.drive("corner_fold", lambda t: target(1., t), 7.)
