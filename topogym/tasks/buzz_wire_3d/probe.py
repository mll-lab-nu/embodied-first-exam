"""A finite-thickness wire and a free rigid ring with a physical handle."""
from dataclasses import dataclass
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
from scipy.spatial.transform import Rotation

from topogym.tasks._rigid_geometry import RingGeometry, cylinder_between, primitive, write_ring


@dataclass(frozen=True)
class BuzzProbeLayout:
    wire_radius_m: float = .004
    curve_radius_m: float = .10
    ring: RingGeometry = RingGeometry(radius_m=.024, tube_radius_m=.004, density_kg_m3=1500.)
    arc_segments: int = 48

    def pose(self, progress):
        """Vertical lead-in followed by a bend; progress is a path parameter."""
        if progress <= .4:
            return np.array([0.,0.,.20+.12*progress/.4]), np.array([1.,0.,0.,0.])
        theta = (progress-.4)/.6
        position = np.array([self.curve_radius_m*(1-np.cos(theta)), 0.,
                             .32+self.curve_radius_m*np.sin(theta)])
        return position, Rotation.from_euler("y",theta).as_quat()[[3,0,1,2]]

    def validate(self):
        if not 0<self.wire_radius_m<self.ring.radius_m-self.ring.tube_radius_m:
            raise ValueError("Wire must fit through ring aperture")
        if self.curve_radius_m<=2*(self.ring.radius_m+self.ring.tube_radius_m):
            raise ValueError("Probe bend is too tight for the ring")


def build_buzz_probe(layout, output: Path, dt=.002, render=True, renderer="nyx"):
    import genesis as gs
    from topogym.core import EntityManifest
    from topogym.world.presentation import add_preview_camera
    layout.validate()
    scene=gs.Scene(show_viewer=False,sim_options=gs.options.SimOptions(dt=dt,substeps=4),
        rigid_options=gs.options.RigidOptions(enable_collision=True,iterations=100,
            max_collision_pairs=512,constraint_timeconst=.005))
    scene.add_entity(gs.morphs.Plane(),material=gs.materials.Rigid(friction=.3))
    root=ET.Element("robot",name="wire_fixture")
    link=ET.SubElement(root,"link",name="wire")
    color=(.45,.48,.51,1)
    theta=np.linspace(0,np.pi/2,layout.arc_segments+1)
    arc=np.c_[layout.curve_radius_m*(1-np.cos(theta)),np.zeros_like(theta),
              .32+layout.curve_radius_m*np.sin(theta)]
    points=np.vstack(([0,0,.14],arc))
    for a,b in zip(points[:-1],points[1:]):
        cylinder_between(link,a,b,layout.wire_radius_m,color)
        primitive(link,"sphere",{"radius":layout.wire_radius_m},b,color=color)
    # Solid caps prevent removing the ring via an open endpoint.
    for p in (points[0],points[-1]):
        primitive(link,"sphere",{"radius":.022},p,color=(.25,.35,.25,1))
    cylinder_between(link,[0,0,0],[0,0,.14],.012,color)
    path=output/"assets/wire.urdf"
    path.parent.mkdir(parents=True,exist_ok=True)
    ET.indent(root)
    ET.ElementTree(root).write(path,encoding="unicode",xml_declaration=True)
    wire=scene.add_entity(gs.morphs.URDF(file=str(path.resolve()),fixed=True,
        merge_fixed_links=False,convexify=True,decimate=False),material=gs.materials.Rigid(friction=.3))
    path=output/"assets/ring_handle.urdf"
    metadata=write_ring(path,layout.ring,color=(.8,.45,.12,1),handle=True)
    position,quaternion=layout.pose(0)
    ring=scene.add_entity(gs.morphs.URDF(file=str(path.resolve()),pos=position,quat=quaternion,
        fixed=False,align=False,merge_fixed_links=False,convexify=True,decimate=False),
        material=gs.materials.Rigid(friction=.3))
    camera=add_preview_camera(scene,EntityManifest(),res=(800,600),pos=(.48,-.6,.48),
        lookat=(.035,0,.30),fov=40,renderer=renderer) if render else None
    scene.build()
    return scene,wire,ring,camera,metadata
