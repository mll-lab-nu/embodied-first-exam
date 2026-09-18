"""Kinematic-only turn alternatives from a recorded pre-turn checkpoint.

This deliberately restores saved poses for diagnosis. It is not a physical
rollout, a grasp demonstration, or proof that contacts along a turn are safe.
"""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from scipy.spatial.transform import Rotation

from .ik_search import BundleIKTrial
from .scene import FiberSceneBuilder, as_numpy, cable_state


def main():
    import genesis as gs
    from omegaconf import OmegaConf
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    folder = args.folder
    cfg = OmegaConf.load(folder/"config.yaml")
    cfg.env.cameras = {}
    cfg.env.renderer.type = "rasterizer"
    plan = json.loads((folder/"plan.json").read_text())
    data = np.load(folder/"trajectory.npz")
    commands = json.loads((folder/"robot_commands.json").read_text())
    # Take the first completed retreat immediately preceding a rolled turn.
    row = next(r for r in json.loads((folder/"phase_metrics.json").read_text()) if r["phase"] == "greedy_retreat")
    index = int(np.abs(data["time_s"]-row["time_s"]).argmin())
    command = [c for c in commands if c["time_s"] <= row["time_s"] and c["phase"] == "greedy_retreat"][-1]
    gs.init(backend=gs.cpu, logging_level="warning", performance_mode=True)
    task = FiberSceneBuilder(cfg.env,cfg.task,cfg.robot_control).build(asset_dir=folder/"turn_probe_assets")
    robot = task.manifest.get("robot")
    task.bundle.set_qpos(data["cable_qpos"][index], zero_velocity=True)
    robot.set_qpos(data["robot_qpos"][index], zero_velocity=True)
    link = task.bundle.get_link(plan["grasp_link"])
    hand = robot.get_link("hand")
    root = cable_state(task.bundle,task.layout)["roots_m"].mean(axis=0)
    r0 = Rotation.from_quat(as_numpy(link.get_quat())[[1,2,3,0]])
    head = r0.inv().apply(root-as_numpy(link.get_pos()))
    rel_hand = r0.inv().apply(as_numpy(hand.get_pos())-as_numpy(link.get_pos()))
    rel_r = r0.inv()*Rotation.from_quat(as_numpy(hand.get_quat())[[1,2,3,0]])
    desired_r = Rotation.from_quat(np.array(command["hand_target_quat_wxyz"])[[1,2,3,0]])*rel_r.inv()
    desired_root = np.array([task.ring_center[0]-.110,root[1],task.ring_center[2]+.065])
    correction = np.asarray(command["hand_target_m"])-desired_r.apply(rel_hand)-desired_root+desired_r.apply(head)
    proxy = SimpleNamespace(robot=robot,c=SimpleNamespace(ee_link=hand,arm_dofs=list(range(7))),
        last_ik_target=np.array(command["arm_joint_target"]),root_goal=desired_root,
        root_rotation=desired_r,root_correction=correction,head_from_grasp=head,
        relative_hand_p=rel_hand,relative_hand_r=rel_r,spec=dict(maximum_joint_command_step_rad=.15))
    results = []
    for height in (.065,.035):
        for side, roll in ((1.,70.),(-1.,-70.)):
            rot=Rotation.from_euler("x",roll,degrees=True)*r0
            duration=max(1.5,1.875*(rot*desired_r.inv()).magnitude()/.65)
            goal=task.ring_center+[-.110,side*.060,height]
            result=BundleIKTrial.probe_root_move(proxy,goal,rot,duration)
            results.append(dict(side=side,roll_deg=roll,height_m=height,**result))
            print(json.dumps(results[-1]),flush=True)
    (folder/"turn_probe.json").write_text(json.dumps(dict(
        scope="kinematic-only saved-pose diagnosis; zero actuator commands and zero physics steps",
        checkpoint_time_s=float(data["time_s"][index]),
        calibration="relative transforms reconstructed at the saved checkpoint; online controller must recheck",
        candidates=results),indent=2)+"\n")


if __name__ == "__main__":
    main()
