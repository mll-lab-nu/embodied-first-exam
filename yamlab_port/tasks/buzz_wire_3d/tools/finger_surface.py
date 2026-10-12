"""Inner surface map of a YAM finger: min x (link6 frame, left finger at q=0) over the (y, z) pad grid."""
import numpy as np
from scipy.spatial import ConvexHull
from yam_kin import YamArm


def hull_eqs(link="left_finger", q=0.0):
    arm = YamArm(base_pos=(0, 0, 0))
    T = arm.fk_all(np.zeros(6), q)
    inv = np.linalg.inv(T["link_6"])
    out = []
    for h in arm.hulls[link]:
        W = (T[link][:3, :3] @ h.T).T + T[link][:3, 3]
        L = (inv[:3, :3] @ W.T).T + inv[:3, 3]
        out.append(ConvexHull(L).equations)
    return out


def x_range(eqs, y, z):
    best = None
    for E in eqs:
        lo, hi = -1.0, 1.0
        for a in E:
            c = a[1] * y + a[2] * z + a[3]
            if abs(a[0]) < 1e-12:
                if c > 1e-12:
                    lo, hi = 1, -1
                    break
                continue
            if a[0] > 0:
                hi = min(hi, -c / a[0])
            else:
                lo = max(lo, -c / a[0])
        if lo <= hi:
            best = lo if best is None else min(best, lo)
    return best


if __name__ == "__main__":
    eqs = hull_eqs()
    ys = np.arange(-0.033, 0.034, 0.004)
    zs = np.arange(0.075, 0.146, 0.007)
    print("min x (mm) of the left finger's inner surface at q=0; rows z, cols y (mm)")
    print("      " + " ".join(f"{y*1000:5.0f}" for y in ys))
    for z in zs:
        print(f"{z*1000:5.0f} " + " ".join(f"{x_range(eqs, y, z)*1000:5.1f}" if x_range(eqs, y, z) is not None else "    ." for y in ys))
