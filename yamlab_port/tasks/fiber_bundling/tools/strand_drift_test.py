"""Cable-only test: move trunk_04 along a lift profile with a PD wrench and measure strand drift in the
trunk_05 frame, for several strand-joint damping values / solver settings."""
import argparse, json, os, sys, time
from isaaclab.app import AppLauncher
p = argparse.ArgumentParser(); p.add_argument("--assets", required=True)
p.add_argument("--fiber_damping", type=float, default=None); p.add_argument("--vel_iters", type=int, default=1)
p.add_argument("--trunk_damping", type=float, default=None); p.add_argument("--hold_only", action="store_true"); p.add_argument("--link", default="trunk_04"); p.add_argument("--rot_deg", type=float, default=0.0)
AppLauncher.add_app_launcher_args(p); args = p.parse_args(); args.headless = True
app = AppLauncher(args).app
import numpy as np, torch
import isaaclab.sim as sim_utils
from isaaclab.assets import Articulation, ArticulationCfg
from isaaclab.utils.math import quat_error_magnitude, quat_box_minus
lay = json.load(open(f"{args.assets}/layout_world.json"))
sim = sim_utils.SimulationContext(sim_utils.SimulationCfg(dt=1/120, device="cpu",
        physx=sim_utils.PhysxCfg(min_position_iteration_count=16, min_velocity_iteration_count=args.vel_iters)))
cfg = sim_utils.UsdFileCfg(usd_path=f"{args.assets}/fixtures.usda"); cfg.func("/World/fixtures", cfg)
from scipy.spatial.transform import Rotation
root = lay["links"]["terminal"]; q = Rotation.from_matrix(np.array(root["R"])).as_quat()
cab = Articulation(ArticulationCfg(prim_path="/World/cable", spawn=sim_utils.UsdFileCfg(usd_path=f"{args.assets}/cable.usda"),
        init_state=ArticulationCfg.InitialStateCfg(pos=tuple(root["origin"]), rot=(q[3], q[0], q[1], q[2]), joint_pos={".*": 0.0}), actuators={}))
sim.reset()
names = cab.body_names; i4 = names.index(args.link); i5 = names.index("trunk_05")
fj = [i for i, n in enumerate(cab.joint_names) if n.startswith("fiber")]
tj = [i for i, n in enumerate(cab.joint_names) if not n.startswith("fiber")]
if args.fiber_damping is not None:
    cab.write_joint_damping_to_sim(torch.full((1, len(fj)), args.fiber_damping), joint_ids=fj)
if args.trunk_damping is not None:
    cab.write_joint_damping_to_sim(torch.full((1, len(tj)), args.trunk_damping), joint_ids=tj)
print("damping fiber", cab.root_physx_view.get_dof_dampings()[0, fj[0]].item(), "trunk", cab.root_physx_view.get_dof_dampings()[0, tj[0]].item())
tips = [names.index(n[-1]) for n in lay["fibers"]["names"]]
p0 = cab.data.body_link_pos_w[0, i4].clone(); q0 = cab.data.body_link_quat_w[0, i4].clone()
def local_tips():
    p5 = cab.data.body_link_pos_w[0, i5].numpy(); R5 = Rotation.from_quat(cab.data.body_link_quat_w[0, i5].numpy()[[1, 2, 3, 0]]).as_matrix()
    return [((cab.data.body_link_pos_w[0, t].numpy()-p5) @ R5)*1000 for t in tips]
L0 = local_tips()
m = cab.root_physx_view.get_masses()[0, i4].item()
for k in range(int(8*120)):
    t = k/120
    u = 0 if args.hold_only else min(max((t-1)/3, 0), 1); u = u*u*(3-2*u)
    target = p0+torch.tensor([0, 0, 0.035*u])
    pos = cab.data.body_link_pos_w[0, i4]; vel = cab.data.body_lin_vel_w[0, i4]
    f = m*(400*(target-pos)-40*vel)
    from isaaclab.utils.math import quat_mul, quat_from_angle_axis
    qt = quat_mul(quat_from_angle_axis(torch.tensor([float(np.radians(args.rot_deg)*u)], dtype=torch.float32), torch.tensor([[0., 0., 1.]]))[0].unsqueeze(0), q0.unsqueeze(0))[0]
    err = quat_box_minus(qt.unsqueeze(0), cab.data.body_link_quat_w[0, i4].unsqueeze(0))[0]
    I = 2e-5
    tq = I*(400*err-40*cab.data.body_ang_vel_w[0, i4])
    cab.set_external_force_and_torque(f.float().view(1, 1, 3), tq.float().view(1, 1, 3), body_ids=[i4], is_global=True)
    cab.write_data_to_sim(); sim.step(); cab.update(1/120)
    if k % 120 == 0 or k == 959:
        Lt = local_tips()
        print(f"t {t:4.1f} trunk_04 dz {(pos[2]-p0[2]).item()*1000:6.2f} mm  tip drift {[round(float(np.linalg.norm(a-b)),2) for a,b in zip(Lt,L0)]} mm")
sys.stdout.flush(); os._exit(0)
