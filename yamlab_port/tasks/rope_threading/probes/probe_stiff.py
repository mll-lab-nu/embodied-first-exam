"""Stiff D6 rope check: cantilever droop of clamped capsule chains (link_000 welded to the world) vs
Euler-Bernoulli (small deflection: delta = w L^4 / (8 E I)), for several damping / armature variants.
Reports tip droop after 3 s and the finite-difference max speed of the last 0.5 s (quiet check), and
whether anything blew up. CPU PhysX, dt 1/120, 16 position iterations (YAMLab's settings).
Usage (vast): vrun.sh 600 probe_stiff.py"""
import argparse, json, os, sys
from isaaclab.app import AppLauncher
p = argparse.ArgumentParser(); AppLauncher.add_app_launcher_args(p)
args = p.parse_args(); args.headless = True
app = AppLauncher(args).app
import numpy as np, torch
import isaaclab.sim as sim_utils
from isaaclab.assets import Articulation, ArticulationCfg
from isaaclab.actuators import ImplicitActuatorCfg
from pxr import Usd, UsdPhysics, Sdf
from yamlab.envs.tasks.rope_threading_lib import rope_chain as C, rope_params as RP
from yamlab.envs.tasks.rope_threading_lib.rope_usd import write_rope_usd

os.makedirs("ps", exist_ok=True)
d = 0.01
m = RP.RHO * np.pi * RP.RADIUS ** 2 * d
kb, kt = RP.bend_stiffness(d), RP.twist_stiffness(d)
EI = RP.E * np.pi * RP.RADIUS ** 4 / 4
w = m / d * 9.81
sim = sim_utils.SimulationContext(sim_utils.SimulationCfg(dt=1 / 120.0, device="cpu",
    physx=sim_utils.PhysxCfg(min_position_iteration_count=16, min_velocity_iteration_count=1)))
V = []
for n in (12, 20):
    for arm, c in ((1e-6, 2e-4), (1e-6, 2e-3), (1e-5, 2e-3), (1e-5, 1e-2)):
        V.append(dict(n=n, armature=arm, damping=c))
ropes = []
for i, v in enumerate(V):
    n = v["n"]
    pts = np.column_stack((np.arange(n + 1) * d, np.full(n + 1, 0.3 * i), np.full(n + 1, 1.0)))
    cc, qq = C.link_frames(pts)
    usd = os.path.abspath(f"ps/r{i}.usda")
    write_rope_usd(usd, cc, qq, d, RP.RADIUS, m, joint_type="d6")
    st = Usd.Stage.Open(usd)
    fj = UsdPhysics.FixedJoint.Define(st, "/Rope/joints/clamp")
    fj.CreateBody1Rel().SetTargets([Sdf.Path("/Rope/link_000")])
    fj.CreateLocalPos0Attr().Set(tuple(map(float, cc[0])))
    st.GetRootLayer().Save()
    r = Articulation(ArticulationCfg(prim_path=f"/World/R{i}", spawn=sim_utils.UsdFileCfg(usd_path=usd),
        init_state=ArticulationCfg.InitialStateCfg(pos=(0, 0, 0)),
        actuators={"bend": ImplicitActuatorCfg(joint_names_expr=[r"j_\d+:1", r"j_\d+:2"], stiffness=kb, damping=v["damping"], armature=v["armature"]),
                   "twist": ImplicitActuatorCfg(joint_names_expr=[r"j_\d+:0"], stiffness=kt, damping=v["damping"], armature=v["armature"])}))
    ropes.append(r)
sim.reset()
orders = []
for r, v in zip(ropes, V):
    orders.append(np.array([r.body_names.index(f"link_{k:03d}") for k in range(v["n"])]))
    print("ROOT", r.body_names[0], "fixed_base", r.is_fixed_base, "stiff", float(r.data.joint_stiffness.max()), "damp", float(r.data.joint_damping.max()))
hist = {i: [] for i in range(len(V))}
T = 3.0
for step in range(int(T * 120) + 1):
    if step % 4 == 0:
        for i, r in enumerate(ropes):
            pos = r.data.body_link_pos_w[0].numpy()[orders[i]].astype(float)
            hist[i].append(pos)
    if step % 60 == 0:
        print("T", step / 120, [round(float(1000 * (1.0 - hist[i][-1][-1, 2])), 2) for i in range(len(V))])
    for r in ropes: r.write_data_to_sim()
    sim.step(render=False)
    for r in ropes: r.update(1 / 120)
res = []
for i, v in enumerate(V):
    H = np.array(hist[i])
    L = (v["n"] - 0.5) * d
    sp = np.linalg.norm(np.diff(H[-16:], axis=0), axis=2).max() / (4 / 120)
    tip = 1.0 - H[-1][-1, 2]
    res.append(dict(v, finite=bool(np.isfinite(H).all()), tip_droop_mm=round(1000 * tip, 2),
                    theory_small_mm=round(1000 * w * L ** 4 / (8 * EI), 2), vmax_last_0p5s_mm_s=round(1000 * sp, 3),
                    droop_t1_mm=round(1000 * (1.0 - H[30][-1, 2]), 2), droop_t2_mm=round(1000 * (1.0 - H[60][-1, 2]), 2)))
    print("RES", json.dumps(res[-1]))
json.dump(res, open("ps/probe_stiff.json", "w"), indent=1)
sys.stdout.flush(); os._exit(0)
