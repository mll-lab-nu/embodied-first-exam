"""Explicit stationary tabletop friction for Genesis' frictionless PBD contact.

The Genesis 1.2.1 LegacyCoupler corrects PBD/rigid normal penetration but omits
tangential friction. This optional model supplies a per-tick Coulomb impulse
under the horizontal support-load approximation N = m*g. It is active during
both preparation and agent execution, has no hidden history or attachment,
and never changes positions, normal velocities, rest lengths or binding.
"""
from dataclasses import dataclass
import numpy as np


def friction_velocity(positions, velocities, free, *, bounds, surface_z,
                      radius, tolerance, normal_acceleration, dt, static_mu, kinetic_mu):
    """Pure dissipative contact response; free-flying particles are unchanged."""
    p, v = np.asarray(positions), np.asarray(velocities)
    result = v.copy()
    contact = (np.asarray(free, dtype=bool) &
        (np.abs(p[:, 2]-(surface_z+radius)) <= tolerance) &
        np.all((p[:, :2] >= bounds[0]) & (p[:, :2] <= bounds[1]), axis=1))
    speed = np.linalg.norm(v[:, :2], axis=1)
    impulse = max(0., normal_acceleration)*dt
    remaining = np.maximum(0., speed-kinetic_mu*impulse)
    remaining[speed <= static_mu*impulse] = 0.
    result[contact, :2] *= (remaining/np.maximum(speed, 1e-30))[contact, None]
    return result


@dataclass(frozen=True)
class TabletopPBDFriction:
    entity_names: tuple
    bounds: tuple
    surface_z: float
    static_mu: float = .5
    kinetic_mu: float = .4
    contact_tolerance_m: float = .001

    def __post_init__(self):
        if (not self.entity_names or len(set(self.entity_names)) != len(self.entity_names)
                or any(not isinstance(n, str) or not n for n in self.entity_names)):
            raise ValueError("PBD friction requires distinct entity names")
        values = [self.surface_z, self.static_mu, self.kinetic_mu, self.contact_tolerance_m]
        if not np.isfinite(values).all() or not 0 <= self.kinetic_mu <= self.static_mu or self.contact_tolerance_m <= 0:
            raise ValueError("Invalid PBD table-friction parameters")

    def apply(self, world):
        solvers = {}
        for name in self.entity_names:
            entity = world.entities[name]
            solver = entity.solver
            if type(solver).__name__ != "PBDSolver" or not hasattr(entity, "get_particles_pos"):
                raise ValueError("Tabletop particle friction requires a PBD entity")
            solvers.setdefault(solver, []).append(entity)
        for solver, entities in solvers.items():
            p, v = solver.particles.pos.to_numpy(), solver.particles.vel.to_numpy()
            free = solver.particles.free.to_numpy()
            gravity = solver._gravity.to_numpy().reshape(-1, 3)
            if len(gravity) != 1 or np.any(gravity[:, :2] != 0):
                raise ValueError("PBD tabletop friction requires unbatched vertical gravity")
            for entity in entities:
                selected = slice(entity.particle_start, entity.particle_start+entity.n_particles)
                v[selected, 0] = friction_velocity(p[selected, 0], v[selected, 0], free[selected, 0],
                    bounds=self.bounds, surface_z=self.surface_z, radius=entity.particle_size/2,
                    tolerance=self.contact_tolerance_m, normal_acceleration=-gravity[0, 2],
                    dt=world.physics_dt_s, static_mu=self.static_mu, kinetic_mu=self.kinetic_mu)
            solver.particles.vel.from_numpy(v)
