"""Extract a numpy kinematic + collision model of one YAM arm from yam.usd (rest pose = all joints 0).

Output npz: link names, rest world transforms (in the arm-root frame), joint screw axes
(point, direction, type, limits, parent/child), collision hull vertices per link (link frame).
Run with the vast venv (pxr). Pure data extraction; nothing is modified.
"""
import sys, json
import numpy as np
from pxr import Usd, UsdGeom, UsdPhysics, Gf

usd, out = sys.argv[1], sys.argv[2]
st = Usd.Stage.Open(usd)
xc = UsdGeom.XformCache()
root = "/yam_new_gripper/arm"
def M(prim):
    m = xc.GetLocalToWorldTransform(prim)
    return np.array(m).T  # pxr is row-vector convention -> transpose to column convention
links = ["arm", "link_1", "link_2", "link_3", "link_4", "link_5", "link_6", "left_finger", "right_finger", "camera_mount", "camera_d405"]
T = {l: M(st.GetPrimAtPath(f"{root}/{l}")) for l in links}
def q2m(q):  # Gf.Quatf -> 3x3
    w = q.GetReal(); x, y, z = q.GetImaginary()
    return np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                     [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                     [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])
joints = []
for name in ["joint1", "joint2", "joint3", "joint4", "joint5", "joint6", "left_finger", "right_finger"]:
    p = st.GetPrimAtPath(f"/yam_new_gripper/joints/{name}")
    j = UsdPhysics.Joint(p)
    b0 = str(j.GetBody0Rel().GetTargets()[0]).split("/")[-1]
    b1 = str(j.GetBody1Rel().GetTargets()[0]).split("/")[-1]
    lp0 = np.array(j.GetLocalPos0Attr().Get()); lr0 = q2m(j.GetLocalRot0Attr().Get())
    lp1 = np.array(j.GetLocalPos1Attr().Get()); lr1 = q2m(j.GetLocalRot1Attr().Get())
    axis = p.GetAttribute("physics:axis").Get()
    ai = "XYZ".index(axis)
    Tj0 = T[b0] @ np.block([[lr0, lp0[:, None]], [np.zeros((1, 3)), np.ones((1, 1))]])
    Tj1 = T[b1] @ np.block([[lr1, lp1[:, None]], [np.zeros((1, 3)), np.ones((1, 1))]])
    lo = p.GetAttribute("physics:lowerLimit").Get(); hi = p.GetAttribute("physics:upperLimit").Get()
    typ = "prismatic" if p.IsA(UsdPhysics.PrismaticJoint) else "revolute"
    if typ == "revolute":
        lo, hi = np.deg2rad(lo), np.deg2rad(hi)
    joints.append(dict(name=name, parent=b0, child=b1, type=typ, point=Tj0[:3, 3].tolist(),
                       axis=Tj0[:3, ai].tolist(), lo=float(lo), hi=float(hi),
                       frame_mismatch=float(np.abs(Tj0 - Tj1).max())))
hulls = {}
for l in links:
    pts_all = []
    for p in Usd.PrimRange(st.GetPrimAtPath(f"{root}/{l}/collisions")):
        if p.GetTypeName() == "Mesh":
            pts = np.array(UsdGeom.Mesh(p).GetPointsAttr().Get(), float)
            Mw = M(p)
            pw = (Mw[:3, :3] @ pts.T).T + Mw[:3, 3]
            pl = (np.linalg.inv(T[l]) @ np.c_[pw, np.ones(len(pw))].T).T[:, :3]
            pts_all.append(pl)
    hulls[l] = pts_all
np.savez(out, links=np.array(links), T=np.stack([T[l] for l in links]),
         joints=json.dumps(joints),
         **{f"hull_{l}_{i}": h for l in links for i, h in enumerate(hulls[l])})
print(json.dumps(joints, indent=1))
for l in links:
    allp = np.concatenate(hulls[l]) if hulls[l] else np.zeros((0, 3))
    if len(allp):
        print(l, "nhull", len(hulls[l]), "link-frame bbox", allp.min(0).round(4), allp.max(0).round(4))
    print(l, "rest pos", T[l][:3, 3].round(4))
