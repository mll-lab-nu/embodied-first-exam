"""Visible ring supports and their matching collision geometry.

Saved configs without ``ring_mount`` keep the historical rectangular post.
The copper rod is a fixed fixture, not a simulated flexible copper beam.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path

import numpy as np

from .geometry import COPPER_COLOR


@dataclass(frozen=True)
class RingMount:
    kind: str = "legacy_box_v1"
    rod_radius_m: float = .0025

    def __post_init__(self):
        if self.kind not in ("legacy_box_v1", "thin_copper_rod_v1"):
            raise ValueError(f"Unknown ring support: {self.kind}")
        if not np.isfinite(self.rod_radius_m) or not .001 <= self.rod_radius_m <= .003:
            raise ValueError("Copper support radius must be between 1 and 3 mm")

    @classmethod
    def from_task_config(cls, cfg):
        return cls(**dict(cfg.get("ring_mount", {})))

    def signature(self, layout):
        return dict(version=1, mount=asdict(self), ring=dict(
            inner_radius_m=layout.ring_inner_radius_m,
            tube_radius_m=layout.ring_tube_radius_m, segments=layout.ring_segments))

    def parts(self, layout, center, floor):
        x, y, z = center
        base_height = .012
        bottom = z-layout.ring_inner_radius_m-2*layout.ring_tube_radius_m
        # Seat the rod 2 mm into the lower ring wall, entirely outside the hole.
        top = bottom + (.002 if self.kind == "thin_copper_rod_v1" else 0.)
        height = top-floor-base_height
        if height <= 0:
            raise ValueError("Ring support has nonpositive height")
        parts = [("ring_mount_base", "box", (x,y,floor+base_height/2),
                  (.10,.13,base_height), (.13,.19,.25))]
        pos = (x,y,(floor+base_height+top)/2)
        if self.kind == "legacy_box_v1":
            parts.append(("ring_mount_post", "box", pos, (.012,.016,height), (.38,.43,.49)))
        else:
            parts.append(("ring_mount_post", "cylinder", pos,
                          (self.rod_radius_m,height), COPPER_COLOR[:3]))
        return parts

    def add_to_scene(self, scene, layout, center, floor, manifest=None):
        import genesis as gs
        for name, kind, pos, size, color in self.parts(layout, center, floor):
            morph = (gs.morphs.Box(pos=pos, size=size, fixed=True) if kind == "box" else
                     gs.morphs.Cylinder(pos=pos, radius=size[0], height=size[1], fixed=True))
            surface = (gs.surfaces.Plastic(color=color) if kind == "box" else
                       gs.surfaces.Metal(color=color, metal_type="copper", roughness=.32))
            entity = scene.add_entity(morph, surface=surface, name=name)
            if manifest is not None:
                manifest.add(name, entity)


def require_fixture_evidence(task_cfg, gate):
    """New support/aperture configurations cannot inherit an old load certificate."""
    from .geometry import FiberLayout
    mount = RingMount.from_task_config(task_cfg)
    layout = FiberLayout(**dict(task_cfg.geometry))
    expected = mount.signature(layout)
    recorded = gate.get("ring_fixture")
    if recorded is None:
        # Historical gates tested the original aperture, without exercising its post.
        if mount != RingMount() or layout.ring != FiberLayout().ring:
            raise RuntimeError("Stability evidence lacks the current ring/support geometry")
    elif recorded != expected:
        raise RuntimeError("Stability evidence must match the current ring/support geometry")


def export_fixture(folder, layout, mount, center, floor, report):
    """Export the same fixture in working-trunk coordinates for asset inspection."""
    import trimesh
    from trimesh.visual.material import PBRMaterial
    from trimesh.visual.texture import TextureVisuals
    folder = Path(folder)
    if mount.kind == "thin_copper_rod_v1":
        ring = trimesh.load(folder/"ring.glb", force="mesh")
        ring.visual = TextureVisuals(uv=np.zeros((len(ring.vertices),2)),
            material=PBRMaterial(baseColorFactor=COPPER_COLOR, metallicFactor=.85, roughnessFactor=.32))
        ring.export(folder/"ring.glb", include_normals=True)
    fixture = trimesh.Scene()
    ring = trimesh.load(folder/"ring.glb", force="mesh")
    ring.apply_transform(trimesh.geometry.align_vectors([0,0,1], [1,0,0]))
    ring.apply_translation(center)
    fixture.add_geometry(ring, node_name="bundling_ring")
    for name, kind, pos, size, color in mount.parts(layout, center, floor):
        mesh = (trimesh.creation.box(extents=size) if kind == "box" else
                trimesh.creation.cylinder(radius=size[0],height=size[1],sections=64))
        mesh.apply_translation(pos)
        mesh.visual = TextureVisuals(uv=np.zeros((len(mesh.vertices),2)),
            material=PBRMaterial(baseColorFactor=(*color,1),
                metallicFactor=.85 if kind == "cylinder" else 0., roughnessFactor=.32 if kind == "cylinder" else .65))
        fixture.add_geometry(mesh,node_name=name)
    fixture.export(folder/"ring_fixture.glb")
    if (folder/"anchored_initial.glb").exists():
        complete = trimesh.load(folder/"anchored_initial.glb", force="scene")
        complete.add_geometry(fixture.to_geometry(),node_name="ring_fixture")
        complete.export(folder/"scene_initial.glb")
    report["ring_fixture"] = mount.signature(layout)
    report["ring_fixture"]["description"] = (
        "fixed copper rod, 2 mm seat in outer lower ring wall; visible and collision dimensions match"
        if mount.kind == "thin_copper_rod_v1" else "historical rectangular fixed post")
    # Keep the comparable signature free of descriptive fields.
    report["ring_fixture_signature"] = mount.signature(layout)
    report["ring_fixture_parts"] = [dict(name=n,kind=k,pos_m=p,size_m=s,color=c)
        for n,k,p,s,c in mount.parts(layout,center,floor)]
    (folder/"asset_report.json").write_text(json.dumps(report,indent=2)+"\n")
    (folder/"sha256.json").write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(folder.iterdir()) if p.is_file() and p.name != "sha256.json"},indent=2)+"\n")
