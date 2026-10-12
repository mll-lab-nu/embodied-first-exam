"""Build the RopeThreading assets for a tier: rope USD (capsule-chain articulation), fixtures USD
(rings/stands/bases as static colliders) and the settled start state.

Adapted from knot_untying/scripts/build_assets.py (knot_untying agent).
1. Old start centreline (table mm) -> YAM world (threading.RELAYOUT), chord-walk into N equal links.
2. rope.usda (rope_usd.write_rope_usd), fixtures.usda (fixtures_usd.write_fixtures_usd).
3. Standalone CPU PhysX sim (dt 1/120, YAMLab workstation + fixtures): write the start pose through the
   spherical-joint coordinates, drive targets = the same coordinates (rest shape = initial U, as the
   release profile's rope_reference_shape "initial"), settle --settle_s, save start_state.npz
   (root state, joint coordinates, rest joint coordinates, link poses) and rope_meta.json.

Usage (vast): vrun.sh 900 build_assets.py --tier easy
"""
import argparse, json, os, sys
from isaaclab.app import AppLauncher

p = argparse.ArgumentParser()
p.add_argument("--tier", default="easy")
p.add_argument("--settle_s", type=float, default=4.0)
p.add_argument("--out_dir", default="")
AppLauncher.add_app_launcher_args(p)
args = p.parse_args()
args.headless = True
app = AppLauncher(args).app

import numpy as np
import torch
import isaaclab.sim as sim_utils
from isaaclab.assets import Articulation
from yamlab.robot.yam import YAM_STATION_ONLY_DIR
from yamlab.envs.tasks.rope_threading_lib import rope_chain as C, rope_params as RP, threading_geom as TH
from yamlab.envs.tasks.rope_threading_lib.rope_usd import write_rope_usd
from yamlab.envs.tasks.rope_threading_lib.fixtures_usd import write_fixtures_usd
import yamlab.envs.tasks.rope_threading_manager_cfg as RC

tier = args.tier
out = args.out_dir or os.path.join(RC.ASSET_ROOT, tier)
os.makedirs(out, exist_ok=True)
scn = TH.scene(tier)
n = RP.N_LINKS
curve = TH.start_centerline_world(tier)
L = float(np.linalg.norm(np.diff(curve, axis=0), axis=1).sum())
d = L / n
pts = C.chord_walk(curve, d, n)
centres, quats = C.link_frames(pts)
m = RP.RHO * np.pi * RP.RADIUS ** 2 * d
P = RP.ROPE
usd = os.path.join(out, "rope.usda")
write_rope_usd(usd, centres, quats, d, RP.RADIUS, m, friction=P["friction"], contact_offset=P["contact_offset"],
               rest_offset=P["rest_offset"], linear_damping=P["linear_damping"], angular_damping=P["angular_damping"],
               max_depenetration_velocity=P["max_depenetration_velocity"], pos_iters=P["solver_position_iterations"],
               vel_iters=P["solver_velocity_iterations"])
fix = os.path.join(out, "fixtures.usda")
write_fixtures_usd(fix, scn, TH.RELAYOUT[tier]["yaw_deg"])
meta = dict(tier=tier, n_links=n, link_length_m=d, rope_length_m=L, radius_m=RP.RADIUS, mass_per_link_kg=m,
            E=RP.E, bend_stiffness_Nm_per_rad=RP.bend_stiffness(d), twist_stiffness_Nm_per_rad=RP.twist_stiffness(d),
            critical_damping=RP.critical_damping(d, P["armature"]), rope_params=P, relayout=TH.RELAYOUT[tier],
            table_support_z=TH.TABLE_SUPPORT_Z,
            rings=[{k: (v.tolist() if isinstance(v, np.ndarray) else v) for k, v in r.items()} for r in scn["rings"]],
            order=scn["order"])
json.dump(meta, open(os.path.join(out, "rope_meta.json"), "w"), indent=1)

