"""Detached upper-bar modeling candidates for the frozen Hedgehog hard cage.

Rebuilds visible and collision assets together. Candidates carry fresh hashes;
neither old oracle qualification nor a native settled state is transferred.
"""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import xml.etree.ElementTree as ET

import numpy as np
import trimesh

from ..contracts import UnsupportedCapability, digest


BASE_SHA256 = "d9207b1d1eabd88d7320f1aef1fce8d6161e77d63574798bf5e374cc052c1e58"
DEFAULTS = dict(bar_phases_deg=[240.], radial_offset_m=.004,
                start_z_m=.036, plateau_start_z_m=.060,
                plateau_end_z_m=.086, end_z_m=.106)


def parameters_checked(parameters):
    if not isinstance(parameters, dict) or set(parameters) - DEFAULTS.keys():
        raise ValueError("Unsupported upper-bar relief parameter")
    result = dict(deepcopy(DEFAULTS), **deepcopy(parameters))
    phases = np.asarray(result["bar_phases_deg"], float)
    if phases.ndim != 1 or not 1 <= len(phases) <= 6 or not np.isfinite(phases).all():
        raise ValueError("Expected one to six finite bar phases")
    if len(set(phases.tolist())) != len(phases) or not np.isin(phases, np.arange(6)*60.).all():
        raise ValueError("Bar phases must be distinct multiples of 60 degrees")
    names = ["radial_offset_m", "start_z_m", "plateau_start_z_m", "plateau_end_z_m", "end_z_m"]
    values = np.asarray([result[k] for k in names], float)
    if not np.isfinite(values).all() or any(isinstance(result[k], bool) for k in names):
        raise ValueError("Expected finite relief dimensions")
    offset, low, a, b, high = values
    if not 0 <= offset <= .010 or not -.09 <= low < a <= b < high <= .106:
        raise ValueError("Relief must be at most 10 mm and below the untouched top collar")
    result.update({k: float(v) for k, v in zip(names, values)})
    result["bar_phases_deg"] = phases.tolist()
    return result


def deform_vertices(vertices, parameters):
    """Radially translate cross sections, with cubic ramps at either end."""
    p = parameters_checked(parameters)
    vertices = np.asarray(vertices, float)
    result = vertices.copy()
    z = vertices[:, 2]
    theta = np.arctan2(vertices[:, 1], vertices[:, 0])
    selected = np.zeros(len(vertices), bool)
    for phase in p["bar_phases_deg"]:
        center = np.deg2rad(phase + 4.659091 + 159.09090742*z)
        delta = np.arctan2(np.sin(theta-center), np.cos(theta-center))
        selected |= np.abs(delta) < np.deg2rad(8)
    selected &= (z > p["start_z_m"]+1e-8) & (z < p["end_z_m"]-1e-8)
    up = np.clip((z-p["start_z_m"])/(p["plateau_start_z_m"]-p["start_z_m"]), 0, 1)
    down = np.clip((p["end_z_m"]-z)/(p["end_z_m"]-p["plateau_end_z_m"]), 0, 1)
    amount = p["radial_offset_m"] * up*up*(3-2*up) * down*down*(3-2*down) * selected
    radial = np.linalg.norm(vertices[:, :2], axis=1)
    result[:, :2] += amount[:, None]*vertices[:, :2]/np.maximum(radial[:, None], 1e-12)
    return result


