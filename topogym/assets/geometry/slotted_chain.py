"""Slotted Post Ring with the cord as a rigid capsule chain: one MJCF of the fixture and every movable part.

The layout is the FEM task's (SlottedPostLayout); the assembly frame has its origin at the post centre on the table,
z up. The base and the post are fixed boxes (the post as two rails, the sill below the slot and the bridge above
it). The ring is RING_SEGMENTS capsules. A bead is a sphere that the cord never touches plus an annulus of
BORE_SEGMENTS capsules round its bore that only the cord touches, so it stops at the slot and the cord slides through
it. The cord is `links` capsules of the cord's radius joined by ball joints with no bending stiffness, rooted at the
middle link (a chain grown from one end makes the contact Jacobians dense); each disc, a DISC_SIDES-sided prism
(Genesis 1.2.1 lets a capsule drift on a primitive cylinder's face), hangs on its cord end by a ball joint at its eye
and never touches its 3 nearest links.

Contact bits: 1 is everything but the bead spheres, 2 the bead spheres; a bead sphere meets every part but the cord.

Masses are the FEM task's (rigid parts at Genesis' default 600 kg/m^3, the cord at 650 kg/m^3), not the capsules'
volumes: the ring a torus (its overlapping capsules would weigh 2.1x), a bead a sphere less its bore, a cord link its
cylinder (the joint spheres would add 28%).
"""
import xml.etree.ElementTree as ET

import numpy as np
from scipy.spatial.transform import Rotation as R

from topogym.assets.geometry.slotted_post_ring import SlottedPostLayout, centerline

LINKS = 88                 # 16.5 mm links (29.6 mm links stop bead1 sliding along the cord: it drags the cord)
RING_SEGMENTS = 32
BORE_SEGMENTS = 16
DISC_SIDES = 32
WOOD_KG_M3 = 600.
CORD_KG_M3 = 650.
JOINT_DAMPING = 2e-4
EYE_LOCAL_M = (0., .043, .011)     # the cord's end on the disc's top face, from its centre (the FEM attachment)
PARTS = ("ring", "bead_left", "bead_right", "disc_left", "disc_right")
COLOURS = dict(fixture=".78 .62 .42 1", ring=".2 .42 .85 1", bead=".85 .22 .18 1", disc=".38 .6 .25 1",
               links=(".12 .12 .12 1", ".96 .8 .22 1"))     # the links alternate: a chain, not a rope
# The cord 0.63 m longer than the FEM task's (LINKS links of 16.5 mm): from disc1's eye it runs the task's way
# towards the post (bead1 no longer on it: B stands disc1 up by a link there), turns out along y -0.21 to x -0.395,
# comes back along y -0.17 through bead1 (now at BEAD1_XY_M, its bore along x) and joins the task's way to the slot.
# The extra becomes the front bight after M1, so that bead1 can be drawn far out before the ring is lifted (user,
# 2026-10-07); bead1 still slides along a nearly straight cord to the slot's mouth in M1.
CORD_OUT_XY_M = ((-.12, -.21), (-.24, -.21), (-.36, -.21), (-.385, -.202), (-.395, -.19), (-.385, -.178),
                 (-.36, -.17))
BEAD1_XY_M = (-.24, -.17)
BEAD1_BORE_HALF_M = .06       # the cord straight through bead1 this far either side (controls)
CORD_ON_M = ((-.12, -.17),)   # then to the task's cord where it climbs to the slot


class ChainLayout(SlottedPostLayout):
    """The FEM task's layout with bead1 moved from its place to the extra cord's way back."""

    def cord_controls(self):
        c = super().cord_controls()
        z = self.rope_radius_m+.001                        # on the table
        bz = c[2, 2]                                        # through bead1's bore at its centre's height
        x, y = BEAD1_XY_M
        bead = [(x-BEAD1_BORE_HALF_M, y, bz), (x, y, bz), (x+BEAD1_BORE_HALF_M, y, bz)]
        table = lambda pts: [(px, py, z) for px, py in pts]
        return np.vstack([c[:1], table(c[1:4, :2]), table(CORD_OUT_XY_M), bead, table(CORD_ON_M), c[4:]])

    def bead_controls(self):
        _, right = super().bead_controls()
        return 4+len(CORD_OUT_XY_M)+1, right


