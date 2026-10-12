"""Cable-only physics smoke test: spawn fixtures + cable articulation, step, report stability."""
import argparse, time, json
from isaaclab.app import AppLauncher
p = argparse.ArgumentParser(); p.add_argument("--assets", required=True); p.add_argument("--steps", type=int, default=600)
AppLauncher.add_app_launcher_args(p); args = p.parse_args(); args.headless = True
app = AppLauncher(args).app
import numpy as np, torch
import isaaclab.sim as sim_utils
from isaaclab.assets import Articulation, ArticulationCfg
sim = sim_utils.SimulationContext(sim_utils.SimulationCfg(dt=1/120, device="cpu",
        physx=sim_utils.PhysxCfg(min_position_iteration_count=16, min_velocity_iteration_count=1)))
cfg = sim_utils.UsdFileCfg(usd_path=f"{args.assets}/fixtures.usda"); cfg.func("/World/fixtures", cfg)
cab = Articulation(ArticulationCfg(prim_path="/World/cable", spawn=sim_utils.UsdFileCfg(usd_path=f"{args.assets}/cable.usda",
        activate_contact_sensors=True), init_state=ArticulationCfg.InitialStateCfg(joint_pos={".*": 0.0}), actuators={}))
sim.reset()
print("num_joints", cab.num_joints, "num_bodies", cab.num_bodies, "fixed_base", cab.is_fixed_base)
print("joint_names", cab.joint_names[:8], "...", cab.joint_names[-4:])
print("body_names", cab.body_names[:4], "...", cab.body_names[-3:])
print("joint damping", cab.data.default_joint_damping[0, :6].tolist(), cab.data.default_joint_damping[0, -3:].tolist())
print("joint armature", cab.data.default_joint_armature[0, :3].tolist(), cab.data.default_joint_armature[0, -3:].tolist())
m = cab.root_physx_view.get_masses()[0]; print("masses", m[:3].tolist(), m[-3:].tolist(), "total", float(m.sum()))
p0 = cab.data.body_pos_w[0].clone()
t = time.time()
for i in range(args.steps):
    sim.step(); cab.update(sim.get_physics_dt())
    if i % 120 == 0 or i == args.steps-1:
        d = (cab.data.body_pos_w[0]-p0).norm(dim=-1)
        print(f"step {i} max drift {d.max().item()*1000:.4f} mm at {cab.body_names[int(d.argmax())]}, max lin vel {cab.data.body_lin_vel_w[0].norm(dim=-1).max().item():.5f}")
print("steps/s", args.steps/(time.time()-t))
app.close()
