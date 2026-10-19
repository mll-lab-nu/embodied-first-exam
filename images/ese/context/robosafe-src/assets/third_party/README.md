# Third-party content

Third-party content includes seven robot models from
[MuJoCo Menagerie](https://github.com/google-deepmind/mujoco_menagerie) (four for the bench: two arms, their hand, and
a third arm with its own gripper that is used as a pair; three for the room: a mobile manipulator, a humanoid and a
quadruped with an arm) and one open font, DejaVu Sans (two files), used to print the text on generated labels.
The default realism profile also installs the reviewed prop meshes and surface textures under
`robosafebench/assets/data/realism_v3`. Its per-pack source URLs, authors, CC0/CC BY 4.0 declarations, modification
notices and exact checksums are carried in that directory's manifests and attribution files. These are inherited
source declarations from the reviewed asset pipeline, rather than a new license certification. Code-generated
prints and native collision geometry remain authored here.

| | |
|---|---|
| Upstream repository | `https://github.com/google-deepmind/mujoco_menagerie` |
| Upstream commit | `0059d4335f8156206f63a35662313385f7ad6d74` (committed 2026-10-07, "Update FR3 and FR3 v2 joint position limits to current Franka spec (#329)") |
| Retrieved | 2026-10-10 |

## What was taken

| Model | Upstream directory | Here | Files |
|---|---|---|---|
| Universal Robots UR5e | `universal_robots_ur5e/` | `mujoco_menagerie/universal_robots_ur5e/` | `ur5e.xml`, `assets/*.obj` (20 meshes), `LICENSE`, `README.md` |
| Robotiq 2F-85 | `robotiq_2f85/` | `mujoco_menagerie/robotiq_2f85/` | `2f85.xml`, `assets/*.stl` (8 meshes), `LICENSE`, `README.md` |
| Franka Research 3 (FR3) | `franka_fr3/` | `mujoco_menagerie/franka_fr3/` | `fr3.xml`, the 36 meshes it names (`assets/`: 28 `.obj`, 8 `.stl`), `LICENSE`, `README.md` |
| I2RT YAM | `i2rt_yam/` | `mujoco_menagerie/i2rt_yam/` | `yam.xml`, the 17 meshes it names (`assets/model2*.stl`), `LICENSE`, `README.md` |
| Stanford TidyBot | `stanford_tidybot/` | `mujoco_menagerie/stanford_tidybot/` | `tidybot.xml` (the base, a Kinova Gen3 arm and a Robotiq 2F-85 in one file), the 20 meshes it names (`assets/base/` 5, `assets/gen3/` 8, `assets/2f85/` 7, all `.stl`), `LICENSE`, `README.md`; 6.7 MB |
| Kinova Gen3 (licence only) | `kinova_gen3/` | `mujoco_menagerie/kinova_gen3/` | `LICENSE`, `README.md`: the terms of the arm that `tidybot.xml` carries inside it; no model file |
| Unitree G1 | `unitree_g1/` | `mujoco_menagerie/unitree_g1/` | `g1_with_hands.xml` (the variant with two three-finger hands), the 49 meshes it names (`assets/*.STL`), `LICENSE`, `README.md`; 31.5 MB |
| Boston Dynamics Spot with its arm | `boston_dynamics_spot/` | `mujoco_menagerie/boston_dynamics_spot/` | `spot_arm.xml`, the 54 meshes it names (`assets/*.obj`), `LICENSE`, `README.md`; 53.4 MB |

The files are byte-for-byte copies; nothing was edited. Left out because the models do not need them: each model's
`scene.xml` (a demo scene), the preview images (`ur5e.png`, `2f85.png`, `fr3.png`) and `CHANGELOG.md`; of the FR3 also
the six meshes in its `assets/` that `fr3.xml` does not name (`link0.obj`, `link3.obj`, `link4.obj`, `link5.obj`,
`link6.obj`, `link7.obj`: the unsplit originals of the visual meshes). Each `README.md` is kept because it states where
the model comes from and how it was derived; it links to the preview image and the changelog that were not copied.