def _v(x):
    return " ".join(f"{a:.9g}" for a in np.asarray(x, float).ravel())


def _quat(rotation):
    return _v(rotation.as_quat()[[3, 0, 1, 2]])


def chain_points(layout, links=LINKS):
    """links+1 points one chord (the task cord's length / links) apart along the task's centerline, from the left
    disc's eye: the chain's joints at the reset."""
    path = centerline(layout, .008)
    chord = float(np.linalg.norm(np.diff(path, axis=0), axis=1).sum())/links
    s = np.r_[0., np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))]
    dense = np.column_stack([np.interp(np.arange(0., s[-1], .0005), s, path[:, k]) for k in range(3)])
    out, j = [dense[0]], 0
    while len(out) <= links:
        far = np.linalg.norm(dense[j:]-out[-1], axis=1) >= chord
        if not far.any():
            out.append(out[-1]+chord*(out[-1]-out[-2])/np.linalg.norm(out[-1]-out[-2]))
            continue
        j += int(np.argmax(far))
        a, b = dense[j-1]-out[-1], dense[j]-dense[j-1]
        t = np.roots([b @ b, 2*a @ b, a @ a-chord**2])        # |a + t b| = chord on the segment
        out.append(dense[j-1]+float(max(t.real))*b)
    return np.array(out)


def fixture_boxes(layout):
    """[(name, centre, half size)] of the fixed boxes in the assembly frame."""
    lay = layout
    top = lay.base_height_m+lay.post_height_m
    boxes = [("base", [0., 0., lay.base_height_m/2], [lay.base_width_m/2, lay.base_depth_m/2, lay.base_height_m/2])]
    for name, x0, x1, z0, z1 in (("rail_left", -lay.post_width_m/2, -lay.slot_width_m/2, lay.base_height_m, top),
                                 ("rail_right", lay.slot_width_m/2, lay.post_width_m/2, lay.base_height_m, top),
                                 ("sill", -lay.slot_width_m/2, lay.slot_width_m/2, lay.base_height_m, lay.slot_bottom_m),
                                 ("bridge", -lay.slot_width_m/2, lay.slot_width_m/2, lay.slot_top_m, top)):
        boxes.append((name, [(x0+x1)/2, 0., (z0+z1)/2], [(x1-x0)/2, lay.post_depth_m/2, (z1-z0)/2]))
    return boxes


def part_vertices(layout):
    """Points on each movable part's surface in its body frame (ring, beads, discs), for region checks."""
    lay = layout
    th = np.arange(RING_SEGMENTS)*2*np.pi/RING_SEGMENTS
    u = np.column_stack([np.cos(th), np.sin(th), np.zeros_like(th)])
    ring = np.vstack([(lay.ring_major_radius_m+lay.ring_tube_radius_m*c)*u+[0., 0., lay.ring_tube_radius_m*s]
                      for c, s in ((1, 0), (-1, 0), (0, 1), (0, -1))])
    bead = lay.bead_radius_m*np.vstack([np.eye(3), -np.eye(3)])
    th = np.arange(DISC_SIDES)*2*np.pi/DISC_SIDES
    rim = np.column_stack([lay.disc_radius_m*np.cos(th), lay.disc_radius_m*np.sin(th)])
    disc = np.vstack([np.column_stack([rim, np.full(DISC_SIDES, z)]) for z in (-lay.disc_thickness_m/2,
                                                                             lay.disc_thickness_m/2)])
    return dict(ring=ring, bead_left=bead, bead_right=bead, disc_left=disc, disc_right=disc)


