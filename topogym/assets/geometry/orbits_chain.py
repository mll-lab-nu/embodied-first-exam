"""Rigid link chain for the below-easy Orbits cord: the handle and the chain in one MJCF.

The handle is the free root body. Capsule links hang from it by ball joints in two branches, one from above each
handle eye; the branches meet at the middle of the loop, tied by an MJCF <connect> equality (a ball constraint). Genesis
resolves static equalities within one entity only, so the handle and the chain share this file. Coordinates are
task-local (unrotated template), metres.
"""
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
from scipy.spatial.transform import Rotation

# Collision bits: chain links touch each other, the fixture, the table and the robot (default bit 1), never the
# handle they are tied to; the handle touches the fixture, the table and the robot.
LINK_BITS, HANDLE_BITS = dict(contype="2", conaffinity="3"), dict(contype="4", conaffinity="1")
CORD_RGBA = ".98 .78 .015 1"


def chain_polyline(layout, cord, radius_m):
    """The authored cord outside the handle, raised for the chain radius.

    The FEM cord ran down through each eye; the chain starts and ends above the handle top, where its end links
    are tied to the eyes, so no link starts inside the handle.
    """
    cord = np.asarray(cord, dtype=float).copy()
    cord[:, 2] += radius_m-layout.cord_radius_m
    top = layout.clearance_m+layout.handle_height_m+radius_m
    above = np.flatnonzero(cord[:, 2] >= top)
    if len(above) < 2:
        raise ValueError("The authored cord never rises above the handle")
    return cord[above[0]:above[-1]+1]


def resample_links(polyline, link_length_m):
    """Link roots at equal arc spacing; the chain ends exactly at the polyline's last point."""
    arc = np.r_[0., np.cumsum(np.linalg.norm(np.diff(polyline, axis=0), axis=1))]
    count = max(2, int(round(arc[-1]/link_length_m)))
    query = np.linspace(0., arc[-1], count+1)
    return np.column_stack([np.interp(query, arc, polyline[:, k]) for k in range(3)])


def _along_x(direction):
    """Rotation taking +x to direction (no roll about it)."""
    rotation, _ = Rotation.align_vectors([direction], [[1., 0., 0.]])
    return rotation


def _v(values):
    return " ".join(f"{float(v):.9g}" for v in np.asarray(values).ravel())


def _wxyz(rotation):
    return _v(rotation.as_quat()[[3, 0, 1, 2]])


def write_cord_assembly(folder, layout, points, *, radius_m, density=650., joint_damping=2e-4, young_modulus_pa=0.,
                        armature=1e-6, friction=.3):
    """Write cord.xml: the handle (free root) with one chain branch from each eye, joined at the middle.

    points are the n+1 link roots and final tip from resample_links, eye to eye. Link i always has its frame at
    points[i] with +x toward points[i+1] (the loop order), so a reader walks the loop by name. Links before the middle
    m = n // 2 hang from the first eye (ball joint at their root); links from m on hang from the second eye, each from
    its successor (ball joint at its far end). The tip of link m-1 is tied to the root of link m by an MJCF <connect>.
    The teammate standard (2026-10-07): a handle root with two branches keeps the tree shallow; ball-joint damping 2e-4,
    armature 1e-6, friction 0.3 with condim 3, mass from each link's cylinder only (the capsule's end spheres overlap the
    neighbours'), bending stiffness from a Young's modulus, k = E pi r^4 / (4 L).
    Returns (path, link names, link lengths, m).
    """
    folder = Path(folder)
    points = np.asarray(points, dtype=float)
    lengths = np.linalg.norm(np.diff(points, axis=0), axis=1)
    n = len(lengths)
    middle = n//2
    root = ET.Element("mujoco", model="orbits_cord_chain")
    ET.SubElement(root, "compiler", angle="radian", autolimits="true", meshdir=".")
    defaults = ET.SubElement(root, "default")
    ET.SubElement(defaults, "geom", friction=f"{friction:.9g}", condim="3", solref="0.002 1", solimp="0.95 0.99 0.001")
    asset = ET.SubElement(root, "asset")
    ET.SubElement(asset, "mesh", name="handle_visual", file="handle.obj")
    body = ET.SubElement(ET.SubElement(root, "worldbody"), "body", name="handle", pos="0 0 0")
    ET.SubElement(body, "freejoint", name="handle_free")
    l = layout
    ET.SubElement(body, "geom", name="handle_box", type="box", density="700",
                  pos=_v([l.handle_x_m, 0., l.clearance_m+l.handle_height_m/2]),
                  size=_v([l.handle_length_m/2, l.handle_width_m/2, l.handle_height_m/2]), **HANDLE_BITS)
    ET.SubElement(body, "geom", name="handle_wood", type="mesh", mesh="handle_visual", density="0",
                  contype="0", conaffinity="0", rgba=".86 .66 .42 1")
    turns = [_along_x(points[i+1]-points[i]) for i in range(n)]
    links = {}

    def add(i, parent, parent_origin, parent_turn, joint_x):
        link = ET.SubElement(parent, "body", name=f"link_{i:02d}", pos=_v(parent_turn.inv().apply(points[i]-parent_origin)),
                             quat=_wxyz(parent_turn.inv()*turns[i]))
        stiffness = young_modulus_pa*np.pi*radius_m**4/(4*lengths[i])
        ET.SubElement(link, "joint", name=f"bend_{i:02d}", type="ball", pos=_v([joint_x, 0., 0.]),
                      damping=f"{joint_damping:.9g}", stiffness=f"{stiffness:.9g}", armature=f"{armature:.9g}")
        ET.SubElement(link, "geom", name=f"cord_{i:02d}", type="capsule", fromto=_v([0., 0., 0., lengths[i], 0., 0.]),
                      size=f"{radius_m:.9g}", mass=f"{density*np.pi*radius_m**2*lengths[i]:.9g}", rgba=CORD_RGBA,
                      **LINK_BITS)
        links[i] = link
        return link

    parent, origin, turn = body, np.zeros(3), Rotation.identity()
    for i in range(middle):
        parent = add(i, parent, origin, turn, 0.)
        origin, turn = points[i], turns[i]
    parent, origin, turn = body, np.zeros(3), Rotation.identity()
    for i in range(n-1, middle-1, -1):
        parent = add(i, parent, origin, turn, lengths[i])
        origin, turn = points[i], turns[i]
    ET.SubElement(links[middle-1], "site", name="tip_a", pos=_v([lengths[middle-1], 0., 0.]))
    ET.SubElement(links[middle], "site", name="tip_b", pos="0 0 0")
    ET.SubElement(ET.SubElement(root, "equality"), "connect", name="middle_tie", site1="tip_a", site2="tip_b",
                  solref="0.005 1")
    # No <contact><exclude> for the two links at the tie, whose end spheres overlap there: Genesis already drops pairs
    # touching at build, and it turns an exclude into rewritten contype / conaffinity bits for the whole entity (a z3
    # solve), which zeroed some links and failed the load (KeyError 'vmesh'). A MuJoCo check must exclude the pair
    # itself; unexcluded, it pushed the tie 3.6 mm apart.
    ET.indent(root)
    path = folder/"cord.xml"
    ET.ElementTree(root).write(path, encoding="unicode")
    return path, tuple(f"link_{i:02d}" for i in range(n)), lengths, middle