sim = sim_utils.SimulationContext(sim_utils.SimulationCfg(dt=1 / 120.0, device="cpu",
    physx=sim_utils.PhysxCfg(min_position_iteration_count=16, min_velocity_iteration_count=1)))
ws = sim_utils.UsdFileCfg(usd_path=os.path.join(YAM_STATION_ONLY_DIR, "workstation.usd"),
                          rigid_props=sim_utils.RigidBodyPropertiesCfg(kinematic_enabled=True),
                          collision_props=sim_utils.CollisionPropertiesCfg())
ws.func("/World/envs/env_0/Workstation", ws)
fx = sim_utils.UsdFileCfg(usd_path=fix)
fx.func("/World/envs/env_0/Fixtures", fx)
cfg = RC.rope_cfg(tier).replace(prim_path="/World/envs/env_0/Rope")
cfg.spawn.usd_path = usd
rope = Articulation(cfg)
sim.reset()
order = np.array([rope.body_names.index(f"link_{i:03d}") for i in range(n)])
root = int(rope.body_names[0].split("_")[1])
jp_np = C.joint_positions_from_links(quats, rope.joint_names)
jp = torch.tensor(jp_np, dtype=torch.float32)[None]
rope.write_root_pose_to_sim(torch.tensor(np.r_[centres[root], quats[root]], dtype=torch.float32)[None])
rope.write_root_velocity_to_sim(torch.zeros(1, 6))
rope.write_joint_state_to_sim(jp, torch.zeros_like(jp))
rope.set_joint_position_target(jp)
sim.forward(); rope.update(0.0)
pos0 = rope.data.body_link_pos_w[0].numpy()[order]
print("INIT_POS_ERR", float(np.abs(pos0 - centres).max()))


def snap():
    pos = rope.data.body_link_pos_w[0].numpy()[order].astype(np.float64)
    quat = rope.data.body_link_quat_w[0].numpy()[order].astype(np.float64)
    return pos, quat


steps = int(round(args.settle_s * 120))
log = []
prev = None
for k in range(steps + 1):
    if k % 4 == 0:
        pos, quat = snap()
        mp = C.material_points(pos, quat, d)
        v = float(np.linalg.norm(mp - prev, axis=1).max() / (4 / 120)) if prev is not None else None
        prev = mp
        if k % 24 == 0:
            log.append(dict(t=round(k / 120, 3), vmax_fd=v, zmin=float(pos[:, 2].min()), zmax=float(pos[:, 2].max()),
                            drift=float(np.abs(pos - centres).max())))
    if k < steps:
        rope.write_data_to_sim(); sim.step(render=False); rope.update(1 / 120)
pos, quat = snap()
joints, gaps = C.chain_points_from_links(pos, quat, d)
thr, diag = TH.threading_check(joints, scn["rings"], scn["order"])
meta.update(settle_s=args.settle_s, settle_log=log, settled_drift_m=float(np.abs(pos - centres).max()),
            settled_z_range=[float(pos[:, 2].min()), float(pos[:, 2].max())], max_joint_gap_m=float(gaps.max()),
            start_threaded=thr, start_crossings=diag["crossing_sequence"])
json.dump(meta, open(os.path.join(out, "rope_meta.json"), "w"), indent=1)
np.savez(os.path.join(out, "start_state.npz"), root_state=rope.data.root_state_w[0].numpy(),
         joint_pos=rope.data.joint_pos[0].numpy(), rest_joint_pos=jp_np.astype(np.float32),
         joint_names=np.array(rope.joint_names), link_pos=pos, link_quat=quat, link_length=d)
print("BUILD", json.dumps({k: meta[k] for k in ("tier", "n_links", "link_length_m", "settled_drift_m", "settled_z_range",
                                                 "max_joint_gap_m", "start_crossings")}))
for row in log:
    print("SETTLE", row)
sys.stdout.flush(); os._exit(0)
