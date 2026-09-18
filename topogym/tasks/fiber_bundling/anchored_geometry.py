"""Fixed power terminal, continuous slack lead and an open cable cradle.

The terminal is the joint-free root of the same MJCF tree as the cable. The
lead and working trunk are passive links; no detachable/free cable root exists.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
from scipy.interpolate import CubicSpline
from scipy.spatial.transform import Rotation

from .geometry import FiberLayout, JACKET_COLOR, frame, generate_assets, segment_distance
from topogym.tasks._rigid_geometry import vector_text


TERMINAL_COLORS = {
    "terminal_case": (.075, .16, .18, 1), "terminal_panel": (.028, .036, .041, 1),
    "terminal_foot": (.09, .10, .11, 1), "terminal_bolt": (.48, .53, .55, 1),
    "terminal_handle": (.08, .09, .10, 1), "terminal_led": (.20, .65, .32, 1),
    "terminal_label": (.70, .75, .73, 1), "terminal_gland": (.14, .16, .17, 1),
}


@dataclass(frozen=True)
class AnchoredLayout:
    axis_height_m: float = .24
    ring_distance_from_roots_m: float = .11
    lead_step_m: float = .04
    # Terminal connector relative to the original 240 mm working-trunk root.
    connector_m: tuple = (-.32, -.16, 0.)
    cradle_x_m: float = .02

    @classmethod
    def from_task_config(cls, cfg):
        # Saved v2 run configs predate this setting. Preserve their old support
        # when replaying instead of silently rendering the new layout.
        return cls(axis_height_m=float(cfg.axis_height_m),
                   ring_distance_from_roots_m=float(cfg.ring_distance_from_roots_m),
                   cradle_x_m=float(cfg.get("cradle_x_m", .10)))

    def spacing(self, layout):
        ring_x = layout.trunk_length_m+self.ring_distance_from_roots_m
        return dict(cradle_center_to_ring_plane_m=ring_x-self.cradle_x_m,
                    cradle_upper_edge_to_ring_plane_m=ring_x-self.cradle_x_m-.065,
                    cradle_upper_edge_to_ring_surface_m=ring_x-self.cradle_x_m-.065-layout.ring_tube_radius_m,
                    note="Axial fixture spacing only; not a swept-volume or robot reachability certificate")

    def lead(self):
        controls = np.array([[-.24,-.16,0.], [-.18,-.22,-.055], [-.09,-.26,-.09],
                             [.015,-.23,-.09], [.055,-.15,-.07], [-.005,-.085,-.05],
                             [-.09,-.05,-.02], [-.08,0.,0.]])
        t = np.r_[0., np.cumsum(np.linalg.norm(np.diff(controls,axis=0),axis=1))]
        curve = CubicSpline(t, controls, bc_type=((1,[1.,0.,0.]), (1,[1.,0.,0.])))
        dense = curve(np.linspace(0,t[-1],2000))
        arc = np.r_[0.,np.cumsum(np.linalg.norm(np.diff(dense,axis=0),axis=1))]
        count = max(2,round(arc[-1]/self.lead_step_m))
        samples = np.linspace(0,arc[-1],count+1)
        curved = np.column_stack([np.interp(samples,arc,dense[:,i]) for i in range(3)])
        return np.vstack([self.connector_m, [-.28,-.16,0.], curved, [-.04,0.,0.], [0.,0.,0.]])

    def terminal_parts(self):
        """name, kind, center/fromto, size, collision; in working-trunk frame."""
        h = self.axis_height_m
        parts = [
            ("terminal_case", "box", [-.44,-.16,-h/2+.016], [.21,.18,h+.016], True),
            ("terminal_panel", "box", [-.44,-.067,-.105], [.17,.008,.16], False),
            ("terminal_label", "box", [-.44,-.062,-.068], [.11,.002,.035], False),
            ("terminal_gland", "cylinder", [-.338,-.16,0.,-.298,-.16,0.], [.018], True),
        ]
        for i,x in enumerate((-.515,-.365)):
            for j,y in enumerate((-.222,-.098)):
                parts.append((f"terminal_foot_{i}{j}","box",[x,y,-h+.004],[.045,.035,.008],True))
                parts.append((f"terminal_bolt_{i}{j}","sphere",[x,-.061,-.055-.10*j],[.003],False))
        for i in range(4):
            parts.append((f"terminal_led_{i}","box",[-.48+.025*i,-.061,-.125],[.017,.003,.007],False))
        for i,x in enumerate((-.49,-.39)):
            parts.append((f"terminal_handle_{i}","box",[x,-.16,.032],[.015,.028,.045],True))
        parts.append(("terminal_handle_top","box",[-.44,-.16,.055],[.115,.028,.014],True))
        return parts

    def cradle_parts(self, layout):
        r, h, x = layout.trunk_radius_m, self.axis_height_m, self.cradle_x_m
        return [
            ("cable_cradle_base", [x,0.,-h+.006], [.15,.11,.012], (.14,.19,.23)),
            ("cable_cradle_post", [x,0.,(-h+.012-r-.012)/2], [.024,.026,h-.024-r], (.39,.44,.47)),
            ("cable_cradle_pad", [x,0.,-r-.004], [.13,.042,.008], (.09,.10,.11)),
            ("cable_cradle_left", [x,-.021,-.005], [.13,.010,.038], (.27,.33,.37)),
            ("cable_cradle_right", [x,.021,-.005], [.13,.010,.038], (.27,.33,.37)),
        ]


def part_color(name):
    return next((color for prefix,color in TERMINAL_COLORS.items() if name.startswith(prefix)), JACKET_COLOR)


def write_anchored_bundle(path, layout, anchor):
    root = ET.parse(path).getroot()
    world = root.find("worldbody")
    trunk = world.find("body")
    world.remove(trunk)
    free = trunk.find("freejoint")
    if free is not None:
        trunk.remove(free)
    terminal = ET.SubElement(world,"body",name="fixed_terminal",pos="0 0 0")
    for name,kind,position,size,collision in anchor.terminal_parts():
        attrs = dict(name=name,type=kind,rgba=vector_text(part_color(name)))
        attrs["fromto" if kind == "cylinder" else "pos"] = vector_text(position)
        attrs["size"] = vector_text(np.asarray(size)/2 if kind == "box" else size)
        if not collision:
            attrs.update(contype="0",conaffinity="0",mass="0")
        ET.SubElement(terminal,"geom",**attrs)
    points = anchor.lead()
    previous, previous_rotation, previous_origin = terminal, Rotation.identity(), np.zeros(3)
    for i,(a,b) in enumerate(zip(points[:-1],points[1:])):
        rotation = frame(b-a)
        local = previous_rotation.inv()*rotation
        body = ET.SubElement(previous,"body",name=f"lead_{i:02d}",
            pos=vector_text(previous_rotation.inv().apply(a-previous_origin)),
            quat=vector_text(local.as_quat()[[3,0,1,2]]),gravcomp="1")
        if i:
            ET.SubElement(body,"joint",name=f"lead_bend_{i:02d}",type="ball",
                damping=str(layout.trunk_damping),stiffness="0",armature="0.000001")
        ET.SubElement(body,"geom",name=f"lead_jacket_{i:02d}",type="capsule",
            fromto=vector_text((0,0,0,np.linalg.norm(b-a),0,0)),size=str(layout.trunk_radius_m),
            rgba=vector_text(JACKET_COLOR))
        previous, previous_rotation, previous_origin = body, rotation, a
    trunk.set("pos",vector_text(previous_rotation.inv().apply(-previous_origin)))
    trunk.set("quat",vector_text(previous_rotation.inv().as_quat()[[3,0,1,2]]))
    ET.SubElement(trunk,"joint",name="trunk_bend_00",type="ball",damping=str(layout.trunk_damping),
                  stiffness="0",armature="0.000001")
    previous.append(trunk)
    ET.indent(root)
    ET.ElementTree(root).write(path,encoding="unicode",xml_declaration=True)


def generate_anchored_assets(folder, layout=None, anchor=None):
    import trimesh
    folder = Path(folder)
    layout, report = generate_assets(folder,layout)
    anchor = anchor or AnchoredLayout()
    lead = anchor.lead()
    coarse = np.vstack([lead, np.column_stack((np.arange(1,layout.trunk_segments+1)*
        layout.trunk_length_m/layout.trunk_segments, np.zeros((layout.trunk_segments,2))))])
    clearance = min(segment_distance(a,b,c,d)-2*layout.trunk_radius_m
        for i,(a,b) in enumerate(zip(coarse[:-1],coarse[1:]))
        for j,(c,d) in enumerate(zip(coarse[:-1],coarse[1:])) if j>i+1)
    if clearance <= 0:
        raise ValueError(f"Slack lead self-intersects ({clearance} m)")
    write_anchored_bundle(folder/"bundle.xml",layout,anchor)
    preview = trimesh.load(folder/"bundle_initial.glb",force="scene")
    for i,(a,b) in enumerate(zip(lead[:-1],lead[1:])):
        mesh = trimesh.creation.cylinder(radius=layout.trunk_radius_m,segment=(a,b),sections=32)
        mesh.visual.vertex_colors=np.array(JACKET_COLOR)*255
        preview.add_geometry(mesh,node_name=f"lead_{i:02d}")
        joint=trimesh.creation.icosphere(radius=layout.trunk_radius_m,subdivisions=2).apply_translation(a)
        joint.visual.vertex_colors=np.array(JACKET_COLOR)*255
        preview.add_geometry(joint,node_name=f"lead_joint_{i:02d}")
    for name,kind,position,size,collision in anchor.terminal_parts():
        if kind=="box": mesh=trimesh.creation.box(extents=size).apply_translation(position)
        elif kind=="sphere": mesh=trimesh.creation.icosphere(radius=size[0],subdivisions=2).apply_translation(position)
        else: mesh=trimesh.creation.cylinder(radius=size[0],segment=np.array(position).reshape(2,3),sections=32)
        mesh.visual.vertex_colors=np.array(part_color(name))*255
        preview.add_geometry(mesh,node_name=name)
    preview.export(folder/"bundle_initial.glb")
    preview.to_geometry().export(folder/"bundle_initial.obj")
    cradle=trimesh.Scene()
    for name,pos,size,color in anchor.cradle_parts(layout):
        mesh=trimesh.creation.box(extents=size).apply_translation(pos)
        mesh.visual.vertex_colors=np.array([*color,1.])*255
        cradle.add_geometry(mesh,node_name=name)
        preview.add_geometry(mesh.copy(),node_name=name)
    cradle.export(folder/"cradle.glb")
    preview.export(folder/"anchored_initial.glb")
    report.update(variant="anchored_terminal_v2",anchor=asdict(anchor),fixture_spacing=anchor.spacing(layout),
        model="fixed terminal root; passive articulated slack lead, working trunk and fine strands",
        lead_centerline_m=lead.tolist(),lead_length_m=float(np.linalg.norm(np.diff(lead,axis=0),axis=1).sum()),
        lead_segments_m=np.linalg.norm(np.diff(lead,axis=0),axis=1).tolist(),
        coarse_link_names=[f"lead_{i:02d}" for i in range(len(lead)-1)]+report["graspable_links"],
        coarse_min_initial_surface_clearance_m=float(clearance),
        terminal_fixed=True, cable_free_root=False,
        graspable_links=[f"trunk_{i:02d}" for i in range(layout.trunk_segments)],
        reset_support="open U cradle; contact only, no weld to cable",
        success_contract="fixed terminal and ring; head-first aperture entry; all fine strands and front jacket beyond exit; trailing lead stays attached",
        legacy_free_cable_results_apply=False,full_task_qualified=False)
    (folder/"anchored_centerlines.json").write_text(json.dumps({"lead_m":lead.tolist(),
        "working_trunk_m":coarse[len(lead)-1:].tolist(),"fibers_m":[p.tolist() for p in layout.fibers()]},indent=2)+"\n")
    (folder/"asset_report.json").write_text(json.dumps(report,indent=2)+"\n")
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir())
            if p.is_file() and p.name!="sha256.json"}
    (folder/"sha256.json").write_text(json.dumps(hashes,indent=2)+"\n")
    return layout,report
