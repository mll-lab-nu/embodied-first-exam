"""Several rope variants side by side on the YAMLab workstation table copies? No: on one big
ground plane (z=0), offset in x/y, to compare rest jitter / settling of rope parameters in one
process. Each variant = own articulation USD with its own per-asset properties."""
import argparse, json, os, sys, time
from isaaclab.app import AppLauncher
p = argparse.ArgumentParser()
p.add_argument("--tier", default="very_easy"); p.add_argument("--n_links", type=int, default=99)
p.add_argument("--steps", type=int, default=960); p.add_argument("--out", default="sw")
p.add_argument("--variants", default="variants.json")
AppLauncher.add_app_launcher_args(p)
args = p.parse_args(); args.headless = True
app = AppLauncher(args).app
import numpy as np, torch
import isaaclab.sim as sim_utils
from isaaclab.assets import Articulation, ArticulationCfg
from isaaclab.actuators import ImplicitActuatorCfg
from yamlab.envs.tasks.knot_untying_lib import rope_geom as G
from yamlab.envs.tasks.knot_untying_lib.rope_usd import write_rope_usd
os.makedirs(args.out, exist_ok=True)
V = json.load(open(args.variants))
pts, d, L = G.chain_from_tier(args.tier, args.n_links)
m = G.ROPE_RHO * np.pi * G.ROPE_RADIUS ** 2 * d
sim = sim_utils.SimulationContext(sim_utils.SimulationCfg(dt=1 / 120.0, device="cpu",
    physx=sim_utils.PhysxCfg(min_position_iteration_count=16, min_velocity_iteration_count=1)))
