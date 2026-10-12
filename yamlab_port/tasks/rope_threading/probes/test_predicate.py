"""Synthetic checks of the ported threading predicate (pure numpy; no Isaac). Polylines are built in the
easy scene (YAM world) and run through threading_geom.threading_check:
  correct route (R1 then R2, right directions)            -> threaded
  wrong order (R2 then R1)                                  -> not threaded
  wrong direction at R1 (R1+)                               -> not threaded
  R1 skipped (rope passes over R1)                          -> not threaded (sequence [R2+])
  extra crossing (R1 twice)                                 -> not threaded
  rope through R1 but grazing the rim (centre 66.5 mm off) -> not threaded (thickness), passes the release profile
Usage: python test_predicate.py <path to rope_threading_lib>
"""
import importlib.util, sys
import numpy as np

lib = sys.argv[1]
spec = importlib.util.spec_from_file_location("threading_geom", f"{lib}/threading_geom.py")
TH = importlib.util.module_from_spec(spec); spec.loader.exec_module(TH)
scn = TH.scene("easy")
rg = {r["name"]: r for r in scn["rings"]}
c1, c2 = rg["R1"]["center"], rg["R2"]["center"]
n1, n2 = rg["R1"]["normal"], rg["R2"]["normal"]
print("R1", np.round(c1, 4), n1, "R2", np.round(c2, 4), n2, "order", scn["order"])


def poly(*knots, step=0.01):
    out = [np.asarray(knots[0], float)]
    for a, b in zip(knots[:-1], knots[1:]):
        a, b = np.asarray(a, float), np.asarray(b, float)
        k = max(2, int(np.ceil(np.linalg.norm(b - a) / step)))
        out.extend(a + (b - a) * (i / k) for i in range(1, k + 1))
    return np.array(out)


table = np.array([0.0, 0.0, -0.30])
# material start -> end: comes from +y of R1, travels -y through R1 (R1-), then -x through R2 (R2+)
good = poly(c1 + [0.1, 0.35, -0.3], c1 + [0, 0.15, 0], c1 + [0, -0.12, 0], c2 + [0.15, 0, 0], c2 + [-0.15, 0, 0], c2 + [-0.15, 0, -0.3])
wrong_order = poly(c2 + [-0.15, 0, -0.3], c2 + [-0.15, 0, 0], c2 + [0.15, 0, 0], c1 + [0, -0.12, 0], c1 + [0, 0.15, 0], c1 + [0.1, 0.35, -0.3])
wrong_dir = poly(c1 + [0.1, -0.35, -0.3], c1 + [0, -0.15, 0], c1 + [0, 0.12, 0], c1 + [0.2, 0.12, 0], c2 + [0.15, 0, 0], c2 + [-0.15, 0, 0])
over_r1 = poly(c1 + [0.1, 0.35, -0.3], c1 + [0, 0.15, 0.2], c1 + [0, -0.12, 0.2], c2 + [0.15, 0, 0], c2 + [-0.15, 0, 0], c2 + [-0.15, 0, -0.3])
twice = poly(c1 + [0.1, 0.35, -0.3], c1 + [0, 0.15, 0], c1 + [0, -0.12, 0], c1 + [0, -0.12, 0.2], c1 + [0, 0.15, 0.2],
             c1 + [0, 0.15, -0.01], c1 + [0, -0.12, -0.01], c2 + [0.15, 0, 0], c2 + [-0.15, 0, 0])
graze = poly(c1 + [0.1, 0.35, -0.3], c1 + [0, 0.15, -0.0655], c1 + [0, -0.12, -0.0655], c2 + [0.15, 0, 0], c2 + [-0.15, 0, 0], c2 + [-0.15, 0, -0.3])
cases = dict(good=(good, True), wrong_order=(wrong_order, False), wrong_dir_R1=(wrong_dir, False), over_R1=(over_r1, False),
             R1_twice=(twice, False), graze_rim=(graze, False))
ok_all = True
for name, (pts, expect) in cases.items():
    thr, d = TH.threading_check(pts, scn["rings"], scn["order"])
    rel, rd = TH.threading_check(pts, scn["rings"], scn["order"], params=TH.RELEASE)
    ok = thr == expect
    ok_all &= ok
    print(f"{'PASS' if ok else 'FAIL'} {name:12s} threaded={thr} seq={d['crossing_sequence']} thickness={d['thickness_clear']} "
          f"release_threaded={rel}")
print("ALL_PASS" if ok_all else "SOME_FAIL")
