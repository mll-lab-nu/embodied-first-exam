"""Dump collision hull vertices of link_5/link_6/fingers/cameras of the YAM USD (closed fingers, q=0)
into each link's frame computed by yam_kin, saved to gripper_hulls.npz (name -> (link, verts in link frame))."""
import sys, numpy as np
from pathlib import Path
from pxr import Usd, UsdPhysics, UsdGeom
sys.path.insert(0, str(Path(__file__).resolve().parent))
import yam_kin as yk
st = Usd.Stage.Open(sys.argv[1])
cache = UsdGeom.XformCache(0)
Ts = yk.fk_all(np.zeros(6))
link_T = {"link_5": Ts[4], "link_6": Ts[5], "left_finger": yk.finger_T(Ts[5], "left_finger", 0.0),
          "right_finger": yk.finger_T(Ts[5], "right_finger", 0.0)}
# fixed camera bodies ride on link_6
out = {}
for p in st.Traverse():
    if not (p.HasAPI(UsdPhysics.CollisionAPI) and p.IsA(UsdGeom.Mesh)):
        continue
    path = str(p.GetPath())
    anc = p
    while anc and not anc.HasAPI(UsdPhysics.RigidBodyAPI):
        anc = anc.GetParent()
    name = anc.GetPath().name
    if name not in ("link_5", "link_6", "left_finger", "right_finger", "camera_mount", "camera_d405"):
        continue
    v = np.array(UsdGeom.Mesh(p).GetPointsAttr().Get(), float)
    M = np.array(cache.GetLocalToWorldTransform(p)).T
    w = (M[:3, :3] @ v.T).T + M[:3, 3]
    link = name if name in link_T else "link_6"
    Ti = np.linalg.inv(link_T[link])
    out[path.split("/")[-1]] = (link, (Ti[:3, :3] @ w.T).T + Ti[:3, 3])
np.savez(Path(__file__).parent / "gripper_hulls.npz", **{k: v[1] for k, v in out.items()},
         _links=np.array([f"{k}:{v[0]}" for k, v in out.items()]))
# report bounds in the TCP frame for the closed and open gripper
for d in (0.0, -0.0475):
    T6 = np.eye(4)
    Ti = np.linalg.inv(yk.T6_TCP)
    allp = {}
    for k, (link, pts) in out.items():
        if link == "link_6": T = T6
        elif link == "link_5": continue
        else: T = yk.finger_T(T6, link, d)
        P = (T[:3, :3] @ pts.T).T + T[:3, 3]
        P = (Ti[:3, :3] @ P.T).T + Ti[:3, 3]
        allp.setdefault(link if "finger" in link else ("camera" if "camera" in k else "link_6"), []).append(P)
    print("finger d =", d)
    for k, L in allp.items():
        P = np.concatenate(L)
        print(f"  {k:13s} min {P.min(0).round(4)} max {P.max(0).round(4)}")