The FR3 was added on 2026-10-10 from the same upstream commit (a shallow fetch of that commit; every copied file
compared equal to the fetched one, and the UR5e and 2F-85 files already here compared equal to the same fetch).

The YAM was added on 2026-10-12 from the same upstream commit (a sparse, shallow fetch of that commit; every copied
file compared equal to the fetched one by SHA-256). Left out: `scene.xml` and `scene_linear_4310.xml` (demo scenes),
the preview images (`yam.png`, `yam_linear_4310.png`), `CHANGELOG.md`, and the second variant of the arm
(`yam_linear_4310.xml` with its meshes under `assets/linear_4310/`: the YAM with another gripper and a wrist camera),
which is not used. The kept `README.md` describes both variants and links to the files that were not copied.
The three room models were added on 2026-10-12 from the same upstream commit (a shallow, sparse fetch of that commit
into a new directory; every copied file compared equal to the fetched one, and the 2F-85 files already here compared
equal to the same fetch; the UR5e and FR3 directories were not fetched again). Left out because the models do not need
them: every `scene*.xml`, the preview images and `CHANGELOG.md` as before; of the TidyBot also `base.xml` (the base
without the arm) and the mesh `assets/gen3/bracelet_no_vision_link.stl`, which `tidybot.xml` does not name; of the G1
also `g1.xml` (the variant with rubber mitts for hands, which cannot hold anything; it would add two meshes, 4.5 MB)
and `g1_mjx.xml`; of Spot also `spot.xml` (the variant without the arm; `spot_arm.xml` names every mesh of the
directory). The TidyBot's `assets/gen3/` and `assets/2f85/` meshes are byte for byte those of upstream's `kinova_gen3/`
and `robotiq_2f85/`; `tidybot.xml` does not use the 2F-85's coupling (`base_mount`), which a Gen3 has built in.
No `RobotSpec` names these three models yet: `docs/MOTION.md` 10.4 says what is in the files and what a spec needs
(`python scripts/describe_robot_models.py` reads them; `tests/sim/test_room_models.py` loads them).

`robosafebench/sim/world.py` loads an arm's and the gripper's MJCF files as they are and combines them in memory (gripper
attached to the arm's `attachment_site`, gravity compensation switched on for the robot's bodies, a force-torque sensor
added at the flange); `robosafebench/sim/robots.py` says which files make which robot (`ur5e_2f85`, `fr3_2f85`,
`yam_bimanual`). No change is written back to these files. For `yam_bimanual` the file `yam.xml` is loaded twice (one
arm each, names prefixed `left/` and `right/`); it holds the arm and its gripper in one model, and what it lacks is
added in memory: names for the two box shapes that are the finger pads, a site at the pinch point between them, the
force-torque site and the wrist camera on `link_6`; the spotlight the file defines is left out.

## Licences, as the files say

**`mujoco_menagerie/universal_robots_ur5e/LICENSE`** begins "Copyright 2018 ROS Industrial Consortium" and continues
with the three-clause BSD terms: redistribution and use in source and binary forms, with or without modification,
permitted provided that (1) redistributions of source code retain the copyright notice, the list of conditions and the
disclaimer, (2) redistributions in binary form reproduce them in the documentation or other materials, and (3) neither
the name of the copyright holder nor the names of its contributors are used to endorse or promote derived products
without specific prior written permission; followed by the "AS IS" warranty disclaimer. The file does not name the
licence; the model's `README.md` says "This model is released under a BSD-3-Clause License".

**`mujoco_menagerie/robotiq_2f85/LICENSE`** begins "Copyright (c) 2013, ROS-Industrial / All rights reserved." and
continues with the two-clause BSD terms: redistribution and use in source and binary forms, with or without
modification, permitted provided that redistributions of source code retain the copyright notice, the list of
conditions and the disclaimer, and redistributions in binary form reproduce them in the documentation or other
materials; followed by the "AS IS" warranty disclaimer. There is no non-endorsement clause. The file does not name the
licence; the model's `README.md` says "This model is released under a BSD-2-Clause License".

