"""Build-time material candidates for isolated development episodes.

These helpers do not edit live solver buffers or production assets. Rebuild the
scene for every candidate; archive returned differences with its new identity.
"""
from contextlib import contextmanager
from dataclasses import replace
import math


_FIELDS = {
    'rigid': {'friction', 'coup_friction', 'rho'},
    'fem_elastic': {'E', 'nu', 'rho', 'friction_mu'},
}


def candidate_spec(spec, *, materials=None, primitive_masses_kg=None):
    """Return a new TaskSpec and changes; reject ambiguous mesh/URDF mass edits."""
    from topogym.assets.materials import MaterialSpec
    materials, masses = dict(materials or {}), dict(primitive_masses_kg or {})
    names = {e.name for e in spec.entities}
    if (set(materials) | set(masses)) - names:
        raise ValueError('Material candidate names an unknown entity')
    entities, changes = [], []
    for entity in spec.entities:
        values = dict(entity.material)
        override = dict(materials.get(entity.name, {}))
        if set(override) - _FIELDS.get(entity.physics_model, set()):
            raise ValueError('Unsupported material field for '+entity.name)
        for key, value in override.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError('Material candidate values must be finite numbers')
            if key in {'friction', 'coup_friction', 'friction_mu'} and value < 0:
                raise ValueError('Friction must be nonnegative')
        values.update(override)
        if entity.name in masses:
            mass = masses[entity.name]
            if isinstance(mass, bool) or not math.isfinite(mass) or mass <= 0:
                raise ValueError('Mass must be positive and finite')
            if entity.physics_model != 'rigid' or entity.fixed or entity.morph_type not in {'box', 'sphere', 'cylinder'}:
                raise ValueError('Explicit mass candidates currently require a movable rigid primitive; authored mesh/URDF inertia must be rebuilt separately')
            if 'rho' in override:
                raise ValueError('Choose either mass or density for one candidate entity')
            shape = entity.morph_options
            if entity.morph_type == 'box':
                volume = math.prod(shape['size'])
            elif entity.morph_type == 'sphere':
                volume = 4*math.pi*shape['radius']**3/3
            else:
                volume = math.pi*shape['radius']**2*shape['height']
            if not math.isfinite(volume) or volume <= 0:
                raise ValueError('Primitive volume must be positive')
            values['rho'] = mass/volume
        MaterialSpec(entity.physics_model, values)
        if values != dict(entity.material):
            changes.append(dict(entity=entity.name, before=dict(entity.material), after=values,
                                requested_mass_kg=masses.get(entity.name)))
        entities.append(replace(entity, material=values))
    metadata = dict(spec.metadata, exploratory_material_candidate=True,
                    formal_qualification=False, material_changes=changes)
    return replace(spec, entities=tuple(entities), metadata=metadata), changes


@contextmanager
def robot_coupling_friction(value):
    """Owner-only build scope in a dedicated process; restore builder afterward.

    The robot's IPC coefficient is coup_friction, distinct from rigid friction.
    Call only around Env.reset(), before any simulation or concurrent work.
    """
    if isinstance(value, bool) or not math.isfinite(value) or value < 0:
        raise ValueError('Robot coupling friction must be finite and nonnegative')
    from topogym.world.tabletop import StandardTabletopSceneBuilder
    original = StandardTabletopSceneBuilder.create

    def create(builder, *args, **kwargs):
        import genesis as gs
        material = kwargs.get('robot_material')
        if material is None or material.coup_type != 'external_articulation':
            raise ValueError('Robot candidate requires IPC external articulation')
        kwargs['robot_material'] = gs.materials.Rigid(**dict(material.model_dump(), coup_friction=value))
        return original(builder, *args, **kwargs)

    StandardTabletopSceneBuilder.create = create
    try:
        yield
    finally:
        StandardTabletopSceneBuilder.create = original


def ipc_pair_friction(first, second):
    """Genesis 1.2.1 combines IPC material coefficients by geometric mean."""
    if any(isinstance(v, bool) or not math.isfinite(v) or v < 0 for v in (first, second)):
        raise ValueError('Friction must be finite and nonnegative')
    return math.sqrt(first*second)
