"""Task-local correction for millimetre capsule closest-point calculations.

Genesis 1.2.1 compares a length^4 determinant with float32 epsilon. For 8 mm
segments even perpendicular axes then enter its parallel/endpoint branch,
which can miss interior contacts. Keep radii and physical tolerances unchanged;
enumerate segment boundaries and a scale-relative interior solution instead.
This changes no installed package files and must run before scene compilation.
"""
CONTACT_MODEL = "capsule_closest_points_scale_relative_v1"


def install_capsule_contact_fix():
    import genesis as gs
    import quadrants as qd
    from genesis.engine.solvers.rigid.collider import utils

    if getattr(utils, "_topogym_capsule_contact_model", None) == CONTACT_MODEL:
        return

    @qd.func
    def closest_points(p, p_end, q, q_end, EPS):
        u, v, w = p_end-p, q_end-q, p-q
        aa, ab, bb = u.dot(u), u.dot(v), v.dot(v)
        d, e = u.dot(w), v.dot(w)
        # Only truly zero-length segments need the denominator floor. Epsilon
        # is dimensionless in the relative parallel test below.
        safe_a, safe_b = qd.max(aa, 1e-20), qd.max(bb, 1e-20)
        s, t = gs.qd_float(0.), qd.math.clamp(e/safe_b, 0., 1.)
        pa, pb = p, q+t*v
        best = (pa-pb).norm_sqr()
        for k in qd.static(range(3)):
            cs, ct = gs.qd_float(0.), gs.qd_float(0.)
            if qd.static(k == 0):
                cs, ct = 1., qd.math.clamp((e+ab)/safe_b, 0., 1.)
            elif qd.static(k == 1):
                cs, ct = qd.math.clamp(-d/safe_a, 0., 1.), 0.
            else:
                cs, ct = qd.math.clamp((ab-d)/safe_a, 0., 1.), 1.
            ca, cb = p+cs*u, q+ct*v
            distance = (ca-cb).norm_sqr()
            if distance < best:
                pa, pb, best = ca, cb, distance
        denom = aa*bb-ab*ab
        if denom > 8.*EPS*aa*bb and denom > 1e-30:
            cs, ct = (ab*e-bb*d)/denom, (aa*e-ab*d)/denom
            if 0. <= cs <= 1. and 0. <= ct <= 1.:
                ca, cb = p+cs*u, q+ct*v
                if (ca-cb).norm_sqr() < best:
                    pa, pb = ca, cb
        return pa, pb

    utils.func_closest_points_on_segments = closest_points
    utils._topogym_capsule_contact_model = CONTACT_MODEL