Both `README.md` files state that the models are derived from the publicly available URDF descriptions of
`ros-industrial/universal_robot` and `ros-industrial/robotiq`.

**`mujoco_menagerie/franka_fr3/LICENSE`** (237 lines) holds two texts. The first is the full Apache License, Version
2.0, January 2004 (terms and conditions 1 to 9 and the appendix on how to apply it); its copyright line is the
unfilled template "Copyright [yyyy] [name of copyright owner]", so the file names no copyright holder for this part.
After a line of dashes comes a "Software License Agreement (BSD License)": the three-clause BSD terms (retain the
notice in source, reproduce it in binary form, and "Neither the name of Willow Garage, Inc. nor the names of its
contributors may be used to endorse or promote products derived from this software without specific prior written
permission"), followed by the "AS IS" warranty disclaimer; this part has no copyright line of its own. The model's
`README.md` says "This model is released under an Apache-2.0 License" and that it is derived from the publicly
available URDF description `frankaemika/franka_description`; it does not say which files the BSD text covers.

**`mujoco_menagerie/i2rt_yam/LICENSE`** (21 lines) is headed "MIT License", has the copyright line "Copyright (c)
2025 i2rt robotics", and continues with the MIT terms word for word: permission, free of charge, to deal in the
software without restriction (use, copy, modify, merge, publish, distribute, sublicense, sell), subject to the
copyright notice and the permission notice being included in all copies or substantial portions; followed by the
"AS IS" warranty disclaimer. The model's `README.md` says "This model is released under an MIT License" and that
`yam.xml` is derived from I2RT's publicly available URDF description (`i2rt-robotics/i2rt`,
`robot_models/yam/yam.urdf`), with a home keyframe, a tracking light, joint friction, armature and position actuators
added.

**`mujoco_menagerie/stanford_tidybot/LICENSE`** (21 lines) is the MIT License: "Copyright (c) 2024 Stanford
Interactive Perception and Robot Learning Lab", permission free of charge to any person "to deal in the Software
without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute,
sublicense, and/or sell copies", on the one condition that "the above copyright notice and this permission notice
shall be included in all copies or substantial portions of the Software"; followed by the "AS IS" warranty disclaimer.
The model's `README.md` says: "The TidyBot base is released under an MIT License. The Kinova Gen3 and Robotiq 2F-85
MJCFs retain their original licenses. For more information, see the LICENSE file." The `LICENSE` file itself holds
the MIT text only: it does not repeat the terms of the arm and the hand, although `tidybot.xml` carries both inside
it and `assets/gen3/` and `assets/2f85/` are their meshes. Those terms are therefore kept beside it here: the hand's
in `mujoco_menagerie/robotiq_2f85/LICENSE` (above), the arm's in `mujoco_menagerie/kinova_gen3/LICENSE`.

**`mujoco_menagerie/kinova_gen3/LICENSE`** (11 lines) begins "Copyright (c) 2018, Kinova inc." and continues with the
three-clause BSD terms: redistribution and use in source and binary forms, with or without modification, permitted
provided that (1) redistributions of source code retain the copyright notice, the list of conditions and the
disclaimer, (2) redistributions in binary form reproduce them in the documentation or other materials, and (3)
"Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote
products derived from this software without specific prior written permission"; followed by the "AS IS" warranty
disclaimer. The file does not name the licence; the model's `README.md` says "This model is released under a
BSD-3-Clause License" and that it is derived from the publicly available URDF description in
`Kinovarobotics/ros_kortex`. The same `README.md` says how a 2F-85 is to be mounted on a Gen3 (without the coupling,
the tool site moved out by 0.12 m), which is how `tidybot.xml` has it.

