"""Low-tier geometry candidates sharing Claw's original robot and goal contract."""
from .common import InterlockedClawsTask


class SimplifiedClawsTask(InterlockedClawsTask):
    pregrasp_weld = True
    # Keep the separately accepted low-tier placement contract unchanged.
    separation_only = False
    terminal_revision = "placement_region_v3_grasp_contact_2mm"

    def build_assets(self, folder):
        from topogym.assets.geometry.claws_simplified import build_simplified_claws
        # Same opposed TCP spacing/height as easy; retarget only the local
        # offsets required by the short-leg engagement or offset frame handle.
        q = self.opposed_q(.13, .30528805, .0222)
        assembly, report, self.initial_robot_q = build_simplified_claws(folder, self.family_id, q)
        return assembly, report
