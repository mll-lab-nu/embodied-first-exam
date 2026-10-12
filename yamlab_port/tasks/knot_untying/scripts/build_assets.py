"""Build the KnotUntying rope asset for a tier: USD articulation + settled start state.

1. Old start centreline (table frame mm) -> YAM world via rope_geom.RELAYOUT, chord-walk into
   N equal links (rope_params.N_LINKS).
2. Write knot_untying_lib/assets/<tier>/rope.usda (rope_usd.write_rope_usd, rope_params.ROPE).
3. Standalone sim (CPU PhysX, dt 1/120, YAMLab workstation table, same per-asset parameters and
   drives as the task cfg): set the knotted pose through the spherical-joint coordinates, settle
   --settle_s seconds under gravity, then save start_state.npz (root state + joint coordinates +
   link poses) and rope_meta.json (with the settled crossing count / over-under order, which must
   match start_state.md of the old task).

Usage (vast): vrun.sh 900 scripts/build_assets.py --tier very_easy [--out_dir <dir>]
"""
import argparse, json, os, sys, time
from isaaclab.app import AppLauncher

p = argparse.ArgumentParser()
p.add_argument("--tier", default="very_easy")
p.add_argument("--settle_s", type=float, default=6.0)
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
from yamlab.envs.tasks.knot_untying_lib import rope_geom as G, rope_params as RP
from yamlab.envs.tasks.knot_untying_lib.rope_usd import write_rope_usd
import yamlab.envs.tasks.knot_untying_manager_cfg as KC

tier = args.tier
out = args.out_dir or os.path.join(KC.ASSET_ROOT, tier)
os.makedirs(out, exist_ok=True)
n = RP.N_LINKS[tier]
pts, d, L = G.chain_from_tier(tier, n)
centres, quats = G.link_frames(pts)
m = RP.RHO * np.pi * RP.RADIUS ** 2 * d
P = RP.ROPE
usd = os.path.join(out, "rope.usda")
write_rope_usd(usd, centres, quats, d, RP.RADIUS, m, friction=P["friction"], contact_offset=P["contact_offset"],
               rest_offset=P["rest_offset"], linear_damping=P["linear_damping"], angular_damping=P["angular_damping"],
               max_depenetration_velocity=P["max_depenetration_velocity"], pos_iters=P["solver_position_iterations"],
               vel_iters=P["solver_velocity_iterations"])
meta = dict(tier=tier, n_links=n, link_length_m=d, rope_length_m=L, radius_m=RP.RADIUS, mass_per_link_kg=m,
            bend_stiffness_Nm_per_rad=RP.bend_stiffness(d), twist_stiffness_Nm_per_rad=RP.twist_stiffness(d),
            rope_params=P, relayout=G.RELAYOUT[tier])
R2, t2 = G.relayout_transform(tier)
meta["relayout_matrix_xy"] = R2.tolist(); meta["relayout_translation_xy_m"] = t2.tolist()
json.dump(meta, open(os.path.join(out, "rope_meta.json"), "w"), indent=1)

sim = sim_utils.SimulationContext(sim_utils.SimulationCfg(dt=1 / 120.0, device="cpu",
    physx=sim_utils.PhysxCfg(min_position_iteration_count=16, min_velocity_iteration_count=1)))
ws = sim_utils.UsdFileCfg(usd_path=os.path.join(YAM_STATION_ONLY_DIR, "workstation.usd"),
                          rigid_props=sim_utils.RigidBodyPropertiesCfg(kinematic_enabled=True),
                          collision_props=sim_utils.CollisionPropertiesCfg())
ws.func("/World/envs/env_0/Workstation", ws)
cfg = KC.rope_cfg(tier).replace(prim_path="/World/envs/env_0/Rope")
cfg.spawn.usd_path = usd
rope = Articulation(cfg)
sim.reset()
order = np.array([rope.body_names.index(f"link_{i:03d}") for i in range(n)])
root = int(rope.body_names[0].split("_")[1])
jp = torch.tensor(G.joint_positions_from_links(quats, rope.joint_names), dtype=torch.float32)[None]
rope.write_root_pose_to_sim(torch.tensor(np.r_[centres[root], quats[root]], dtype=torch.float32)[None])
rope.write_root_velocity_to_sim(torch.zeros(1, 6))
rope.write_joint_state_to_sim(jp, torch.zeros_like(jp))
rope.set_joint_position_target(torch.zeros_like(jp))
sim.forward(); rope.update(0.0)
pos0 = rope.data.body_link_pos_w[0].numpy()[order]
print("INIT_POS_ERR", float(np.abs(pos0 - centres).max()))


def snap():
    pos = rope.data.body_link_pos_w[0].numpy()[order]; quat = rope.data.body_link_quat_w[0].numpy()[order]
    lv = rope.data.body_link_lin_vel_w[0].numpy()[order]; av = rope.data.body_link_ang_vel_w[0].numpy()[order]
    return pos, quat, lv, av


steps = int(round(args.settle_s * 120))
log = []
for k in range(steps + 1):
    if k % 12 == 0:
        pos, quat, lv, av = snap()
        ok, dg = G.evaluate(pos, quat, lv, av, d, table_z=0.75)
        log.append(dict(t=k / 120, vmax=dg["maximum_speed_m_s"], n_cr=dg["n_crossings"], ou=dg["over_under"]))
    if k < steps:
        rope.write_data_to_sim(); sim.step(render=False); rope.update(1 / 120)
pos, quat, lv, av = snap()
ok, dg = G.evaluate(pos, quat, lv, av, d, table_z=0.75)
joints, gaps = G.chain_points_from_links(pos, quat, d)
cr = G.crossings_fast(joints)
exp = G.expected_knot(tier)
meta.update(settled_over_under=dg["over_under"], settled_crossings=len(cr), expected_over_under=exp["over_under_along_rope"],
            order_matches=dg["over_under"] == exp["over_under_along_rope"], settle_s=args.settle_s,
            settled_crossing_height_gaps_mm=[round((c["zi"] - c["zj"]) * 1000, 2) for c in cr],
            settled_crossing_xy=[c["xy"] for c in cr], settled_vmax_m_s=dg["maximum_speed_m_s"],
            settled_min_nonlocal_m=dg["minimum_nonlocal_distance_m"], settle_log=log[::5])
json.dump(meta, open(os.path.join(out, "rope_meta.json"), "w"), indent=1)
np.savez(os.path.join(out, "start_state.npz"), root_state=rope.data.root_state_w[0].numpy(),
         joint_pos=rope.data.joint_pos[0].numpy(), joint_names=np.array(rope.joint_names),
         link_pos=pos, link_quat=quat, link_length=d)
print("BUILD", json.dumps({k: meta[k] for k in ("tier", "n_links", "link_length_m", "settled_over_under", "expected_over_under",
                                                 "order_matches", "settled_crossing_height_gaps_mm", "settled_vmax_m_s")}))
sys.stdout.flush(); os._exit(0)  # Kit shutdown can hang