**`mujoco_menagerie/unitree_g1/LICENSE`** (27 lines) begins "Copyright (c) 2016-2023 HangZhou YuShu TECHNOLOGY
CO.,LTD. ("Unitree Robotics") / All rights reserved." and continues with the three-clause BSD terms (retain the
notice in source, reproduce it in binary form, no use of the holder's or contributors' names to endorse or promote
derived products without specific prior written permission), followed by the "AS IS" warranty disclaimer. The file
does not name the licence; the model's `README.md` says "This model is released under a BSD-3-Clause License" and
that it is derived from the publicly available MJCF description in `unitreerobotics/unitree_ros` (the variant taken
here calls itself `g1_29dof_with_hand_rev_1_0`). The chest carries the maker's name as part of the shape
(`logo_link.STL`), and it shows in rendered images (looked at: `build/robot_models/g1.png`); the non-endorsement
clause concerns promoting derived products with that name, not showing the robot as it is. Whether a camera image
an agent gets should show a maker's name is a question for the benchmark, not for the licence.

**`mujoco_menagerie/boston_dynamics_spot/LICENSE`** (29 lines) is headed "BSD 3-Clause License", begins "Copyright (c)
2021, Clearpath Robotics Inc. / All rights reserved." and continues with the same three numbered conditions and the
"AS IS" warranty disclaimer. The copyright holder named is Clearpath Robotics, not Boston Dynamics: the model's
`README.md` says it is derived from the publicly available URDF description `bdaiinstitute/spot_ros2`
(`spot_simple.urdf.xacro` and `spot_arm_macro.urdf`) and "is released under a BSD-3-Clause License".

None of the four restricts redistribution in a public repository beyond keeping the notices. Redistribution therefore
requires keeping each `LICENSE` file next to its model, which is how they are stored here (for the TidyBot: its own,
the Gen3's and the 2F-85's); for the FR3, Apache-2.0 section 4 also asks that modified files carry a notice of the
change (none is modified here).

Redistribution therefore requires keeping each `LICENSE` file next to its model, which is how they are stored here;
for the FR3, Apache-2.0 section 4 also asks that modified files carry a notice of the change (none is modified here).

## Updating

Copy the same files from a newer upstream commit, replace the commit hash and date above, re-read the `LICENSE` files
and correct this page if they changed, then run `pytest tests/sim` (the determinism and skill tests exercise the
UR5e and the gripper, `tests/sim/test_sim_robots.py` the FR3, `tests/sim/test_sim_two_arms.py` the YAM pair) and
`python -m robosafebench.sim eval --robot <type>`; for the room models, `pytest tests/sim/test_room_models.py` and
`python scripts/describe_robot_models.py --planar`, and compare its tables with `docs/MOTION.md` 10.4.

## Font for printed labels

| | |
|---|---|
| Files | `fonts/DejaVuSans-Bold.ttf`, `fonts/DejaVuSans.ttf`, `fonts/LICENSE` |
| Font | DejaVu Sans 2.37 (`https://dejavu-fonts.github.io/`) |
| Taken from | the Debian package `fonts-dejavu-core` 2.37-8 installed on the build machine (`/usr/share/fonts/truetype/dejavu/`), byte-for-byte, on 2026-10-10 |
| SHA-256 | `DejaVuSans-Bold.ttf` `5c1247acef7f2b8522a31742c76d6adcb5569bacc0be7ceaa4dc39dd252ce895`, `DejaVuSans.ttf` `ae7b7855e115a5966d8b1b3f80f254ccc117ec86f9965e202ee2940453837280` |
| Used by | `robosafebench/assets/labels.py`, which rasterises label text with Pillow when an asset is built. The font files are not copied into generated assets; only the rendered text is |

Licence (`fonts/LICENSE`): the Bitstream Vera Fonts licence (a permissive licence: the fonts may be used, copied, merged,
distributed and sold as part of a larger package, not sold by themselves, and modified only under another name), with
the DejaVu changes in the public domain and the glyphs taken from Arev under the same terms in the name of Tavmjong
Bah. The Bitstream part of `fonts/LICENSE` is the text of `/usr/share/doc/fonts-dejavu-core/copyright` re-wrapped; the
two heading lines and the Arev part were typed in from the upstream `LICENSE` wording and should be compared with
`https://github.com/dejavu-fonts/dejavu-fonts/blob/master/LICENSE` when the font is next updated.
