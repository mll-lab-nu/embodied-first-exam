"""Scene-only probe of the capsule-chain rope (no robot): build, settle, measure.

Standalone Isaac Lab sim (CPU PhysX, dt 1/120, min iters 16 as YAMLab) with the YAMLab
workstation USD as the table. Reports DOF layout, whether the authored (knotted) pose is kept
at init, and settling metrics: crossings + over/under order, max speed, joint gaps, heights.
"""
import argparse, json, time, os, sys
from isaaclab.app import AppLauncher

p = argparse.ArgumentParser()
p.add_argument("--tier", default="very_easy")
p.add_argument("--n_links", type=int, default=99)
p.add_argument("--k", type=float, default=1e-3, help="bend/twist stiffness N m/rad")
p.add_argument("--c", type=float, default=2e-5, help="joint damping N m s/rad")
p.add_argument("--armature", type=float, default=0.0)
p.add_argument("--iters", type=int, default=32)
p.add_argument("--vel_iters", type=int, default=4)
p.add_argument("--lin_damp", type=float, default=0.0)
p.add_argument("--ang_damp", type=float, default=0.0)
p.add_argument("--friction", type=float, default=0.3)
p.add_argument("--sleep", type=float, default=0.0)
p.add_argument("--kt", type=float, default=7.7e-4, help="twist stiffness")
p.add_argument("--steps", type=int, default=480)
p.add_argument("--out", default="probe_out")
p.add_argument("--save_settled", default="")
AppLauncher.add_app_launcher_args(p)
args = p.parse_args()
args.headless = True
app = AppLauncher(args).app

import numpy as np
import torch
import isaaclab.sim as sim_utils
from isaaclab.assets import Articulation, ArticulationCfg
from isaaclab.actuators import ImplicitActuatorCfg
from yamlab.envs.tasks.knot_untying_lib import rope_geom as G
from yamlab.envs.tasks.knot_untying_lib.rope_usd import write_rope_usd
from yamlab.robot.yam import YAM_STATION_ONLY_DIR

os.makedirs(args.out, exist_ok=True)
pts, d, L = G.chain_from_tier(args.tier, args.n_links)
centres, quats = G.link_frames(pts)
m = G.ROPE_RHO * np.pi * G.ROPE_RADIUS ** 2 * d
usd = os.path.abspath(os.path.join(args.out, f"rope_{args.tier}_{args.n_links}.usda"))
write_rope_usd(usd, centres, quats, d, G.ROPE_RADIUS, m, friction=args.friction, pos_iters=args.iters,
               vel_iters=args.vel_iters, linear_damping=args.lin_damp, angular_damping=args.ang_damp, sleep_threshold=args.sleep)

sim = sim_utils.SimulationContext(sim_utils.SimulationCfg(
    dt=1 / 120.0, device="cpu",
    physx=sim_utils.PhysxCfg(min_position_iteration_count=16, min_velocity_iteration_count=1)))
cfg_ws = sim_utils.UsdFileCfg(usd_path=os.path.join(YAM_STATION_ONLY_DIR, "workstation.usd"),
                              rigid_props=sim_utils.RigidBodyPropertiesCfg(kinematic_enabled=True),
                              collision_props=sim_utils.CollisionPropertiesCfg())
cfg_ws.func("/World/Workstation", cfg_ws)
sim_utils.GroundPlaneCfg().func("/World/ground", sim_utils.GroundPlaneCfg())
rope = Articulation(ArticulationCfg(
    prim_path="/World/Rope",
    spawn=sim_utils.UsdFileCfg(usd_path=usd),
    init_state=ArticulationCfg.InitialStateCfg(pos=(0, 0, 0)),
    actuators={"bend": ImplicitActuatorCfg(joint_names_expr=[".*:1", ".*:2"], stiffness=args.k, damping=args.c, armature=args.armature),
               "twist": ImplicitActuatorCfg(joint_names_expr=[".*:0"], stiffness=args.kt, damping=args.c, armature=args.armature)},
))
sim.reset()
print("NUM_BODIES", rope.num_bodies, "NUM_JOINTS", rope.num_joints)
print("JOINT_NAMES_HEAD", rope.joint_names[:6], "BODY_NAMES_HEAD", rope.body_names[:3])
order = np.array([rope.body_names.index(f"link_{i:03d}") for i in range(args.n_links)])


