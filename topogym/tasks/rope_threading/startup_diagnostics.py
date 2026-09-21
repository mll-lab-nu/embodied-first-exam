"""Additional observations of startup motion; no changes to the dynamics."""
import numpy as np

from topogym.tasks.knot_untying.diagnostics import FemDiagnostics


class StartupDiagnostics(FemDiagnostics):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.startup_samples = []
        self.initial_mean_z = float(self.initial[self.rings, 2].mean())
        self.initial_com_z = float(np.average(self.initial[:, 2], weights=self.mass))

    def observe(self):
        super().observe()
        self.startup_samples.append(dict(
            time_s=self.count*self.dt,
            mean_centerline_lift_m=float(self.last_centers[:, 2].mean()-self.initial_mean_z),
            center_of_mass_lift_m=float(np.average(self.last_positions[:, 2], weights=self.mass)-self.initial_com_z),
            center_of_mass_vz_m_s=float(np.average(self.last_velocity[:, 2], weights=self.mass)),
            minimum_table_gap_m=float(self.last_positions[:, 2].min()-self.floor),
            kinetic_energy_j=float(.5*np.sum(self.mass*np.sum(self.last_velocity**2, axis=1)))))

    def report(self):
        report = super().report()
        report["startup"] = dict(
            scope="native substep observations; does not replace settling/contact qualification",
            initial_table_gap_m=float(self.initial[:, 2].min()-self.floor),
            maximum_mean_lift_m=max((s["mean_centerline_lift_m"] for s in self.startup_samples), default=0.),
            first_substep=self.startup_samples[0] if self.startup_samples else None,
            total_mass_kg=float(self.mass.sum()))
        return report
