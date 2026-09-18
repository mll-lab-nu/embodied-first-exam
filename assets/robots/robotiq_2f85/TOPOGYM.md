# TopoGym integration

Source: [MuJoCo Menagerie / robotiq_2f85](https://github.com/google-deepmind/mujoco_menagerie/tree/main/robotiq_2f85), downloaded 2026-09-14. The upstream `2f85.xml`, eight STL files, README and BSD-2-Clause LICENSE are retained. `source_hashes.json` identifies the exact vendored bytes. No runtime downloads are needed.

`topogym/robot/assets.py` composes the installed Genesis Panda arm with this gripper. Meshes retain their original millimetre-to-metre scale. The assembled flange rotation aligns the closing direction with the existing task convention. The Panda hand and fingers are removed from the world body. The four-bar connect constraints, passive linkage joints and collision exclusions are retained.

`hand` is a fixed **task reference frame**, 51.8 mm ahead of the flange mount, not a second physical hand. The original tasks' nominal 102.9 mm grasp offset is approximately preserved near closure. The actual contact-pad centre moves with aperture and adaptation; use `controller.grasp_center_pos()` for measured proximity. `left_finger` and `right_finger` name the physical pad links. `finger_joint1/2` name the two rotary drivers; never interpret their raw positions as metres.

The controller exposes the previous metric **half-gap** API (0–40 mm; 0–80 mm full opening), converting it through `calibration.json`. Regenerate that unloaded model map with `scripts/calibrate_robotiq_model.py`. It is not a measurement of hardware accuracy or of the loaded adaptive mechanism.

Genesis 1.2.1 approximates the original split tendon using two joint actuators, coupled by the retained equality. The shared controller distributes commands symmetrically. It also restores the spring preload missing from Genesis's MJCF importer: native `stiffness=0.05`, `springref=2.62` requires `tau=-0.05*q+0.131` N·m. Genesis supplies the first term; the controller supplies the constant second term. This must be rechecked if the importer starts supporting spring reference positions.

The shared preset selects this model. Pass `common.robot_setup.gripper_model=panda` to reproduce the original Panda gripper. Controller tuning lives in `common.robot_setup.robotiq`; old Panda slider gains are not applied to Robotiq rotary drivers.
