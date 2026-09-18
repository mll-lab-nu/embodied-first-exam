"""Explicit compound collision shapes shared by small rigid contact probes."""
from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
from scipy.spatial.transform import Rotation


@dataclass(frozen=True)
class RingGeometry:
    radius_m: float = .04
    tube_radius_m: float = .004
    segments: int = 48
    density_kg_m3: float = 7800.

    def __post_init__(self):
        if not all(math.isfinite(v) and v > 0 for v in
                   (self.radius_m, self.tube_radius_m, self.density_kg_m3)):
            raise ValueError("Ring dimensions and density must be finite and positive")
        if self.tube_radius_m >= self.radius_m or self.segments < 16:
            raise ValueError("Ring needs an open aperture and at least 16 segments")

    @property
    def mass_kg(self):
        return 2 * math.pi**2 * self.radius_m * self.tube_radius_m**2 * self.density_kg_m3

    def points(self):
        a = np.arange(self.segments) * 2 * np.pi / self.segments
        return np.c_[self.radius_m*np.cos(a), self.radius_m*np.sin(a), np.zeros_like(a)]


def vector_text(values):
    return " ".join(f"{float(v):.12g}" for v in values)


def primitive(link, kind, dimensions, xyz=(0, 0, 0), rpy=(0, 0, 0), color=(.7, .5, .2, 1)):
    for tag in ("visual", "collision"):
        element = ET.SubElement(link, tag)
        ET.SubElement(element, "origin", xyz=vector_text(xyz), rpy=vector_text(rpy))
        geometry = ET.SubElement(element, "geometry")
        ET.SubElement(geometry, kind, **{k: str(v) for k, v in dimensions.items()})
        if tag == "visual":
            material = ET.SubElement(element, "material", name="surface")
            ET.SubElement(material, "color", rgba=vector_text(color))


def cylinder_between(link, a, b, radius, color):
    a, b = np.asarray(a), np.asarray(b)
    delta = b-a
    length = float(np.linalg.norm(delta))
    direction = delta/length
    rpy = (0., float(np.arccos(np.clip(direction[2], -1, 1))),
           float(np.arctan2(direction[1], direction[0])))
    primitive(link, "cylinder", {"radius": radius, "length": length}, (a+b)/2, rpy, color)


def write_ring(path: Path, geometry: RingGeometry, color=(.7, .5, .2, 1), handle=False):
    root = ET.Element("robot", name="compound_ring")
    link = ET.SubElement(root, "link", name="ring")
    r, a, mass = geometry.radius_m, geometry.tube_radius_m, geometry.mass_kg
    # Circular torus inertia is the declared nominal approximation to the
    # overlapping capsule union, not an arbitrary per-collision-piece inertia.
    inertia_xy, inertia_z = mass*(.5*r*r+.625*a*a), mass*(r*r+.75*a*a)
    com = np.zeros(3)
    inertia = np.diag([inertia_xy, inertia_xy, inertia_z])
    if handle:
        length = .07
        handle_mass = geometry.density_kg_m3*np.pi*a*a*length
        handle_com = np.array([r+length/2, 0., 0.])
        total = mass+handle_mass
        com = handle_com*handle_mass/total
        handle_i = np.diag([handle_mass*a*a/2,
                           handle_mass*(3*a*a+length*length)/12,
                           handle_mass*(3*a*a+length*length)/12])
        for m, offset in ((mass, -com), (handle_mass, handle_com-com)):
            inertia += m*(np.dot(offset, offset)*np.eye(3)-np.outer(offset, offset))
        inertia += handle_i
        mass = total
        cylinder_between(link, (r,0,0), (r+length,0,0), a, color)
    inertial = ET.SubElement(link, "inertial")
    ET.SubElement(inertial, "origin", xyz=vector_text(com))
    ET.SubElement(inertial, "mass", value=str(mass))
    ET.SubElement(inertial, "inertia", ixx=str(inertia[0,0]), iyy=str(inertia[1,1]),
                  izz=str(inertia[2,2]), ixy="0", ixz="0", iyz="0")
    points = geometry.points()
    for start, end in zip(points, np.roll(points, -1, axis=0)):
        cylinder_between(link, start, end, a, color)
        primitive(link, "sphere", {"radius": a}, start, color=color)
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(root)
    ET.ElementTree(root).write(path, encoding="unicode", xml_declaration=True)
    return {"mass_kg": mass, "center_of_mass_m": com.tolist(),
            "inertia_kg_m2": inertia.tolist(), "collision_shapes": 2*geometry.segments+int(handle)}


def world_ring(geometry, position, quaternion_wxyz):
    q = np.asarray(quaternion_wxyz)
    rotation = Rotation.from_quat(q[[1, 2, 3, 0]])
    return rotation.apply(geometry.points())+position, rotation.apply([0., 0., 1.])


def disk_linking_number(center, normal, radius, other_points):
    """Oriented intersections of a polygonal loop with a circular spanning disk.

    Valid for separated rigid circular rings. This checks topology of observed
    states; timestep/contact checks are separately required to catch tunneling.
    """
    p = np.asarray(other_points)-center
    q = np.roll(p, -1, axis=0)
    d0, d1 = p@normal, q@normal
    crossing = ((d0 <= 0) & (d1 > 0)) | ((d0 > 0) & (d1 <= 0))
    if not crossing.any():
        return 0
    t = d0[crossing]/(d0[crossing]-d1[crossing])
    intersection = p[crossing]+t[:,None]*(q[crossing]-p[crossing])
    inside = np.linalg.norm(intersection, axis=1) < radius
    return int(np.sign(d1[crossing]-d0[crossing])[inside].sum())
