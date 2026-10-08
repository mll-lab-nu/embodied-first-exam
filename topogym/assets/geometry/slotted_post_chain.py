"""Rigid link chain for the below-easy Slotted Post cord: chain, end discs and beads in one MJCF; the ring in another.

The team's rigid chain (2026-10-07): capsule links on ball joints (damping 2e-4, armature 1e-6, no bending stiffness),
cord density 650 kg/m^3 counted on each link's cylinder only, friction 0.3, condim 3. The middle link is the free root
(a chain grown from one end is slower to solve) and both halves grow from it towards the discs. Each disc hangs from
its end link by a ball joint at its eye, 43 mm from the disc centre on its top face, and does not collide with its 3
nearest links. A bead is a free body: a solid sphere the cord does not touch, and 16 capsules lining its bore that only
the cord touches. Genesis applies contype / conaffinity within one MJCF entity only (across entities every pair
collides), so the beads share the cord's file. The ring is 32 capsules round its centreline with the mass and inertia
of the torus. Coordinates are assembly-local metres.
"""
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
from scipy.spatial.transform import Rotation
from shapely.geometry import Point
import trimesh

LINK_LENGTH_M = .0165
DENSITY = 650.
JOINT_DAMPING = 2e-4
ARMATURE = 1e-6
FRICTION = .3
DISC_MASS_KG = .0623
DISC_EYE_M = .043              # eye from the disc centre, on its top face
DISC_EXCLUDED_LINKS = 3
BEAD_MASS_KG = .01717
BORE_CAPSULES = 16
BORE_CAPSULE_RADIUS_M = .0015
RING_CAPSULES = 32
RING_DENSITY = 600.            # 72.25 g for the team's 61 mm ring, 10 mm tube
# Collision bits (within the cord entity): links touch links, discs and bead bores; bead spheres touch discs and each
# other, never the links; bead bores touch only the links.
LINK_BITS = dict(contype="2", conaffinity="3")
DISC_BITS = dict(contype="1", conaffinity="1")
SPHERE_BITS = dict(contype="4", conaffinity="5")
BORE_BITS = dict(contype="8", conaffinity="2")
CORD_RGBA, WOOD_RGBA, BEAD_RGBA = ".8 .76 .64 1", ".15 .065 .035 1", ".7 .55 .34 1"
# Genesis renders an MJCF collision geom with its grey collision surface, so collision geoms sit in group 3 (not copied
# into visuals) and each part has a massless visual twin that keeps its colour.
HIDDEN = dict(group="3")
VISUAL = dict(contype="0", conaffinity="0", group="1", density="0")


def _v(values):
    return " ".join(f"{float(v):.9g}" for v in np.asarray(values).ravel())


def _wxyz(rotation):
    return _v(rotation.as_quat()[[3, 0, 1, 2]])


def _along_x(direction):
    rotation, _ = Rotation.align_vectors([direction], [[1., 0., 0.]])
    return rotation


def chain_roots(layout, cord, disc_centers):
    """Link joints at equal arc spacing along the authored cord, ending at the two disc eyes (on the disc tops)."""
    cord = np.asarray(cord, float).copy()
    top = layout.floor_clearance_m+layout.disc_thickness_m
    for end, center in ((0, disc_centers[0]), (-1, disc_centers[1])):
        cord[end, 2] = top
        if abs(np.linalg.norm(cord[end, :2]-center[:2])-DISC_EYE_M) > .002:
            raise ValueError("The authored cord end is not at a disc eye")
    arc = np.r_[0., np.cumsum(np.linalg.norm(np.diff(cord, axis=0), axis=1))]
    count = max(2, int(round(arc[-1]/LINK_LENGTH_M)))
    query = np.linspace(0., arc[-1], count+1)
    return np.column_stack([np.interp(query, arc, cord[:, k]) for k in range(3)])


def disc_mesh(layout):
    """32-sided prism, centre at the origin, bottom face at z = 0."""
    profile = Point(0., 0.).buffer(layout.disc_radius_m, quad_segs=8)
    return trimesh.creation.extrude_polygon(profile, layout.disc_thickness_m, engine="earcut")


