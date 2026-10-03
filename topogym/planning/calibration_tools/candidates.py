"""Isolated candidate declarations; no edits to installed tasks or live physics."""
from contextlib import contextmanager
from copy import deepcopy
from itertools import product
import math

from .contracts import UnsupportedCapability, digest, identifier, json_value


CONFIG_FIELDS = {"physics_dt_s", "control_decimation", "solver_substeps", "task_parameters", "grasp_assist"}
FIELDS = {"name", "config", "materials", "primitive_masses_kg", "robot_material", "phase_actions", "object_drives", "geometry"}


def merge(base, patch):
    result = deepcopy(base)
    for key, value in patch.items():
        result[key] = merge(result[key], value) if isinstance(result.get(key), dict) and isinstance(value, dict) else deepcopy(value)
    return result


def validate_candidate(candidate):
    result = json_value(candidate or {})
    if not isinstance(result, dict) or set(result)-FIELDS:
        raise ValueError("Unknown candidate field")
    if "name" in result:
        identifier(result["name"])
    for name in FIELDS-{"name"}:
        if name in result and not isinstance(result[name], dict):
            raise ValueError(name+" must be a mapping")
    if set(result.get("config", {}))-CONFIG_FIELDS:
        raise ValueError("Candidate config only supports timing, task_parameters and grasp_assist")
    if "geometry" in result and (set(result["geometry"])-{"parameters", "initial_layout_lift_m"}
                                or not isinstance(result["geometry"].get("parameters"), dict)):
        raise ValueError("Geometry candidate requires a parameters mapping")
    lift = result.get("geometry", {}).get("initial_layout_lift_m", 0.)
    if isinstance(lift, bool) or not isinstance(lift, (int, float)) or not math.isfinite(lift) or not 0 <= lift <= .02:
        raise ValueError("Initial layout lift must be between zero and 20 mm")
    if any(not isinstance(name, str) or name in {"robot", "table"} or kind not in {"rigid", "fem"}
           for name, kind in result.get("object_drives", {}).items()):
        raise ValueError("object_drives maps task entity names to 'rigid' or 'fem'")
    robot = result.get("robot_material", {})
    if set(robot)-{"friction", "coup_friction"}:
        raise ValueError("Robot material candidates support friction and coup_friction")
    for fields in [robot, *result.get("materials", {}).values()]:
        if not isinstance(fields, dict):
            raise ValueError("Entity material overrides must be mappings")
        for key, value in fields.items():
            if key not in {"friction", "coup_friction", "friction_mu", "rho", "E", "nu"}:
                raise ValueError("Unsupported candidate material parameter")
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError("Candidate material values must be finite numbers")
            if (key in {"friction", "coup_friction", "friction_mu"} and value < 0 or
                key in {"rho", "E"} and value <= 0 or key == "nu" and not -1 < value < .5):
                raise ValueError("Invalid candidate material parameter")
    for value in result.get("primitive_masses_kg", {}).values():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError("Candidate mass must be positive and finite")
    from .grasp_trials import PHASES
    if set(result.get("phase_actions", {}))-set(PHASES):
        raise ValueError("Unknown candidate trial phase")
    if not all(isinstance(v, dict) for v in result.get("phase_actions", {}).values()):
        raise ValueError("phase_actions must contain action patches")
    return result


def candidate_config(config, candidate):
    from topogym.simulator.config import SimulatorConfig
    result = merge(json_value(config), validate_candidate(candidate).get("config", {}))
    if result.get("seed") is None:
        result["seed"] = 0
    SimulatorConfig(**result)  # Validate before spawning, without importing Genesis.
    return result


def candidate_trial(trial, candidate):
    from .grasp_trials import normalize_trial
    result = normalize_trial(trial)
    patches = validate_candidate(candidate).get("phase_actions", {})
    for phase in result["phases"]:
        if phase["name"] in patches:
            phase["actions"] = [merge(a, patches[phase["name"]]) for a in phase["actions"]]
    return normalize_trial(result)