gp = sim_utils.GroundPlaneCfg(physics_material=sim_utils.RigidBodyMaterialCfg(static_friction=0.5, dynamic_friction=0.5))
gp.func("/World/ground", gp)
ropes, offs = [], []
for vi, v in enumerate(V):
    off = np.array([1.0 * (vi % 4), 1.0 * (vi // 4), -G.TABLE_Z])
    P = pts + off
    c, q = G.link_frames(P)
    usd = os.path.abspath(os.path.join(args.out, f"rope_{vi}.usda"))
    write_rope_usd(usd, c, q, d, G.ROPE_RADIUS, m * v.get("mass_scale", 1.0), friction=v.get("friction", 0.3),
                   pos_iters=v.get("iters", 32), vel_iters=v.get("vel_iters", 4), linear_damping=v.get("lin", 0.0),
                   angular_damping=v.get("ang", 0.0), contact_offset=v.get("co", 0.002), sleep_threshold=v.get("sleep", 0.0),
                   max_depenetration_velocity=v.get("depen", 0.5))
    r = Articulation(ArticulationCfg(prim_path=f"/World/Rope{vi}", spawn=sim_utils.UsdFileCfg(usd_path=usd),
        init_state=ArticulationCfg.InitialStateCfg(pos=(0, 0, 0)),
        actuators={"bend": ImplicitActuatorCfg(joint_names_expr=[".*:1", ".*:2"], stiffness=v.get("k", 1e-3), damping=v.get("c", 2e-5), armature=v.get("arm", 0.0)),
                   "twist": ImplicitActuatorCfg(joint_names_expr=[".*:0"], stiffness=v.get("kt", 7.7e-4), damping=v.get("c", 2e-5), armature=v.get("arm", 0.0))}))
    ropes.append((r, c, q)); offs.append(off)
sim.reset()
orders = []
for r, c, q in ropes:
    root = int(r.body_names[0].split("_")[1])
    jp = torch.tensor(G.joint_positions_from_links(q, r.joint_names), dtype=torch.float32)[None]
    r.write_root_pose_to_sim(torch.tensor(np.r_[c[root], q[root]], dtype=torch.float32)[None])
    r.write_root_velocity_to_sim(torch.zeros(1, 6)); r.write_joint_state_to_sim(jp, torch.zeros_like(jp))
    orders.append(np.array([r.body_names.index(f"link_{i:03d}") for i in range(args.n_links)]))
sim.forward()
for r, _, _ in ropes: r.update(0.0)
hist = [[] for _ in V]
prevs = [None for _ in V]
t0 = time.time()
for k in range(args.steps + 1):
    if k % 4 == 0:
        for vi, (r, _, _) in enumerate(ropes):
            o = orders[vi]
            pos = r.data.body_link_pos_w[0].numpy()[o]; quat = r.data.body_link_quat_w[0].numpy()[o]
            lv = r.data.body_link_lin_vel_w[0].numpy()[o]; av = r.data.body_link_ang_vel_w[0].numpy()[o]
            ok, dg = G.evaluate(pos, quat, lv, av, d, table_z=0.0)
            Rm = G.quat_to_mat(quat); arm = 0.5 * d * Rm[:, :, 0]
            sp = np.maximum(np.linalg.norm(lv, axis=1), np.maximum(np.linalg.norm(lv + np.cross(av, arm), axis=1), np.linalg.norm(lv - np.cross(av, arm), axis=1)))
            jts, _ = G.chain_points_from_links(pos, quat, d)
            allp = np.vstack((jts, pos))
            prev = prevs[vi]
            fd = float(np.linalg.norm(allp - prev, axis=1).max() * 30.0) if prev is not None else float("nan")
            prevs[vi] = allp
            hist[vi].append(dict(fd=fd, step=k, vmax=dg["maximum_speed_m_s"], vlin=float(np.linalg.norm(lv, axis=1).max()), argmax=int(sp.argmax()),
                                 n_cr=dg["n_crossings"], ou=dg["over_under"], zmin=dg["z_min_surface_above_table_m"], zmax=dg["z_max_surface_above_table_m"],
                                 gap=dg["max_joint_gap_m"]))
    if k < args.steps:
        for r, _, _ in ropes: r.write_data_to_sim()
        sim.step(render=False)
        for r, _, _ in ropes: r.update(1 / 120)
print("WALL", time.time() - t0)
res = []
for vi, v in enumerate(V):
    h = hist[vi]
    tail = h[-60:]
    out = dict(v=v, final_cr=h[-1]["n_cr"], final_ou=h[-1]["ou"], vmax_last2s=max(x["vmax"] for x in tail), vlin_last2s=max(x["vlin"] for x in tail),
               vmax_med_last2s=float(np.median([x["vmax"] for x in tail])), argmax_links=sorted(set(x["argmax"] for x in tail))[:8],
               t_quiet=next((x["step"] / 120 for i, x in enumerate(h) if all(y["vmax"] <= 1e-3 for y in h[i:])), None),
               zmin=h[-1]["zmin"], zmax=h[-1]["zmax"], gapmax=max(x["gap"] for x in h))
    out["fd_per_s"] = [round(max(x["fd"] for x in h[max(j,1):j+30]) * 1000, 2) for j in range(0, len(h) - 1, 30)]
    fdl = np.array([x["fd"] for x in h[-120:]])
    q = fdl <= 1e-3
    streak = best = 0
    for v_ in q:
        streak = streak + 1 if v_ else 0; best = max(best, streak)
    out["frac_quiet_last4s"] = float(q.mean()); out["longest_quiet_streak_last4s"] = int(best)
    out["fd_p99_last4s_mm"] = float(np.quantile(fdl, 0.99) * 1000)
    out["fd_med_last2s"] = float(np.median([x["fd"] for x in tail])) * 1000
    out["vmax_per_s"] = [round(max(x["vmax"] for x in h[j:j+30]) * 1000, 2) for j in range(0, len(h) - 1, 30)]
    res.append(out); print("VAR", vi, json.dumps(out))
json.dump(dict(res=res, hist=hist), open(os.path.join(args.out, "sweep.json"), "w"))
sys.stdout.flush(); os._exit(0)  # Kit shutdown can hang