def _disc(parent, name, parent_turn, offset, center, eye, layout):
    """Disc body at the eye (ball joint), its local +y from the centre towards the eye."""
    heading = (eye-center)[:2]
    yaw = Rotation.from_euler("z", np.arctan2(-heading[0], heading[1]))
    body = ET.SubElement(parent, "body", name=name, pos=_v(offset), quat=_wxyz(parent_turn.inv()*yaw))
    ET.SubElement(body, "joint", name=f"{name}_eye", type="ball", damping=f"{JOINT_DAMPING:.9g}",
                  armature=f"{ARMATURE:.9g}")
    m, r, h = DISC_MASS_KG, layout.disc_radius_m, layout.disc_thickness_m
    ET.SubElement(body, "inertial", pos=_v([0., -DISC_EYE_M, -h/2]), mass=f"{m:.9g}",
                  diaginertia=_v([m*(3*r*r+h*h)/12, m*(3*r*r+h*h)/12, m*r*r/2]))
    ET.SubElement(body, "geom", name=f"{name}_prism", type="mesh", mesh="disc", pos=_v([0., -DISC_EYE_M, -h]),
                  **DISC_BITS, **HIDDEN)
    ET.SubElement(body, "geom", name=f"{name}_look", type="mesh", mesh="disc", pos=_v([0., -DISC_EYE_M, -h]),
                  rgba=WOOD_RGBA, **VISUAL)
    return body


def _bead(worldbody, name, center, bore, layout):
    body = ET.SubElement(worldbody, "body", name=name, pos=_v(center),
                         quat=_wxyz(Rotation.align_vectors([bore], [[0., 0., 1.]])[0]))
    ET.SubElement(body, "freejoint", name=f"{name}_free")
    m, r = BEAD_MASS_KG, layout.bead_radius_m
    ET.SubElement(body, "inertial", pos="0 0 0", mass=f"{m:.9g}", diaginertia=_v([.4*m*r*r]*3))
    ET.SubElement(body, "geom", name=f"{name}_sphere", type="sphere", size=f"{r:.9g}", **SPHERE_BITS, **HIDDEN)
    ET.SubElement(body, "geom", name=f"{name}_look", type="sphere", size=f"{r:.9g}", rgba=BEAD_RGBA, **VISUAL)
    ring = layout.bead_hole_radius_m+BORE_CAPSULE_RADIUS_M
    half = np.sqrt(r*r-ring*ring)-BORE_CAPSULE_RADIUS_M
    for k in range(BORE_CAPSULES):
        a = 2*np.pi*k/BORE_CAPSULES
        x, y = ring*np.cos(a), ring*np.sin(a)
        ET.SubElement(body, "geom", name=f"{name}_bore_{k:02d}", type="capsule", fromto=_v([x, y, -half, x, y, half]),
                      size=f"{BORE_CAPSULE_RADIUS_M:.9g}", **BORE_BITS, **HIDDEN)


