"""Headless real-robot collision regression; test placements are not a policy demo."""
import argparse
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation


def main():
    import genesis as gs
    from hydra import compose, initialize_config_dir
    from omegaconf import OmegaConf
    from topogym.utils.franka import initialize_franka_controller
    from .scene import FiberSceneBuilder, as_numpy

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=("fine", "trunk"), required=True)
    parser.add_argument("--output", type=Path,
                        default=Path("runs/environment-solvability/fiber_bundling/gripper_contact_rule"))
    args = parser.parse_args()
    output = args.output/args.target
    output.mkdir(parents=True, exist_ok=True)
    with initialize_config_dir(version_base="1.3", config_dir=str(Path(__file__).resolve().parents[3]/"configs")):
        cfg = compose(config_name="fiber_bundling_preview")
    cfg.env.genesis.backend = "cpu"
    cfg.env.renderer.type = "rasterizer"
    cfg.env.cameras = {}
    OmegaConf.save(cfg, output/"config.yaml", resolve=True)
    gs.init(backend=gs.cpu, logging_level="warning", seed=int(cfg.task.geometry.seed))
    task = FiberSceneBuilder(cfg.env, cfg.task, cfg.robot_control).build(asset_dir=output/"assets")
    controller = initialize_franka_controller(scene=task.scene, manifest=task.manifest,
                                            robot_cfg=cfg.robot_control, settle_steps=0)
    robot = task.manifest.get("robot")
    for _ in range(5):
        task.scene.step()  # Deliberately exercise the controller's raw scene API.
    before = task.state()
    base = as_numpy(robot.get_pos()).copy()
    finger = robot.get_link("left_finger")
    rot = Rotation.from_quat(as_numpy(finger.get_quat())[[1, 2, 3, 0]])
    pad_surface = as_numpy(finger.get_pos())+rot.apply([0, -.0066, .01875])
    if args.target == "fine":
        target = before["fibers_m"][0, 8:10].mean(axis=0)
        radius = task.layout.fiber_radius_m
    else:
        link = task.bundle.get_link("trunk_02")
        rotation = Rotation.from_quat(as_numpy(link.get_quat())[[1, 2, 3, 0]])
        target = as_numpy(link.get_pos())+rotation.apply([task.layout.trunk_length_m/task.layout.trunk_segments/2, 0, 0])
        radius = task.layout.trunk_radius_m
    # Test-only root translation places a real pad slightly into the selected
    # surface. No cable state writes, fake contacts or disabled collisions.
    robot.set_pos(base+target+rot.apply([0, radius*.9, 0])-pad_surface)
    task.scene.step()
    touched = task.state()
    native = task.bundle.get_contacts(with_entity=robot)
    native_pairs = list(zip(as_numpy(native["link_a"]).tolist(), as_numpy(native["link_b"]).tolist()))
    names = {link.idx: link.name for entity in (robot, task.bundle) for link in entity.links}
    pairs = [[names[a], names[b]] for a, b in native_pairs]
    robot.set_pos(base)
    controller.reset_home(settle_steps=0)
    for _ in range(5):
        task.step()
    after = task.state()
    separation = len(task.bundle.get_contacts(with_entity=robot)["link_a"]) == 0
    expected_fail = args.target == "fine"
    checks = dict(
        initially_valid=not before["failed"], native_robot_cable_contact=bool(pairs),
        contact_rule_matches_target=touched["contact_rule"]["failed"] == expected_fail,
        task_failure_matches_target=touched["failed"] == expected_fail,
        separated=separation, episode_result_latched=after["failed"] == expected_fail,
        every_substep_observed=after["contact_rule"]["observed_substeps"] == 11*int(cfg.env.sim.substeps),
    )
    if expected_fail:
        checks["terminated_on_contact"] = touched["terminated"] and not touched["success"]
    report = dict(scope="real_gripper_contact_rule_regression_only", target=args.target,
                  passed=all(checks.values()), checks=checks, native_contact_link_pairs=pairs,
                  monitored_gripper_links=list(task.contact_guard.gripper_links.values()),
                  before=before["contact_rule"], touched=touched["contact_rule"], after=after["contact_rule"],
                  final_threading=after["threading"], robot_base_test_placement=True,
                  cable_pose_writes=0, full_threading_verified=False)
    (output/"report.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps(report, indent=2), flush=True)
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