def rebuild_assets(task, parameters, folder):
    """Rebuild an already unpacked disposable asset directory, never resources."""
    from topogym.assets.library import resource_path
    if task.task_id != "hedgehog_in_cage" or task.variation_id != "hedgehog_in_cage_hard":
        raise UnsupportedCapability("Upper-bar relief currently supports frozen Hedgehog hard")
    source = resource_path(task.asset_resource)
    if hashlib.sha256(source.read_bytes()).hexdigest() != BASE_SHA256:
        raise ValueError("Hedgehog source assets changed; rederive the bar parameterization")
    p = parameters_checked(parameters)
    folder = Path(folder).resolve()
    if folder == source.parent.resolve() or source.resolve().is_relative_to(folder):
        raise ValueError("Candidate output must be separate from installed resources")
    if (folder / "geometry_candidate.json").exists():
        raise ValueError("Refusing to compound a deformation onto an existing candidate")
    report = json.loads((folder / "asset_report.json").read_text())
    before_hashes = {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in folder.iterdir() if f.is_file()}
    original_parts, rebuilt_parts, changed = [], [], []
    for path in sorted(folder.glob("cage_collision_*.obj")):
        mesh = trimesh.load(path, force="mesh", process=False)
        original_parts.append(mesh)
        vertices = deform_vertices(mesh.vertices, p)
        if np.array_equal(vertices, mesh.vertices):
            rebuilt_parts.append(mesh)
            continue
        candidate = trimesh.Trimesh(vertices, mesh.faces.copy(), process=False).convex_hull
        if not candidate.is_watertight or not candidate.is_convex or candidate.volume <= 0:
            raise ValueError("Candidate collision cell is not a closed convex solid")
        candidate.export(path)
        rebuilt_parts.append(candidate)
        changed.append(path.name)
    # Preserve the original GLB material and UVs; its graph uses cage coordinates.
    for name in ("cage.obj", "cage.glb"):
        path = folder / name
        mesh = trimesh.load(path, process=False)
        if isinstance(mesh, trimesh.Scene):
            for node in mesh.graph.nodes_geometry:
                transform, _ = mesh.graph[node]
                if not np.allclose(transform, np.eye(4), atol=1e-12):
                    raise ValueError("Expected identity visual transform")
            for geometry in mesh.geometry.values():
                geometry.vertices = deform_vertices(geometry.vertices, p)
        else:
            mesh.vertices = deform_vertices(mesh.vertices, p)
        mesh.export(path)
    # Match the source's additive-part mass model, including embedded overlaps.
    density = report["bodies"]["cage"]["mass_kg"] / sum(m.volume for m in original_parts)
    mass = sum(m.volume*density for m in rebuilt_parts)
    center = sum(m.volume*density*m.center_mass for m in rebuilt_parts)/mass
    inertia = np.zeros((3, 3))
    for mesh in rebuilt_parts:
        d = mesh.center_mass-center
        inertia += density*mesh.moment_inertia + mesh.volume*density*(np.dot(d, d)*np.eye(3)-np.outer(d, d))
    tree = ET.parse(folder / "cage.urdf")
    inertial = tree.getroot().find("link/inertial")
    inertial.find("origin").set("xyz", " ".join(f"{x:.15g}" for x in center))
    inertial.find("mass").set("value", repr(float(mass)))
    for key, i, j in [("ixx",0,0),("iyy",1,1),("izz",2,2),("ixy",0,1),("ixz",0,2),("iyz",1,2)]:
        inertial.find("inertia").set(key, repr(float(inertia[i,j])))
    tree.write(folder / "cage.urdf", encoding="utf-8", xml_declaration=True)
    report["bodies"]["cage"].update(mass_kg=float(mass), center_of_mass_m=center.tolist(), inertia_kg_m2=inertia.tolist())
    report["shape"]["upper_bar_relief"] = p
    report["shape"]["side_exit_blocked_by_core"] = None
    report["shape"]["side_exit_guard_requires_revalidation"] = True
    report["maximum_radial_extent_m"] = max(float(np.linalg.norm(m.vertices[:, :2], axis=1).max()) for m in rebuilt_parts)
    report.update(geometry_candidate=True, historical_certificate_transferred=False)
    (folder / "asset_report.json").write_text(json.dumps(report, indent=2)+"\n")
    template = json.loads((folder / "template.json").read_text())
    template["cage"]["custom_shape"]["upper_bar_relief"] = p
    template["cage"]["custom_shape"]["side_exit_blocked_by_core"] = None
    template["cage"]["custom_shape"]["side_exit_guard_requires_revalidation"] = True
    (folder / "template.json").write_text(json.dumps(template, indent=2)+"\n")
    after_hashes = {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in folder.iterdir() if f.is_file()}
    for name in before_hashes:
        if name.startswith("hedgehog") or name.startswith("counterfactual_closed_stem"):
            if after_hashes[name] != before_hashes[name]:
                raise ValueError("Candidate changed the ball or the closed-stem control")
    record = dict(candidate_id="hard_upper_bar_relief_"+digest(p)[:12], parameters=p,
                  base_sha256=BASE_SHA256, candidate_sha256=digest(after_hashes),
                  changed_collision_cells=changed, mass_density_kg_m3=float(density),
                  geometry_scope="visible mesh plus convex collision cells; native rebuild required",
                  visual_collision_sources_updated=True, top_collar_unchanged=True,
                  native_execution_verified=False, formal_qualification=False,
                  old_oracle_qualification_transferred=False, assets=after_hashes)
    (folder / "geometry_candidate.json").write_text(json.dumps(record, indent=2)+"\n")
    return record


def preview(task, parameters, output):
    from topogym.assets.variation_resources import unpack_assets
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    unpack_assets(task.asset_resource, output)
    return dict(rebuild_assets(task, parameters, output), output=str(output))


@contextmanager
def declaration(task, parameters):
    """Override one disposable Task instance's asset builder, not global state."""
    import types
    if task.entities or task.last_physics_step is not None:
        raise ValueError("Geometry candidates require a fresh disposable Task, not a live episode")
    p = parameters_checked(parameters)
    original = task.build_assets
    original_revision = task.model_revision
    original_instance = task.instance_id
    had_override = "build_assets" in task.__dict__
    saved_override = task.__dict__.get("build_assets")
    had_revision = "model_revision" in task.__dict__
    record = {}
    def build(self, folder):
        _, ball, bottom, report = original(folder)
        record.update(rebuild_assets(self, p, folder))
        report.update(json.loads((Path(folder)/"asset_report.json").read_text()))
        return trimesh.load(Path(folder)/"cage.obj", force="mesh", process=False), ball, bottom, report
    task.build_assets = types.MethodType(build, task)
    task.model_revision = original_revision+"_bar_relief_"+digest(p)[:12]
    task.instance_id = digest(dict(base_instance_id=original_instance, base_assets_sha256=BASE_SHA256,
                                  candidate_parameters=p, model_revision=task.model_revision))
    try:
        yield record
    finally:
        task.instance_id = original_instance
        if had_override:
            task.build_assets = saved_override
        else:
            del task.build_assets
        if had_revision:
            task.model_revision = original_revision
        else:
            del task.model_revision
