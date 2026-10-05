"""Kinematic ribbon states: a centerline path from the root to the tip, strands offset +-d.

Used to design and verify canonical topological states with the exact Wirtinger word
before any physical execution. Offsets are horizontal and perpendicular to the path's
horizontal direction (or +y for vertical legs), so a post on the centerline is straddled.
"""
import numpy as np


def densify(P, step=.003):
    P = np.asarray(P, float)
    out = [P[0]]
    for a, b in zip(P[:-1], P[1:]):
        k = max(1, int(np.ceil(np.linalg.norm(b-a)/step)))
        out.extend(a+(b-a)*t for t in np.linspace(0, 1, k+1)[1:])
    return np.array(out)


def ribbon(path, d=.01, tip_radius=None, offsets=None):
    """path: root ... tip. Returns a closed loop (strand a out, tip arc, strand b back)."""
    C = densify(path)
    n = len(C)
    N = np.zeros((n, 3))
    for i in range(n):
        t = C[min(i+1, n-1)]-C[max(i-1, 0)]
        h = np.array([t[0], t[1], 0.])
        if np.linalg.norm(h) < 1e-9:
            N[i] = [0, 1, 0] if i == 0 else N[i-1]
        else:
            h /= np.linalg.norm(h)
            N[i] = [-h[1], h[0], 0]
            if i > 0 and N[i] @ N[i-1] < 0:     # keep a consistent side through vertical legs
                N[i] = -N[i]
    if offsets is not None:
        N = N*np.asarray(offsets)[:, None]
    a = C+d*N
    b = C-d*N
    tip = C[-1]
    t = C[-1]-C[-2]
    t = t/np.linalg.norm(t)
    th = np.linspace(0, np.pi, 13)[1:-1]
    arc = [tip+d*(np.cos(x)*N[-1])+d*np.sin(x)*t for x in th]
    return np.vstack([a, arc, b[::-1]])


def loop_around(center, r, z, n=60):
    th = np.linspace(0, 2*np.pi, n+1)[:-1]
    return np.column_stack([center[0]+r*np.cos(th), center[1]+r*np.sin(th), np.full(n, z)])
