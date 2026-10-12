"""Probe the PhysX spherical-joint coordinate convention: which joint positions reproduce the
authored (knotted) link poses. Also measures raw physics speed of the 99-link chain."""
import argparse, itertools, json, os, sys, time
from isaaclab.app import AppLauncher
p = argparse.ArgumentParser()
p.add_argument("--tier", default="very_easy"); p.add_argument("--n_links", type=int, default=99)
p.add_argument("--iters", type=int, default=32); p.add_argument("--out", default="pj")
AppLauncher.add_app_launcher_args(p)
args = p.parse_args(); args.headless = True
app = AppLauncher(args).app
import numpy as np, torch
import isaaclab.sim as sim_utils
from isaaclab.assets import Articulation, ArticulationCfg
from isaaclab.actuators import ImplicitActuatorCfg
from yamlab.envs.tasks.knot_untying_lib import rope_geom as G
from yamlab.envs.tasks.knot_untying_lib.rope_usd import write_rope_usd
from yamlab.robot.yam import YAM_STATION_ONLY_DIR
from scipy.spatial.transform import Rotation as Rot

os.makedirs(args.out, exist_ok=True)
pts, d, L = G.chain_from_tier(args.tier, args.n_links)
centres, quats = G.link_frames(pts)
m = G.ROPE_RHO * np.pi * G.ROPE_RADIUS ** 2 * d
usd = os.path.abspath(os.path.join(args.out, f"rope.usda"))
write_rope_usd(usd, centres, quats, d, G.ROPE_RADIUS, m, pos_iters=args.iters)
sim = sim_utils.SimulationContext(sim_utils.SimulationCfg(dt=1 / 120.0, device="cpu",
    physx=sim_utils.PhysxCfg(min_position_iteration_count=16, min_velocity_iteration_count=1)))
cfg_ws = sim_utils.UsdFileCfg(usd_path=os.path.join(YAM_STATION_ONLY_DIR, "workstation.usd"),
    rigid_props=sim_utils.RigidBodyPropertiesCfg(kinematic_enabled=True), collision_props=sim_utils.CollisionPropertiesCfg())
cfg_ws.func("/World/Workstation", cfg_ws)
rope = Articulation(ArticulationCfg(prim_path="/World/Rope", spawn=sim_utils.UsdFileCfg(usd_path=usd),
    init_state=ArticulationCfg.InitialStateCfg(pos=(0, 0, 0)),
    actuators={"rope": ImplicitActuatorCfg(joint_names_expr=[".*"], stiffness=1e-3, damping=2e-5)}))
sim.reset()
order = np.array([rope.body_names.index(f"link_{i:03d}") for i in range(args.n_links)])
root = int(rope.body_names[0].split("_")[1])
print("ROOT_LINK", root)
qs = quats[:, [1, 2, 3, 0]]  # xyzw for scipy
rel = []
for i in range(args.n_links - 1):
    rel.append((Rot.from_quat(qs[i]).inv() * Rot.from_quat(qs[i + 1])).as_rotvec())
rel = np.array(rel)
jn = rope.joint_names
def joint_vec(perm, sA, sB):
    out = np.zeros(len(jn))
    for k, name in enumerate(jn):
        base, ax = name.split(":")
        i = int(base[2:]); ax = int(ax)
        sgn = sA if i < root else sB
        out[k] = sgn * rel[i][perm[ax]]
    return out
root_pose = np.r_[centres[root], quats[root]]
res = []
for perm in itertools.permutations(range(3)):
    for sA in (1, -1):
        for sB in (1, -1):
            jp = torch.tensor(joint_vec(perm, sA, sB), dtype=torch.float32)[None]
            rope.write_root_pose_to_sim(torch.tensor(root_pose, dtype=torch.float32)[None])
            rope.write_root_velocity_to_sim(torch.zeros(1, 6))
            rope.write_joint_state_to_sim(jp, torch.zeros_like(jp))
            sim.forward(); rope.update(0.0)
            pos = rope.data.body_link_pos_w[0].numpy()[order]
            err = np.abs(pos - centres).max(axis=1)
            res.append((float(err.max()), perm, sA, sB, float(err[:root].max()), float(err[root:].max())))
res.sort(key=lambda r: r[0])
for r in res[:6]:
    print("CONV", r)
best = res[0]
json.dump(dict(root=root, best=dict(err=best[0], perm=best[1], sA=best[2], sB=best[3])), open(os.path.join(args.out, "conv.json"), "w"))
# raw physics speed from the authored pose (with the best convention)
jp = torch.tensor(joint_vec(best[1], best[2], best[3]), dtype=torch.float32)[None]
rope.write_root_pose_to_sim(torch.tensor(root_pose, dtype=torch.float32)[None]); rope.write_root_velocity_to_sim(torch.zeros(1, 6))
rope.write_joint_state_to_sim(jp, torch.zeros_like(jp)); sim.forward(); rope.update(0.0)
t = time.time()
for k in range(240):
    rope.write_data_to_sim(); sim.step(render=False); rope.update(1 / 120)
w = time.time() - t
pos = rope.data.body_link_pos_w[0].numpy()[order]; quat = rope.data.body_link_quat_w[0].numpy()[order]
j, gaps = G.chain_points_from_links(pos, quat, d)
cr = G.crossings_fast(j)
print("PHYS_STEPS_PER_S", 240 / w, "after 2s crossings", len(cr), G.over_under_sequence(cr), "gaps max", gaps.max())
sys.stdout.flush(); os._exit(0)  # Kit shutdown can hang