def state():
    pos = rope.data.body_link_pos_w[0].cpu().numpy()[order]
    quat = rope.data.body_link_quat_w[0].cpu().numpy()[order]
    lv = rope.data.body_link_lin_vel_w[0].cpu().numpy()[order]
    av = rope.data.body_link_ang_vel_w[0].cpu().numpy()[order]
    return pos, quat, lv, av


# set the knotted start pose (convention from probe_joints.py)
root = int(rope.body_names[0].split("_")[1])
jp = torch.tensor(G.joint_positions_from_links(quats, rope.joint_names), dtype=torch.float32)[None]
rope.write_root_pose_to_sim(torch.tensor(np.r_[centres[root], quats[root]], dtype=torch.float32)[None])
rope.write_root_velocity_to_sim(torch.zeros(1, 6))
rope.write_joint_state_to_sim(jp, torch.zeros_like(jp))
sim.forward(); rope.update(0.0)
# table collider info
from pxr import UsdGeom, UsdPhysics, Usd
stage = sim.stage
bb = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "proxy", "guide"])
for prim in stage.Traverse():
    if str(prim.GetPath()).startswith("/World/Workstation") and prim.HasAPI(UsdPhysics.CollisionAPI):
        r = bb.ComputeWorldBound(prim).ComputeAlignedRange()
        ro = prim.GetAttribute("physxCollision:restOffset").Get() if prim.HasAttribute("physxCollision:restOffset") else None
        co = prim.GetAttribute("physxCollision:contactOffset").Get() if prim.HasAttribute("physxCollision:contactOffset") else None
        print("COLLIDER", prim.GetPath(), prim.GetTypeName(), "min", [round(v, 4) for v in r.GetMin()], "max", [round(v, 4) for v in r.GetMax()], "rest", ro, "contact", co)
pos0, quat0, _, _ = state()
init_err = float(np.abs(pos0 - centres).max())
print("INIT_POS_ERR_vs_authored_m", init_err)
jp0 = rope.data.joint_pos[0].cpu().numpy()
print("INIT_JOINT_POS absmax", float(np.abs(jp0).max()), "nonzero", int((np.abs(jp0) > 1e-4).sum()))
print("ROOT_STATE", rope.data.root_state_w[0].cpu().numpy().round(4).tolist())

log = []
t0 = time.time()
for k in range(args.steps + 1):
    if k % 4 == 0:
        pos, quat, lv, av = state()
        ok, diag = G.evaluate(pos, quat, lv, av, d)
        joints, gaps = G.chain_points_from_links(pos, quat, d)
        cr = G.crossings(joints)
        diag.update(step=k, t=k / 120, crossing_gaps_mm=[round((c["zi"] - c["zj"]) * 1000, 2) for c in cr],
                    kinetic_J=float(0.5 * m * (lv ** 2).sum()), z_centre_min=float(pos[:, 2].min() - G.TABLE_Z))
        log.append(diag)
        if k % 60 == 0:
            print(json.dumps({kk: diag[kk] for kk in ("step", "n_crossings", "over_under", "crossing_gaps_mm", "maximum_speed_m_s",
                                                      "p99_speed_m_s", "max_joint_gap_m", "z_min_surface_above_table_m",
                                                      "z_max_surface_above_table_m", "planar_clear", "kinetic_J")}))
    if k < args.steps:
        rope.write_data_to_sim()
        sim.step(render=False)
        rope.update(1 / 120.0)
wall = time.time() - t0
print("WALL_s", wall, "physics steps/s", args.steps / wall)
exp = G.expected_knot(args.tier)
last = log[-1]
summary = dict(tier=args.tier, n_links=args.n_links, d=d, L=L, mass_per_link=m, k=args.k, c=args.c, armature=args.armature,
               iters=args.iters, init_pos_err=init_err, expected=exp["over_under_along_rope"],
               final=last, crossing_order_kept=last["over_under"] == exp["over_under_along_rope"],
               max_speed_last_1s=max(x["maximum_speed_m_s"] for x in log[-30:]),
               max_gap_all=max(x["max_joint_gap_m"] for x in log))
print("SUMMARY", json.dumps(summary))
json.dump(dict(summary=summary, log=log), open(os.path.join(args.out, "probe.json"), "w"))
if args.save_settled:
    pos, quat, lv, av = state()
    np.savez(args.save_settled, root_state=rope.data.root_state_w[0].cpu().numpy(),
             joint_pos=rope.data.joint_pos[0].cpu().numpy(), joint_names=np.array(rope.joint_names),
             link_pos=pos, link_quat=quat, d=d, n_links=args.n_links)
sys.stdout.flush(); os._exit(0)  # Kit shutdown can hang