def scene_xml(layout, links=LINKS):
    """(MJCF text of the task's reset, chain points)."""
    lay = layout
    root = ET.Element("mujoco", model="slotted_post_ring_chain")
    ET.SubElement(root, "compiler", angle="radian", autolimits="true")
    d = ET.SubElement(root, "default")
    ET.SubElement(d, "geom", friction=".3 .001 .00001", solref=".001 1", solimp=".95 .99 .0005", condim="3",
                  contype="3", conaffinity="3", density=str(WOOD_KG_M3))
    asset = ET.SubElement(root, "asset")
    world = ET.SubElement(root, "worldbody")

    def look(parent, name, rgba, **geom):
        """A visual twin of a geom: the renderer draws collision geoms in one grey, visual-only ones in their colour."""
        ET.SubElement(parent, "geom", name=name+"_look", contype="0", conaffinity="0", mass="0", group="1",
                      rgba=rgba, **geom)

    wood = dict(rgba=".75 .6 .4 1")
    for name, center, half in fixture_boxes(lay):
        ET.SubElement(world, "geom", name=name, type="box", pos=_v(center), size=_v(half), **wood)
        look(world, name, COLOURS["fixture"], type="box", pos=_v(center), size=_v(half))

    q = chain_points(lay, links)

    ring = ET.SubElement(world, "body", name="ring", pos=_v([0, 0, lay.ring_z]), quat=_quat(R.identity()))
    ET.SubElement(ring, "freejoint", name="ring")
    th = np.arange(RING_SEGMENTS+1)*2*np.pi/RING_SEGMENTS
    c = lay.ring_major_radius_m*np.column_stack([np.cos(th), np.sin(th), np.zeros_like(th)])
    big, small = lay.ring_major_radius_m, lay.ring_tube_radius_m
    mass = WOOD_KG_M3*2*np.pi**2*big*small**2                 # a torus
    ET.SubElement(ring, "inertial", pos="0 0 0", mass=str(mass),
                  diaginertia=_v(mass*np.r_[big**2/2+5*small**2/8, big**2/2+5*small**2/8, big**2+3*small**2/4]))
    for j in range(RING_SEGMENTS):
        ET.SubElement(ring, "geom", name=f"ring_{j}", type="capsule", fromto=_v([c[j], c[j+1]]),
                      size=str(lay.ring_tube_radius_m), rgba=".45 .2 .1 1")
        look(ring, f"ring_{j}", COLOURS["ring"], type="capsule", fromto=_v([c[j], c[j+1]]), size=str(lay.ring_tube_radius_m))

    tube = (lay.bead_radius_m-lay.bead_hole_radius_m)/2
    th = np.arange(BORE_SEGMENTS+1)*2*np.pi/BORE_SEGMENTS
    loop = (lay.bead_hole_radius_m+tube)*np.column_stack([np.cos(th), np.sin(th), np.zeros_like(th)])
    controls = lay.cord_controls()
    for side, k in zip(("left", "right"), lay.bead_controls()):
        pos, rot = controls[k], R.align_vectors([controls[k+1]-controls[k-1]], [[0., 0., 1.]])[0]
        bead = ET.SubElement(world, "body", name=f"bead_{side}", pos=_v(pos), quat=_quat(rot))
        ET.SubElement(bead, "freejoint", name=f"bead_{side}")
        ET.SubElement(bead, "geom", name=f"bead_{side}", type="sphere", size=str(lay.bead_radius_m),
                      mass=str(WOOD_KG_M3*4/3*np.pi*(lay.bead_radius_m**2-lay.bead_hole_radius_m**2)**1.5),  # bored
                      contype="2", conaffinity="2", rgba=".9 .8 .6 .6")
        look(bead, f"bead_{side}", COLOURS["bead"], type="sphere", size=str(lay.bead_radius_m))
        for j in range(BORE_SEGMENTS):
            ET.SubElement(bead, "geom", name=f"bead_{side}_bore{j}", type="capsule", fromto=_v([loop[j], loop[j+1]]),
                          size=str(tube), contype="1", conaffinity="1", mass="0", rgba=".9 .8 .6 1")

    th = np.arange(DISC_SIDES)*2*np.pi/DISC_SIDES
    rim = np.column_stack([lay.disc_radius_m*np.cos(th), lay.disc_radius_m*np.sin(th)])
    h = lay.disc_thickness_m/2
    ET.SubElement(asset, "mesh", name="disc", vertex=_v([[x, y, z] for z in (-h, h) for x, y in rim]))
    disc = dict(type="mesh", mesh="disc", rgba=".45 .2 .1 1")
    cord = dict(type="capsule", size=str(lay.rope_radius_m), contype="1", conaffinity="1", rgba=".95 .78 .3 1")
    link_mass = lambda length: str(CORD_KG_M3*np.pi*lay.rope_radius_m**2*length)          # the cylinder only
    joint = dict(type="ball", damping=str(JOINT_DAMPING), armature="1e-6")
    eye = np.asarray(EYE_LOCAL_M)

    def branch(parent, rot_parent, pos, indices, forward):
        """Links along `indices`, each a child of the previous; returns the last body, its rotation and end point."""
        for i in indices:
            a, b = (q[i], q[i+1]) if forward else (q[i+1], q[i])
            length = float(np.linalg.norm(b-a))
            rot = R.align_vectors([b-a], [[1., 0., 0.]])[0]
            body = ET.SubElement(parent, "body", name=f"link_{i:03d}", pos=_v(pos), quat=_quat(rot_parent.inv()*rot))
            ET.SubElement(body, "joint", name=f"bend_{i:03d}", **joint)
            ET.SubElement(body, "geom", name=f"cord_{i:03d}", fromto=_v([0, 0, 0, length, 0, 0]), mass=link_mass(length),
                          **cord)
            look(body, f"cord_{i:03d}", COLOURS["links"][i % 2], type="capsule", fromto=_v([0, 0, 0, length, 0, 0]),
                 size=str(lay.rope_radius_m))
            parent, rot_parent, pos = body, rot, np.array([length, 0., 0.])
        return parent, rot_parent, pos

    def hang_disc(parent, rot_parent, pos, side):
        rel = rot_parent.inv()*R.identity()     # composed: the reset's authored floats (inv() alone differs in the last bits)
        body = ET.SubElement(parent, "body", name=f"disc_{side}", pos=_v(pos-rel.apply(eye)), quat=_quat(rel))
        ET.SubElement(body, "joint", name=f"disc_{side}_ball", pos=_v(eye), **joint)
        ET.SubElement(body, "geom", name=f"disc_{side}", **disc)
        look(body, f"disc_{side}", COLOURS["disc"], type="mesh", mesh="disc")

    k = links//2
    length = float(np.linalg.norm(q[k+1]-q[k]))
    rot = R.align_vectors([q[k+1]-q[k]], [[1., 0., 0.]])[0]
    middle = ET.SubElement(world, "body", name=f"link_{k:03d}", pos=_v(q[k]), quat=_quat(rot))
    ET.SubElement(middle, "freejoint", name="root")
    ET.SubElement(middle, "geom", name=f"cord_{k:03d}", fromto=_v([0, 0, 0, length, 0, 0]), mass=link_mass(length),
                  **cord)
    look(middle, f"cord_{k:03d}", COLOURS["links"][k % 2], type="capsule", fromto=_v([0, 0, 0, length, 0, 0]),
         size=str(lay.rope_radius_m))
    hang_disc(*branch(middle, rot, np.array([length, 0., 0.]), range(k+1, links), True), "right")
    hang_disc(*branch(middle, rot, np.zeros(3), range(k-1, -1, -1), False), "left")
    contact = ET.SubElement(root, "contact")
    for side, near in (("left", range(3)), ("right", range(links-3, links))):
        for i in near:
            ET.SubElement(contact, "exclude", body1=f"disc_{side}", body2=f"link_{i:03d}")
    ET.indent(root)
    return ET.tostring(root, encoding="unicode"), q