def write_cord_assembly(folder, layout, roots, disc_centers, beads):
    """Write cord.xml. roots: n+1 link joints from the left disc eye to the right one (chain_roots); disc_centers: the two
    disc centres (bottom face); beads: [(name, centre, bore direction)]. Returns (path, link names, link lengths,
    reversed flags): link i spans roots[i] -> roots[i+1]; a reversed link's frame starts at roots[i+1] and points back."""
    folder = Path(folder)
    disc_mesh(layout).export(folder/"chain_disc.obj")
    roots = np.asarray(roots, float)
    lengths = np.linalg.norm(np.diff(roots, axis=0), axis=1)
    n, middle = len(lengths), len(lengths)//2
    radius = layout.rope_radius_m
    root = ET.Element("mujoco", model="slotted_cord_chain")
    ET.SubElement(root, "compiler", angle="radian", autolimits="true", meshdir=".")
    defaults = ET.SubElement(root, "default")
    ET.SubElement(defaults, "geom", friction=f"{FRICTION:.9g} 0.005 0.0001", condim="3")
    ET.SubElement(ET.SubElement(root, "asset"), "mesh", name="disc", file="chain_disc.obj")
    worldbody = ET.SubElement(root, "worldbody")

    def link(parent, i, parent_turn, offset, reverse):
        a, b = (roots[i+1], roots[i]) if reverse else (roots[i], roots[i+1])
        turn = _along_x(b-a)
        body = ET.SubElement(parent, "body", name=f"link_{i:02d}", pos=_v(offset), quat=_wxyz(parent_turn.inv()*turn))
        if parent is worldbody:
            ET.SubElement(body, "freejoint", name="cord_free")
        else:
            ET.SubElement(body, "joint", name=f"bend_{i:02d}", type="ball", damping=f"{JOINT_DAMPING:.9g}",
                          armature=f"{ARMATURE:.9g}")
        # Mass of the link's cylinder only: counting the joint spheres the capsules overlap in adds about 28 %.
        ET.SubElement(body, "geom", name=f"cord_{i:02d}", type="capsule", fromto=_v([0., 0., 0., lengths[i], 0., 0.]),
                      size=f"{radius:.9g}", mass=f"{DENSITY*np.pi*radius*radius*lengths[i]:.9g}", **LINK_BITS, **HIDDEN)
        ET.SubElement(body, "geom", name=f"cord_{i:02d}_look", type="capsule",
                      fromto=_v([0., 0., 0., lengths[i], 0., 0.]), size=f"{radius:.9g}", rgba=CORD_RGBA, **VISUAL)
        return body, turn

    top, top_turn = link(worldbody, middle, Rotation.identity(), roots[middle], False)
    parent, turn = top, top_turn
    for i in range(middle+1, n):
        parent, turn = link(parent, i, turn, [lengths[i-1], 0., 0.], False)
    _disc(parent, "disc_right", turn, [lengths[-1], 0., 0.], np.asarray(disc_centers[1]), roots[-1], layout)
    parent, turn, offset = top, top_turn, [0., 0., 0.]
    for i in range(middle-1, -1, -1):
        parent, turn = link(parent, i, turn, offset, True)
        offset = [lengths[i], 0., 0.]
    _disc(parent, "disc_left", turn, offset, np.asarray(disc_centers[0]), roots[0], layout)
    for name, center, bore in beads:
        _bead(worldbody, name, center, bore, layout)
    contact = ET.SubElement(root, "contact")
    for disc, near in (("disc_left", range(DISC_EXCLUDED_LINKS)), ("disc_right", range(n-DISC_EXCLUDED_LINKS, n))):
        for i in near:
            ET.SubElement(contact, "exclude", body1=disc, body2=f"link_{i:02d}")
    ET.indent(root)
    path = folder/"cord.xml"
    ET.ElementTree(root).write(path, encoding="unicode")
    return path, tuple(f"link_{i:02d}" for i in range(n)), lengths, tuple(i < middle for i in range(n))


def write_ring(folder, layout, center_z):
    """Write ring.xml: one free body at the ring centre, 32 capsules round the centreline, the torus' mass and inertia."""
    folder = Path(folder)
    R, r = layout.ring_major_radius_m, layout.ring_tube_radius_m
    m = RING_DENSITY*2*np.pi**2*R*r*r
    trimesh.creation.torus(major_radius=R, minor_radius=r, major_sections=128, minor_sections=24).export(
        folder/"chain_ring.obj")
    root = ET.Element("mujoco", model="slotted_ring")
    ET.SubElement(root, "compiler", angle="radian", autolimits="true", meshdir=".")
    ET.SubElement(ET.SubElement(root, "default"), "geom", friction=f"{FRICTION:.9g} 0.005 0.0001", condim="3")
    ET.SubElement(ET.SubElement(root, "asset"), "mesh", name="ring_look", file="chain_ring.obj")
    body = ET.SubElement(ET.SubElement(root, "worldbody"), "body", name="target_ring", pos=_v([0., 0., center_z]))
    ET.SubElement(body, "freejoint", name="ring_free")
    ET.SubElement(body, "inertial", pos="0 0 0", mass=f"{m:.9g}",
                  diaginertia=_v([m*(R*R/2+5*r*r/8)]*2+[m*(R*R+3*r*r/4)]))
    angles = 2*np.pi*np.arange(RING_CAPSULES+1)/RING_CAPSULES
    points = np.column_stack([R*np.cos(angles), R*np.sin(angles), np.zeros_like(angles)])
    for k in range(RING_CAPSULES):
        ET.SubElement(body, "geom", name=f"ring_{k:02d}", type="capsule", fromto=_v([points[k], points[k+1]]),
                      size=f"{r:.9g}", **HIDDEN)
    ET.SubElement(body, "geom", name="ring_look", type="mesh", mesh="ring_look", rgba=WOOD_RGBA, **VISUAL)
    ET.indent(root)
    path = folder/"ring.xml"
    ET.ElementTree(root).write(path, encoding="unicode")
    return path, m
