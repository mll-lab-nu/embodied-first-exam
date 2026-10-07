#!/bin/bash
# Assemble the rcb-mujoco asset tree (build context images/mujoco/rcb_mj, not committed) from pinned upstream commits.
#   MuJoCo Menagerie 1b86ece (the commit MuJoCo Playground pins): aloha, kuka_iiwa_14, franka_emika_panda, robotiq_2f85,
#     unitree_go1, boston_dynamics_spot, google_barkour_vb
#   MuJoCo Playground 4057c14 (Apache-2.0): manipulation/{aloha,franka_emika_panda,franka_emika_panda_robotiq}/xmls,
#     locomotion/{go1,spot}/xmls (Go1's with its heightfield and texture)
#   SimToolReal 313d5ae (MIT): left Sharpa HA4 hand, DexToolBench objects + goal trajectories (no policy, no RL code)
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd); OUT=${RCB_MJ_OUT:-$HERE/rcb_mj}; TMP=$(mktemp -d)
git clone -q https://github.com/google-deepmind/mujoco_menagerie.git $TMP/menagerie && git -C $TMP/menagerie checkout -q 1b86ece576591213e2b666ebf59508454200ca97
git clone -q https://github.com/google-deepmind/mujoco_playground.git $TMP/playground && git -C $TMP/playground checkout -q 4057c14
git clone -q https://github.com/tylerlum/simtoolreal.git $TMP/simtoolreal && git -C $TMP/simtoolreal checkout -q 313d5ae
rm -rf "${OUT:?}"; mkdir -p $OUT/menagerie $OUT/playground/aloha $OUT/playground/franka_emika_panda $OUT/playground/franka_emika_panda_robotiq $OUT/playground/locomotion/go1 $OUT/playground/locomotion/spot $OUT/simtoolreal/assets/urdf $OUT/simtoolreal/dextoolbench
cp -r $TMP/menagerie/aloha $TMP/menagerie/kuka_iiwa_14 $TMP/menagerie/franka_emika_panda $TMP/menagerie/robotiq_2f85 $TMP/menagerie/unitree_go1 $TMP/menagerie/boston_dynamics_spot $TMP/menagerie/google_barkour_vb $OUT/menagerie/; cp $TMP/menagerie/LICENSE $OUT/menagerie/
for e in aloha franka_emika_panda franka_emika_panda_robotiq; do cp -r $TMP/playground/mujoco_playground/_src/manipulation/$e/xmls $OUT/playground/$e/; done; cp $TMP/playground/LICENSE $OUT/playground/
for e in go1 spot; do cp -r $TMP/playground/mujoco_playground/_src/locomotion/$e/xmls $OUT/playground/locomotion/$e/; done
cp -r $TMP/simtoolreal/assets/urdf/left_sharpa_ha4 $TMP/simtoolreal/assets/urdf/dextoolbench $OUT/simtoolreal/assets/urdf/
cp -r $TMP/simtoolreal/dextoolbench/trajectories $OUT/simtoolreal/dextoolbench/; cp $TMP/simtoolreal/LICENSE $OUT/simtoolreal/
rm -rf "${TMP:?}"; du -sh $OUT
