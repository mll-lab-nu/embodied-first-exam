"""Are the spherical-joint drives (stiffness/damping/armature) actually applied? Read back the
PhysX DOF properties and run a gravity-free uncurl test with three ropes:
 R0 k=1e-3 c=1e-4, R1 k=0 c=0, R2 k=1e-3 c=1e-2 (all armature 1e-6)."""
import argparse, json, os, sys
from isaaclab.app import AppLauncher
p = argparse.ArgumentParser(); AppLauncher.add_app_launcher_args(p)
args = p.parse_args(); args.headless = True
app = AppLauncher(args).app
import numpy as np, torch
import isaaclab.sim as sim_utils
from isaaclab.assets import Articulation, ArticulationCfg
from isaaclab.actuators import ImplicitActuatorCfg
from yamlab.envs.tasks.knot_untying_lib import rope_geom as G
from yamlab.envs.tasks.knot_untying_lib.rope_usd import write_rope_usd
os.makedirs("pd", exist_ok=True)
n, d = 30, 0.01
m = 650 * np.pi * 0.004 ** 2 * d
sim = sim_utils.SimulationContext(sim_utils.SimulationCfg(dt=1 / 120.0, device="cpu", gravity=(0.0, 0.0, -1e-6),
    physx=sim_utils.PhysxCfg(min_position_iteration_count=16, min_velocity_iteration_count=1)))
V = [(1e-3, 1e-4, "spherical"), (0.0, 0.0, "d6"), (1e-3, 1e-2, "d6"), (1e-3, 1e-4, "d6")]
ropes = []
for i, (k, c, jt) in enumerate(V):
    pts = np.column_stack((np.arange(n + 1) * d, np.full(n + 1, 0.5 * i), np.full(n + 1, 1.0)))
    cc, qq = G.link_frames(pts)
    usd = os.path.abspath(f"pd/r{i}.usda")
    write_rope_usd(usd, cc, qq, d, 0.004, m, joint_type=jt)
    r = Articulation(ArticulationCfg(prim_path=f"/World/R{i}", spawn=sim_utils.UsdFileCfg(usd_path=usd),
        init_state=ArticulationCfg.InitialStateCfg(pos=(0, 0, 0)),
        actuators={"all": ImplicitActuatorCfg(joint_names_expr=[".*"], stiffness=k, damping=c, armature=1e-6)}))
    ropes.append(r)
sim.reset()
for i, r in enumerate(ropes):
    v = r.root_physx_view
    print("READBACK", i, V[i], "names", r.joint_names[:3], "stiff", np.unique(v.get_dof_stiffnesses().numpy().round(8))[:4], "damp", np.unique(v.get_dof_dampings().numpy().round(8))[:4],
          "arm", np.unique(v.get_dof_armatures().numpy().round(9))[:4], "data.stiff", float(r.data.joint_stiffness.max()), "data.damp", float(r.data.joint_damping.max()))
    jp = torch.zeros(1, r.num_joints)
    for j, nm in enumerate(r.joint_names):
        if nm.endswith(":2"):
            jp[0, j] = 0.15   # curl about z
    r.write_joint_state_to_sim(jp, torch.zeros_like(jp))
    r.set_joint_position_target(torch.zeros_like(jp))
sim.forward()
for r in ropes: r.update(1 / 120)
for step in range(121):
    if step % 10 == 0:
        out = []
        for r in ropes:
            out.append(round(float(r.data.joint_pos[0].abs().max()), 4))
        print("T", step / 120, "max |joint| per rope", out)
    for r in ropes: r.write_data_to_sim()
    sim.step(render=False)
    for r in ropes: r.update(1 / 120)
sys.stdout.flush(); os._exit(0)
