"""Print the cable's physical properties as seen inside the YAMLab env (damping, armature, gravity, materials)."""
import argparse, os, sys
from isaaclab.app import AppLauncher
p = argparse.ArgumentParser(); AppLauncher.add_app_launcher_args(p); args = p.parse_args(); args.headless = True
app = AppLauncher(args).app
import numpy as np, torch
from yamlab.utils.task_creation import create_task_environment
env = create_task_environment(task_name="FiberBundling-VeryEasy-v0", assets_instance_paths={}, mode="evaluation",
                              observation_modalities=["proprioception"], num_envs=1, device="cpu")
env.reset()
cab = env.scene["cable"]; v = cab.root_physx_view
fj = [i for i, n in enumerate(cab.joint_names) if n.startswith("fiber")]
print("dampings fiber", v.get_dof_dampings()[0, fj[:3]].tolist(), "trunk", v.get_dof_dampings()[0, :3].tolist())
print("stiffness", v.get_dof_stiffnesses()[0, fj[:3]].tolist())
print("armature", v.get_dof_armatures()[0, fj[:3]].tolist())
print("friction", v.get_dof_friction_coefficients()[0, fj[:3]].tolist() if hasattr(v, "get_dof_friction_coefficients") else None)
print("disable gravity", v.get_disable_gravities()[0].tolist()[:3] if hasattr(v, "get_disable_gravities") else "n/a")
print("max vel", v.get_dof_max_velocities()[0, fj[:3]].tolist())
print("gravity", env.sim.cfg.gravity)
print("default joint damping (data)", cab.data.default_joint_damping[0, fj[:3]].tolist(), "joint_damping", cab.data.joint_damping[0, fj[:3]].tolist())
sys.stdout.flush(); os._exit(0)