def parameter_grid(axes, *, maximum=128):
    """Cartesian candidate patches, e.g. {'materials.rope.friction_mu': [.3, .6]}."""
    if not isinstance(axes, dict) or not axes:
        raise ValueError("Grid requires nonempty dotted-path axes")
    paths = [p.split(".") for p in axes]
    if any(len(p) < 2 or p[0] not in FIELDS-{"name"} or any(not v for v in p) for p in paths):
        raise ValueError("Grid paths must address candidate mappings")
    for i, p in enumerate(paths):
        if any(p[:len(q)] == q or q[:len(p)] == p for q in paths[i+1:]):
            raise ValueError("Grid paths must not overlap")
    if any(not isinstance(v, (list, tuple)) or not v for v in axes.values()):
        raise ValueError("Grid axes require nonempty value lists")
    from .contracts import positive_int
    positive_int(maximum, "maximum candidates", 128)
    if math.prod(map(len, axes.values())) > maximum:
        raise ValueError("Candidate grid exceeds maximum")
    result = []
    for index, values in enumerate(product(*axes.values())):
        row = dict(name=f"candidate_{index:03d}")
        for path, value in zip(paths, values):
            target = row
            for key in path[:-1]:
                target = target.setdefault(key, {})
            target[path[-1]] = deepcopy(value)
        result.append(validate_candidate(row))
    return result


@contextmanager
def build_candidate(env, candidate):
    """Wrap this owner's Task class and builder only while declaring a new scene."""
    candidate = validate_candidate(candidate)
    report = dict(candidate=candidate, candidate_id=digest(candidate), changes=[],
                  formal_qualification=False, live_buffers_modified=False)
    if not candidate:
        yield report
        return
    from .material_trials import candidate_spec
    from topogym.world.tabletop import StandardTabletopSceneBuilder
    original_class, original_builder = env._task_class, StandardTabletopSceneBuilder.create
    class CandidateTask(original_class):
        def declare(self, *args, **kwargs):
            if "geometry" not in candidate:
                return super().declare(*args, **kwargs)
            if self.task_id != "horseshoe_ring":
                raise UnsupportedCapability("Fresh physics geometry candidates currently support Horseshoe Ring")
            from .adapters.horseshoe_ring import declaration
            with declaration(self, candidate["geometry"]["parameters"],
                    initial_layout_lift_m=candidate["geometry"].get("initial_layout_lift_m", 0.)) as geometry:
                result = super().declare(*args, **kwargs)
            report["geometry"] = geometry
            return result

        def finalize_spec(self, spec, **kwargs):
            spec = super().finalize_spec(spec, **kwargs)
            if candidate.get("materials") or candidate.get("primitive_masses_kg") or candidate.get("robot_material"):
                if spec.initial_state is not None:
                    raise UnsupportedCapability("Material changes need a rebuilt initial-state archive for this frozen task")
            result, changes = spec, []
            if candidate.get("materials") or candidate.get("primitive_masses_kg"):
                result, changes = candidate_spec(spec, materials=candidate.get("materials"),
                    primitive_masses_kg=candidate.get("primitive_masses_kg"))
            report["changes"] = changes
            return result
    def create(builder, *args, **kwargs):
        patch = candidate.get("robot_material", {})
        if patch:
            import genesis as gs
            material = kwargs.get("robot_material")
            if material is None:
                raise UnsupportedCapability("Builder did not declare a robot material")
            if "coup_friction" in patch and material.coup_type != "external_articulation":
                raise UnsupportedCapability("Robot coup_friction requires IPC external articulation")
            kwargs["robot_material"] = gs.materials.Rigid(**dict(material.model_dump(), **patch))
        return original_builder(builder, *args, **kwargs)
    env._task_class = CandidateTask
    StandardTabletopSceneBuilder.create = create
    try:
        yield report
    finally:
        env._task_class = original_class
        StandardTabletopSceneBuilder.create = original_builder


def effective_materials(env, candidate):
    """Record observed coefficients/masses and IPC pair values where exposed."""
    from topogym.utils.arrays import to_numpy
    from itertools import combinations
    import numpy as np
    world = env._world
    names = set(candidate.get("materials", {})) | set(candidate.get("primitive_masses_kg", {}))
    if candidate.get("robot_material"):
        names.add("robot")
    entities = {}
    for name in names:
        entity = world.entities[name]
        row = dict(material=json_value(entity.material.model_dump()), mass_kg=None)
        if hasattr(entity, "get_mass"):
            row["mass_kg"] = float(np.asarray(to_numpy(entity.get_mass())).sum())
        entities[name] = row
    coupler, pairs = world.scene.sim.coupler, []
    if hasattr(coupler, "_ipc_contact_tabular"):
        contacts = {**getattr(coupler, "_ipc_abd_contacts", {}), **getattr(coupler, "_ipc_fem_contacts", {})}
        for (a, first), (b, second) in combinations(contacts.items(), 2):
            if a.name not in names and b.name not in names:
                continue
            pair = coupler._ipc_contact_tabular.at(first.id(), second.id())
            pairs.append(dict(entities=[a.name, b.name], friction=pair.friction_rate(), enabled=pair.is_enabled()))
    return dict(entities=entities, ipc_contact_pairs=pairs)
