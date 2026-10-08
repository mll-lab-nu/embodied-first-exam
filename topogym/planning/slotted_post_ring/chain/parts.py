"""Where a hand can pinch the chain: what lies under a link, and whether the open fingers over it clear the parts."""
import numpy as np

from .motion import StageFailure

CHAIN_OPEN_M = .025       # gripper opening over a chain link
FINGER_M = (.012, .01)    # a finger's half width along the link, its thickness beyond the opening
PINCH_LINKS = 10          # a disc is lifted by one of the chain's links this near it


def support_z(lay, p):
    """Height of what lies under p: the base's top over the base, else the table."""
    on_base = abs(p[0]) < lay.base_width_m/2 and abs(p[1]) < lay.base_depth_m/2
    return lay.base_height_m if on_base else 0.


def fingers_clear(s, lay, mid, along, skip=()):
    """The open fingers' footprint over a link (a rectangle about its midpoint) misses every bead and disc (but
    `skip`)."""
    u = along[:2]/np.linalg.norm(along[:2])
    v = np.array([-u[1], u[0]])
    half = np.array([FINGER_M[0], CHAIN_OPEN_M/2+FINGER_M[1]])
    for name, radius in (("bead_left", lay.bead_radius_m), ("bead_right", lay.bead_radius_m),
                         ("disc_left", lay.disc_radius_m), ("disc_right", lay.disc_radius_m)):
        if name in skip:
            continue
        d = s.pos(name)[:2]-mid[:2]
        local = np.abs([d @ u, d @ v])
        if np.linalg.norm(np.maximum(local-half, 0.)) < radius:
            return False
    return True


def on_disc(s, lay, disc, mid, along):
    """The link (midpoint, direction) lies on the disc's upper face with the open fingers' footprint over it inside
    its rim (a finger past the rim goes down beside it and closes on the rim too: the disc slips out)."""
    c, r = s.poses[disc]
    n = r.apply([0., 0., 1.])
    n = n if n[2] > 0 else -n
    h = (mid-c) @ n
    u = along[:2]/np.linalg.norm(along[:2])
    v = np.array([-u[1], u[0]])
    half = np.array([FINGER_M[0], CHAIN_OPEN_M/2+FINGER_M[1]])
    corners = mid[:2]+np.array([sx*half[0]*u+sy*half[1]*v for sx in (-1, 1) for sy in (-1, 1)])
    return bool(abs(h-lay.disc_thickness_m/2-lay.rope_radius_m) < .004
                and np.linalg.norm(corners-c[:2], axis=1).max() < lay.disc_radius_m-.003)


def pinch_link(s, lay, disc, on_disc_ok=False, links=PINCH_LINKS):
    """The link nearest the disc's end of the chain, among its `links` nearest, that lies low (it may lie over the
    base's edge) with the fingers' footprint clear of the parts (on_disc_ok: or lying on that disc's upper face, the
    fingers on it)."""
    n = len(s.points)-1
    for k in (range(links) if disc == "disc_left" else range(n-1, n-1-links, -1)):
        a, b = s.points[k], s.points[k+1]
        mid = (a+b)/2
        skip = (disc,) if on_disc_ok and on_disc(s, lay, disc, mid, b-a) else ()
        if mid[2]-support_z(lay, mid) < .03 and fingers_clear(s, lay, mid, b-a, skip):
            return k
    raise StageFailure(f"no clear link to pinch near {disc}")
