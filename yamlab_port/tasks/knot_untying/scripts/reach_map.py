"""Numpy-only reach map (no Isaac): gripper down, fingertips 2 mm above the table, both arms.
Reads yam_kin.json (dumped by probe_kin.py). Usage: python reach_map.py yam_kin.json"""
import json, sys, os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from oracle_lib_np import YamKinNP as K, down_rotation

D = json.load(open(sys.argv[1]))
TABLE = 0.75
rng = np.random.default_rng(0)
for n in ("left_arm", "right_arm"):
    k = K.from_json(D[n]["kin"]); tool, close = np.array(D[n]["tool_l6"]), np.array(D[n]["close_l6"])
    print("REACHMAP", n, "cols y=-0.48..0.48 step 0.06; digit = number of the 4 jaw yaws (0,45,90,135 deg) reachable")
    for x in np.arange(0.32, 0.86, 0.04):
        row = ""
        for y in np.arange(-0.48, 0.49, 0.06):
            cnt = 0
            for yaw in np.radians([0, 45, 90, 135]):
                ok = False
                for flip in (0, np.pi):
                    Rd = down_rotation(tool, close, yaw + flip)
                    b = k.base[:3, 3]
                    seeds = []
                    for q2, q3, q4 in ((1.6, 1.4, -0.6), (2.2, 1.9, -1.0), (1.0, 0.8, -0.3), (2.8, 2.6, -1.3)):
                        for q6 in (-1.5, 0.0, 1.5):
                            seeds.append(np.array([np.arctan2(y - b[1], x - b[0]), q2, q3, q4, 0.0, q6]))
                    q, ep, er = k.ik(np.array([x, y, TABLE + 0.002]), Rd, seeds[0], extra_seeds=seeds[1:], early=True)
                    if ep < 0.002 and er < np.radians(2):
                        ok = True; break
                cnt += ok
            row += str(cnt) if cnt else "."
        print("   x=%.2f %s" % (x, row))
