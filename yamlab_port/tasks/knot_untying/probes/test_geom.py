"""Check the vectorised predicate helpers against the copied reference ones (pure numpy)."""
import numpy as np, time
import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "overlay", "yamlab", "envs", "tasks", "knot_untying_lib")); import rope_geom as G
rng = np.random.default_rng(0)
for tier in ["very_easy", "easier"]:
    pts, d, L = G.chain_from_tier(tier, 99 if tier == "very_easy" else 111)
    c, q = G.link_frames(pts)
    sp, s = G.stations_points(c, q, d)
    assert G.planar_clearance(sp, s, .008) == G.planar_clearance_fast(sp, s, .008)
    a, b = G.crossings(pts), G.crossings_fast(pts)
    assert [(x["i"], x["j"], x["first_over"]) for x in a] == [(x["i"], x["j"], x["first_over"]) for x in b]
n_ok = 0
for trial in range(300):
    # random smooth-ish planar curves, some crossing, some clear
    n = 60
    ang = np.cumsum(rng.normal(0, rng.uniform(0.05, 0.5), n))
    xy = np.cumsum(np.column_stack((np.cos(ang), np.sin(ang))) * 0.01, 0)
    P = np.column_stack((xy, np.zeros(n)))
    S = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    r1, r2 = G.planar_clearance(P, S, .008), G.planar_clearance_fast(P, S, .008)
    assert r1[0] == r2[0], (trial, r1, r2)
    m1, m2 = r1[1]["minimum_nonlocal_distance_m"], r2[1]["minimum_nonlocal_distance_m"]
    assert (m1 is None and m2 is None) or abs(m1 - m2) < 1e-12, (m1, m2)
    n_ok += r1[0]
t = time.time(); [G.planar_clearance_fast(sp, s, .008) for _ in range(20)]; tf = (time.time() - t) / 20
t = time.time(); G.planar_clearance(sp, s, .008); tr = time.time() - t
print("OK equivalence; clear cases", n_ok, "/300; fast %.2f ms, reference %.1f ms" % (tf * 1e3, tr * 1e3))
