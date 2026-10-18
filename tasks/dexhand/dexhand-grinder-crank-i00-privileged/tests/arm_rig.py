"""Tianji Marvin dual-arm rig for DexHand families (runtime module; stdlib + numpy + mujoco only).

``mount_marvin`` replaces the floating six-axis wrist stage of a family scene by the fixed Tianji Marvin stand with
two 7-DoF arms (the exact kinematics, inertias, meshes, joint limits, damping, armature, contact excludes and
position-servo gains of ``pot_shelf_transfer`` / ``sweep_dustpan``: kp 700, kv 48, force limits 108/108/66/66/18/18/18
N m) and a Sharpa Wave hand on each flange (right: the genuine right model; left: the right model reflected in y, the
convention of the accepted bimanual families). ``hand="wuji"`` swaps both Wave hands for the genuine Wuji Hand 2.2
(``hands.replace_wave_hands``) under the same flange mounts. Both arms and both hands are always present (robot id
``marvin-bimanual-sharpa-wave``); a one-hand task drives one arm and keeps the other at ``PARK``.

Action layout (one row = every actuator target, model order; identical to pot_shelf_transfer):
    [ left arm J1..J7 (7) | right arm J1..J7 (7) | left hand fingers | right hand fingers ]
    sharpa: 14 + 22 + 22 = 58          wuji: 14 + 20 + 20 = 54
Any other (non-robot) actuators of a scene would follow the hands; DexHand scenes have none.

See docs/benchmarks/dexhand.md ("Arm rig") for the rig's role in the DexHand families; arm_ik.py (authoring only)
converts a family's wrist-stage episode into arm rows.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import numpy as np

ROBOT_ID = "marvin-bimanual-sharpa-wave"
SIDES = ("left", "right")
ARM_JOINTS = {
    "left": ["SHOULDER_PITCH_L_J1", "SHOULDER_ROLL_L_J2", "ELBOW_PITCH_L_J3", "ELBOW_YAW_L_J4",
             "WRIST_PITCH_L_J5", "WRIST_YAW_L_J6", "WRIST_ROLL_L_J7"],
    "right": ["SHOULDER_PITCH_R_J1", "SHOULDER_ROLL_R_J2", "ELBOW_PITCH_R_J3", "ELBOW_YAW_R_J4",
              "WRIST_PITCH_R_J5", "WRIST_YAW_R_J6", "WRIST_ROLL_R_J7"],
}
ARM_ACTUATORS = [joint + "_target" for side in SIDES for joint in ARM_JOINTS[side]]
FLANGE_BODY = {"left": "left_ee", "right": "right_ee"}
WRIST_LINK = {"left": "wrist_roll_l_j7_link", "right": "wrist_roll_r_j7_link"}
WAVE_ROOT = {"left": "left_hand_C_MC", "right": "right_hand_C_MC"}
DEFAULT_MOUNTS = {"left": "left_hand_mount", "right": "right_hand_mount"}
# Shoulder joint centres in the base_link frame (x forward, y left, z up); the flange is 0.287 + 0.314 + 0.095 m
# of links away from the shoulder (upper arm, forearm, wrist to flange) and the palm centre about 0.09 m further.
SHOULDER = {"left": (0.0, 0.2215, 1.121), "right": (0.0, -0.2215, 1.121)}
# Parked pose of an inactive arm: hanging straight down beside the torso column (zero gravity torque, so no servo
# sag), fingers down. Arm + hand stay inside x in [-0.05, 0.12] m, |y| in [0.17, 0.27] m, z >= 0.23 m of the base frame
# (the stand's platform top is z = 0.144 m), i.e. behind any table whose front edge is at x >= 0.20 m.
PARK = {
    "left": [1.5707963267948966, -1.5707963267948966, 0.0, 0.0, 0.0, 0.0, 0.0],
    "right": [-1.5707963267948966, -1.5707963267948966, 0.0, 0.0, 0.0, 0.0, 0.0],
}

_MARVIN_XML = """<marvin>
 <asset>
  <mesh name="visual_base_link_0" content_type="model/stl" file="@TIANJI@/converted_visual/visual_base_link_0.stl" />
  <mesh name="visual_base_link_1" content_type="model/stl" file="@TIANJI@/converted_visual/visual_base_link_1.stl" />
  <mesh name="visual_base_link_2" content_type="model/stl" file="@TIANJI@/converted_visual/visual_base_link_2.stl" />
  <mesh name="visual_base_link_3" content_type="model/stl" file="@TIANJI@/converted_visual/visual_base_link_3.stl" />
  <mesh name="visual_base_link_4" content_type="model/stl" file="@TIANJI@/converted_visual/visual_base_link_4.stl" />
  <mesh name="collision_base_link_0" content_type="model/stl" file="@TIANJI@/converted_collision/collision_base_link_0.stl" />
  <mesh name="collision_base_link_1" content_type="model/stl" file="@TIANJI@/converted_collision/collision_base_link_1.stl" />
  <mesh name="collision_base_link_2" content_type="model/stl" file="@TIANJI@/converted_collision/collision_base_link_2.stl" />
  <mesh name="collision_base_link_3" content_type="model/stl" file="@TIANJI@/converted_collision/collision_base_link_3.stl" />
  <mesh name="collision_base_link_4" content_type="model/stl" file="@TIANJI@/converted_collision/collision_base_link_4.stl" />
  <mesh name="collision_base_link_5" content_type="model/stl" file="@TIANJI@/converted_collision/collision_base_link_5.stl" />
  <mesh name="collision_base_link_6" content_type="model/stl" file="@TIANJI@/converted_collision/collision_base_link_6.stl" />
  <mesh name="collision_base_link_7" content_type="model/stl" file="@TIANJI@/converted_collision/collision_base_link_7.stl" />
  <mesh name="collision_base_link_8" content_type="model/stl" file="@TIANJI@/converted_collision/collision_base_link_8.stl" />
  <mesh name="collision_base_link_9" content_type="model/stl" file="@TIANJI@/converted_collision/collision_base_link_9.stl" />
  <mesh name="visual_shoulder_pitch_l_j1_link_0" content_type="model/stl" file="@TIANJI@/converted_visual/visual_shoulder_pitch_l_j1_link_0.stl" />
  <mesh name="visual_shoulder_pitch_l_j1_link_1" content_type="model/stl" file="@TIANJI@/converted_visual/visual_shoulder_pitch_l_j1_link_1.stl" />
  <mesh name="visual_shoulder_pitch_l_j1_link_2" content_type="model/stl" file="@TIANJI@/converted_visual/visual_shoulder_pitch_l_j1_link_2.stl" />
  <mesh name="collision_shoulder_pitch_l_j1_link_0" content_type="model/stl" file="@TIANJI@/converted_collision/collision_shoulder_pitch_l_j1_link_0.stl" />
  <mesh name="collision_shoulder_pitch_l_j1_link_1" content_type="model/stl" file="@TIANJI@/converted_collision/collision_shoulder_pitch_l_j1_link_1.stl" />
  <mesh name="collision_shoulder_pitch_l_j1_link_2" content_type="model/stl" file="@TIANJI@/converted_collision/collision_shoulder_pitch_l_j1_link_2.stl" />
  <mesh name="collision_shoulder_pitch_l_j1_link_3" content_type="model/stl" file="@TIANJI@/converted_collision/collision_shoulder_pitch_l_j1_link_3.stl" />
  <mesh name="visual_shoulder_roll_l_j2_link_0" content_type="model/stl" file="@TIANJI@/converted_visual/visual_shoulder_roll_l_j2_link_0.stl" />
  <mesh name="collision_shoulder_roll_l_j2_link_0" content_type="model/stl" file="@TIANJI@/converted_collision/collision_shoulder_roll_l_j2_link_0.stl" />
  <mesh name="collision_shoulder_roll_l_j2_link_1" content_type="model/stl" file="@TIANJI@/converted_collision/collision_shoulder_roll_l_j2_link_1.stl" />
  <mesh name="collision_shoulder_roll_l_j2_link_2" content_type="model/stl" file="@TIANJI@/converted_collision/collision_shoulder_roll_l_j2_link_2.stl" />
  <mesh name="collision_shoulder_roll_l_j2_link_3" content_type="model/stl" file="@TIANJI@/converted_collision/collision_shoulder_roll_l_j2_link_3.stl" />
  <mesh name="visual_elbow_pitch_l_j3_link_0" content_type="model/stl" file="@TIANJI@/converted_visual/visual_elbow_pitch_l_j3_link_0.stl" />
  <mesh name="collision_elbow_pitch_l_j3_link_0" content_type="model/stl" file="@TIANJI@/converted_collision/collision_elbow_pitch_l_j3_link_0.stl" />
  <mesh name="collision_elbow_pitch_l_j3_link_1" content_type="model/stl" file="@TIANJI@/converted_collision/collision_elbow_pitch_l_j3_link_1.stl" />
  <mesh name="collision_elbow_pitch_l_j3_link_2" content_type="model/stl" file="@TIANJI@/converted_collision/collision_elbow_pitch_l_j3_link_2.stl" />
  <mesh name="collision_elbow_pitch_l_j3_link_3" content_type="model/stl" file="@TIANJI@/converted_collision/collision_elbow_pitch_l_j3_link_3.stl" />
  <mesh name="visual_elbow_yaw_l_j4_link_0" content_type="model/stl" file="@TIANJI@/converted_visual/visual_elbow_yaw_l_j4_link_0.stl" />
  <mesh name="collision_elbow_yaw_l_j4_link_0" content_type="model/stl" file="@TIANJI@/converted_collision/collision_elbow_yaw_l_j4_link_0.stl" />
  <mesh name="collision_elbow_yaw_l_j4_link_1" content_type="model/stl" file="@TIANJI@/converted_collision/collision_elbow_yaw_l_j4_link_1.stl" />
  <mesh name="collision_elbow_yaw_l_j4_link_2" content_type="model/stl" file="@TIANJI@/converted_collision/collision_elbow_yaw_l_j4_link_2.stl" />
  <mesh name="collision_elbow_yaw_l_j4_link_3" content_type="model/stl" file="@TIANJI@/converted_collision/collision_elbow_yaw_l_j4_link_3.stl" />
  <mesh name="visual_wrist_pitch_l_j5_link_0" content_type="model/stl" file="@TIANJI@/converted_visual/visual_wrist_pitch_l_j5_link_0.stl" />
  <mesh name="collision_wrist_pitch_l_j5_link_0" content_type="model/stl" file="@TIANJI@/converted_collision/collision_wrist_pitch_l_j5_link_0.stl" />
  <mesh name="collision_wrist_pitch_l_j5_link_1" content_type="model/stl" file="@TIANJI@/converted_collision/collision_wrist_pitch_l_j5_link_1.stl" />
  <mesh name="collision_wrist_pitch_l_j5_link_2" content_type="model/stl" file="@TIANJI@/converted_collision/collision_wrist_pitch_l_j5_link_2.stl" />
  <mesh name="collision_wrist_pitch_l_j5_link_3" content_type="model/stl" file="@TIANJI@/converted_collision/collision_wrist_pitch_l_j5_link_3.stl" />
  <mesh name="visual_wrist_yaw_l_j6_link_0" content_type="model/stl" file="@TIANJI@/converted_visual/visual_wrist_yaw_l_j6_link_0.stl" />
  <mesh name="collision_wrist_yaw_l_j6_link_0" content_type="model/stl" file="@TIANJI@/converted_collision/collision_wrist_yaw_l_j6_link_0.stl" />
  <mesh name="collision_wrist_yaw_l_j6_link_1" content_type="model/stl" file="@TIANJI@/converted_collision/collision_wrist_yaw_l_j6_link_1.stl" />
  <mesh name="collision_wrist_yaw_l_j6_link_2" content_type="model/stl" file="@TIANJI@/converted_collision/collision_wrist_yaw_l_j6_link_2.stl" />
  <mesh name="collision_wrist_yaw_l_j6_link_3" content_type="model/stl" file="@TIANJI@/converted_collision/collision_wrist_yaw_l_j6_link_3.stl" />
  <mesh name="visual_wrist_roll_l_j7_link_0" content_type="model/stl" file="@TIANJI@/converted_visual/visual_wrist_roll_l_j7_link_0.stl" />
  <mesh name="visual_wrist_roll_l_j7_link_1" content_type="model/stl" file="@TIANJI@/converted_visual/visual_wrist_roll_l_j7_link_1.stl" />
  <mesh name="collision_wrist_roll_l_j7_link_0" content_type="model/stl" file="@TIANJI@/converted_collision/collision_wrist_roll_l_j7_link_0.stl" />
  <mesh name="collision_wrist_roll_l_j7_link_1" content_type="model/stl" file="@TIANJI@/converted_collision/collision_wrist_roll_l_j7_link_1.stl" />
  <mesh name="collision_wrist_roll_l_j7_link_2" content_type="model/stl" file="@TIANJI@/converted_collision/collision_wrist_roll_l_j7_link_2.stl" />
  <mesh name="collision_wrist_roll_l_j7_link_3" content_type="model/stl" file="@TIANJI@/converted_collision/collision_wrist_roll_l_j7_link_3.stl" />
  <mesh name="visual_shoulder_pitch_r_j1_link_0" content_type="model/stl" file="@TIANJI@/converted_visual/visual_shoulder_pitch_r_j1_link_0.stl" />
  <mesh name="visual_shoulder_pitch_r_j1_link_1" content_type="model/stl" file="@TIANJI@/converted_visual/visual_shoulder_pitch_r_j1_link_1.stl" />
  <mesh name="visual_shoulder_pitch_r_j1_link_2" content_type="model/stl" file="@TIANJI@/converted_visual/visual_shoulder_pitch_r_j1_link_2.stl" />
  <mesh name="collision_shoulder_pitch_r_j1_link_0" content_type="model/stl" file="@TIANJI@/converted_collision/collision_shoulder_pitch_r_j1_link_0.stl" />
  <mesh name="collision_shoulder_pitch_r_j1_link_1" content_type="model/stl" file="@TIANJI@/converted_collision/collision_shoulder_pitch_r_j1_link_1.stl" />
  <mesh name="collision_shoulder_pitch_r_j1_link_2" content_type="model/stl" file="@TIANJI@/converted_collision/collision_shoulder_pitch_r_j1_link_2.stl" />
  <mesh name="collision_shoulder_pitch_r_j1_link_3" content_type="model/stl" file="@TIANJI@/converted_collision/collision_shoulder_pitch_r_j1_link_3.stl" />
  <mesh name="visual_shoulder_roll_r_j2_link_0" content_type="model/stl" file="@TIANJI@/converted_visual/visual_shoulder_roll_r_j2_link_0.stl" />
  <mesh name="collision_shoulder_roll_r_j2_link_0" content_type="model/stl" file="@TIANJI@/converted_collision/collision_shoulder_roll_r_j2_link_0.stl" />
  <mesh name="collision_shoulder_roll_r_j2_link_1" content_type="model/stl" file="@TIANJI@/converted_collision/collision_shoulder_roll_r_j2_link_1.stl" />
  <mesh name="collision_shoulder_roll_r_j2_link_2" content_type="model/stl" file="@TIANJI@/converted_collision/collision_shoulder_roll_r_j2_link_2.stl" />
  <mesh name="collision_shoulder_roll_r_j2_link_3" content_type="model/stl" file="@TIANJI@/converted_collision/collision_shoulder_roll_r_j2_link_3.stl" />
  <mesh name="visual_elbow_pitch_r_j3_link_0" content_type="model/stl" file="@TIANJI@/converted_visual/visual_elbow_pitch_r_j3_link_0.stl" />
  <mesh name="collision_elbow_pitch_r_j3_link_0" content_type="model/stl" file="@TIANJI@/converted_collision/collision_elbow_pitch_r_j3_link_0.stl" />
  <mesh name="collision_elbow_pitch_r_j3_link_1" content_type="model/stl" file="@TIANJI@/converted_collision/collision_elbow_pitch_r_j3_link_1.stl" />
  <mesh name="collision_elbow_pitch_r_j3_link_2" content_type="model/stl" file="@TIANJI@/converted_collision/collision_elbow_pitch_r_j3_link_2.stl" />
  <mesh name="collision_elbow_pitch_r_j3_link_3" content_type="model/stl" file="@TIANJI@/converted_collision/collision_elbow_pitch_r_j3_link_3.stl" />
  <mesh name="visual_elbow_yaw_r_j4_link_0" content_type="model/stl" file="@TIANJI@/converted_visual/visual_elbow_yaw_r_j4_link_0.stl" />
  <mesh name="collision_elbow_yaw_r_j4_link_0" content_type="model/stl" file="@TIANJI@/converted_collision/collision_elbow_yaw_r_j4_link_0.stl" />
  <mesh name="collision_elbow_yaw_r_j4_link_1" content_type="model/stl" file="@TIANJI@/converted_collision/collision_elbow_yaw_r_j4_link_1.stl" />
  <mesh name="collision_elbow_yaw_r_j4_link_2" content_type="model/stl" file="@TIANJI@/converted_collision/collision_elbow_yaw_r_j4_link_2.stl" />
  <mesh name="collision_elbow_yaw_r_j4_link_3" content_type="model/stl" file="@TIANJI@/converted_collision/collision_elbow_yaw_r_j4_link_3.stl" />
  <mesh name="visual_wrist_pitch_r_j5_link_0" content_type="model/stl" file="@TIANJI@/converted_visual/visual_wrist_pitch_r_j5_link_0.stl" />
  <mesh name="collision_wrist_pitch_r_j5_link_0" content_type="model/stl" file="@TIANJI@/converted_collision/collision_wrist_pitch_r_j5_link_0.stl" />
  <mesh name="collision_wrist_pitch_r_j5_link_1" content_type="model/stl" file="@TIANJI@/converted_collision/collision_wrist_pitch_r_j5_link_1.stl" />
  <mesh name="collision_wrist_pitch_r_j5_link_2" content_type="model/stl" file="@TIANJI@/converted_collision/collision_wrist_pitch_r_j5_link_2.stl" />
  <mesh name="visual_wrist_yaw_r_j6_link_0" content_type="model/stl" file="@TIANJI@/converted_visual/visual_wrist_yaw_r_j6_link_0.stl" />
  <mesh name="collision_wrist_yaw_r_j6_link_0" content_type="model/stl" file="@TIANJI@/converted_collision/collision_wrist_yaw_r_j6_link_0.stl" />
  <mesh name="collision_wrist_yaw_r_j6_link_1" content_type="model/stl" file="@TIANJI@/converted_collision/collision_wrist_yaw_r_j6_link_1.stl" />
  <mesh name="collision_wrist_yaw_r_j6_link_2" content_type="model/stl" file="@TIANJI@/converted_collision/collision_wrist_yaw_r_j6_link_2.stl" />
  <mesh name="collision_wrist_yaw_r_j6_link_3" content_type="model/stl" file="@TIANJI@/converted_collision/collision_wrist_yaw_r_j6_link_3.stl" />
  <mesh name="visual_wrist_roll_r_j7_link_0" content_type="model/stl" file="@TIANJI@/converted_visual/visual_wrist_roll_r_j7_link_0.stl" />
  <mesh name="visual_wrist_roll_r_j7_link_1" content_type="model/stl" file="@TIANJI@/converted_visual/visual_wrist_roll_r_j7_link_1.stl" />
  <mesh name="collision_wrist_roll_r_j7_link_0" content_type="model/stl" file="@TIANJI@/converted_collision/collision_wrist_roll_r_j7_link_0.stl" />
  <mesh name="collision_wrist_roll_r_j7_link_1" content_type="model/stl" file="@TIANJI@/converted_collision/collision_wrist_roll_r_j7_link_1.stl" />
  <mesh name="collision_wrist_roll_r_j7_link_2" content_type="model/stl" file="@TIANJI@/converted_collision/collision_wrist_roll_r_j7_link_2.stl" />
  <mesh name="collision_wrist_roll_r_j7_link_3" content_type="model/stl" file="@TIANJI@/converted_collision/collision_wrist_roll_r_j7_link_3.stl" />
 </asset>
 <body name="base_link">
  <inertial pos="-0.00172139 0.0099291 0.206453" quat="0.898342 0.0173327 0.000142353 0.438955" mass="0.109249" diaginertia="0.0178338 0.0177215 0.00764831" />
  <geom pos="0 0 0" quat="0.707107 0 0 0.707107" type="mesh" contype="0" conaffinity="0" group="1" density="0" rgba="0.611764705882353 0.6313725490196078 0.6509803921568628 1.0" mesh="visual_base_link_0" />
  <geom pos="0 0 0" quat="0.707107 0 0 0.707107" type="mesh" contype="0" conaffinity="0" group="1" density="0" rgba="0.5098039215686274 0.5411764705882353 0.5568627450980392 1.0" mesh="visual_base_link_1" />
  <geom pos="0 0 0" quat="0.707107 0 0 0.707107" type="mesh" contype="0" conaffinity="0" group="1" density="0" rgba="0.27058823529411763 0.2980392156862745 0.3176470588235294 1.0" mesh="visual_base_link_2" />
  <geom pos="0 0 0" quat="0.707107 0 0 0.707107" type="mesh" contype="0" conaffinity="0" group="1" density="0" rgba="0.01568627450980392 0.0196078431372549 0.023529411764705882 1.0" mesh="visual_base_link_3" />
  <geom quat="0.707107 0 0 0.707107" type="mesh" contype="0" conaffinity="0" group="1" density="0" rgba="0.00784313725490196 0.011764705882352941 0.011764705882352941 1.0" mesh="visual_base_link_4" />
  <geom pos="0 0 0" quat="0.707107 0 0 0.707107" type="mesh" rgba="0 0 0 0" mesh="collision_base_link_0" group="3" />
  <geom pos="0 0 0" quat="0.707107 0 0 0.707107" type="mesh" rgba="0 0 0 0" mesh="collision_base_link_1" group="3" />
  <geom pos="0 0 0" quat="0.707107 0 0 0.707107" type="mesh" rgba="0 0 0 0" mesh="collision_base_link_2" group="3" />
  <geom pos="0 0 0" quat="0.707107 0 0 0.707107" type="mesh" rgba="0 0 0 0" mesh="collision_base_link_3" group="3" />
  <geom pos="0 0 0" quat="0.707107 0 0 0.707107" type="mesh" rgba="0 0 0 0" mesh="collision_base_link_4" group="3" />
  <geom pos="0 0 0" quat="0.707107 0 0 0.707107" type="mesh" rgba="0 0 0 0" mesh="collision_base_link_5" group="3" />
  <geom pos="0 0 0" quat="0.707107 0 0 0.707107" type="mesh" rgba="0 0 0 0" mesh="collision_base_link_6" group="3" />
  <geom pos="0 0 0" quat="0.707107 0 0 0.707107" type="mesh" rgba="0 0 0 0" mesh="collision_base_link_7" group="3" />
  <geom pos="0 0 0" quat="0.707107 0 0 0.707107" type="mesh" rgba="0 0 0 0" mesh="collision_base_link_8" group="3" />
  <geom quat="0.707107 0 0 0.707107" type="mesh" rgba="0 0 0 0" mesh="collision_base_link_9" group="3" />
  <body name="upper_body_base" pos="-2.9142e-05 0 1.121">
   <body name="left_arm_base" pos="2.9142e-05 0 -1.121" quat="0.707107 0 0 0.707107">
    <body name="shoulder_pitch_l_j1_link" pos="0.2215 2.9142e-05 1.121" quat="0.5 -0.5 0.5 -0.5">
     <inertial pos="2.347e-05 0.0055715 -0.03076" quat="0.711599 0.0343691 -0.0341702 0.700912" mass="1.9705" diaginertia="0.00529754 0.00492285 0.00184874" />
     <joint name="SHOULDER_PITCH_L_J1" pos="0 0 0" axis="0 0 1" range="-3.10669 3.10669" actuatorfrcrange="-108 108" damping="2" armature="0.02" />
     <geom type="mesh" contype="0" conaffinity="0" group="1" density="0" rgba="0.8823529411764706 0.8941176470588236 0.8980392156862745 1.0" mesh="visual_shoulder_pitch_l_j1_link_0" />
     <geom type="mesh" contype="0" conaffinity="0" group="1" density="0" rgba="0.611764705882353 0.6313725490196078 0.6509803921568628 1.0" mesh="visual_shoulder_pitch_l_j1_link_1" />
     <geom type="mesh" contype="0" conaffinity="0" group="1" density="0" rgba="0.01568627450980392 0.0196078431372549 0.023529411764705882 1.0" mesh="visual_shoulder_pitch_l_j1_link_2" />
     <geom type="mesh" rgba="0 0 0 0" mesh="collision_shoulder_pitch_l_j1_link_0" group="3" />
     <geom type="mesh" rgba="0 0 0 0" mesh="collision_shoulder_pitch_l_j1_link_1" group="3" />
     <geom type="mesh" rgba="0 0 0 0" mesh="collision_shoulder_pitch_l_j1_link_2" group="3" />
     <geom type="mesh" rgba="0 0 0 0" mesh="collision_shoulder_pitch_l_j1_link_3" group="3" />
     <body name="shoulder_roll_l_j2_link" quat="0.707107 0.707107 0 0">
      <inertial pos="0.00013483 0.0617046 0.00950639" quat="0.643375 0.765551 -3.57328e-05 0.000294349" mass="2.24398" diaginertia="0.0119493 0.0112156 0.00338374" />
      <joint name="SHOULDER_ROLL_L_J2" pos="0 0 0" axis="0 0 1" range="-2.0944 2.0944" actuatorfrcrange="-108 108" damping="2" armature="0.02" />
      <geom type="mesh" contype="0" conaffinity="0" group="1" density="0" rgba="0.8823529411764706 0.8941176470588236 0.8980392156862745 1.0" mesh="visual_shoulder_roll_l_j2_link_0" />
      <geom type="mesh" rgba="0 0 0 0" mesh="collision_shoulder_roll_l_j2_link_0" group="3" />
      <geom type="mesh" rgba="0 0 0 0" mesh="collision_shoulder_roll_l_j2_link_1" group="3" />
      <geom type="mesh" rgba="0 0 0 0" mesh="collision_shoulder_roll_l_j2_link_2" group="3" />
      <geom type="mesh" rgba="0 0 0 0" mesh="collision_shoulder_roll_l_j2_link_3" group="3" />
      <body name="elbow_pitch_l_j3_link" pos="0 0.287 0" quat="0.707107 -0.707107 0 0">
       <inertial pos="0.00968562 0.00246599 -0.046273" quat="0.782446 -0.0355285 -0.0735516 0.617337" mass="1.9242" diaginertia="0.00765215 0.00730789 0.0016338" />
       <joint name="ELBOW_PITCH_L_J3" pos="0 0 0" axis="0 0 1" range="-3.10669 3.10669" actuatorfrcrange="-66 66" damping="2" armature="0.02" />
       <geom type="mesh" contype="0" conaffinity="0" group="1" density="0" rgba="0.8823529411764706 0.8941176470588236 0.8980392156862745 1.0" mesh="visual_elbow_pitch_l_j3_link_0" />
       <geom type="mesh" rgba="0 0 0 0" mesh="collision_elbow_pitch_l_j3_link_0" group="3" />
       <geom type="mesh" rgba="0 0 0 0" mesh="collision_elbow_pitch_l_j3_link_1" group="3" />
       <geom type="mesh" rgba="0 0 0 0" mesh="collision_elbow_pitch_l_j3_link_2" group="3" />
       <geom type="mesh" rgba="0 0 0 0" mesh="collision_elbow_pitch_l_j3_link_3" group="3" />
       <body name="elbow_yaw_l_j4_link" pos="0.018 0 0" quat="0 0 -0.707107 0.707107">
        <inertial pos="0.00850411 -0.0471822 0.00941509" quat="0.741754 0.628694 0.0774999 -0.220317" mass="1.6085" diaginertia="0.00603244 0.00535875 0.00198228" />
        <joint name="ELBOW_YAW_L_J4" pos="0 0 0" axis="0 0 1" range="-2.53073 1.0472" actuatorfrcrange="-66 66" damping="2" armature="0.02" />
        <geom type="mesh" contype="0" conaffinity="0" group="1" density="0" rgba="0.8823529411764706 0.8941176470588236 0.8980392156862745 1.0" mesh="visual_elbow_yaw_l_j4_link_0" />
        <geom type="mesh" rgba="0 0 0 0" mesh="collision_elbow_yaw_l_j4_link_0" group="3" />
        <geom type="mesh" rgba="0 0 0 0" mesh="collision_elbow_yaw_l_j4_link_1" group="3" />
        <geom type="mesh" rgba="0 0 0 0" mesh="collision_elbow_yaw_l_j4_link_2" group="3" />
        <geom type="mesh" rgba="0 0 0 0" mesh="collision_elbow_yaw_l_j4_link_3" group="3" />
        <body name="wrist_pitch_l_j5_link" pos="0.018 -0.314 0" quat="0 0 -0.707107 0.707107">
         <inertial pos="0.00051127 0.00101064 -0.112717" quat="0.999438 -0.00995046 -0.00675781 0.0312997" mass="2.0883" diaginertia="0.00626924 0.00564262 0.00243436" />
         <joint name="WRIST_PITCH_L_J5" pos="0 0 0" axis="0 0 1" range="-3.10669 3.10669" actuatorfrcrange="-18 18" damping="2" armature="0.02" />
         <geom type="mesh" contype="0" conaffinity="0" group="1" density="0" rgba="0.8823529411764706 0.8941176470588236 0.8980392156862745 1.0" mesh="visual_wrist_pitch_l_j5_link_0" />
         <geom type="mesh" rgba="0 0 0 0" mesh="collision_wrist_pitch_l_j5_link_0" group="3" />
         <geom type="mesh" rgba="0 0 0 0" mesh="collision_wrist_pitch_l_j5_link_1" group="3" />
         <geom type="mesh" rgba="0 0 0 0" mesh="collision_wrist_pitch_l_j5_link_2" group="3" />
         <geom type="mesh" rgba="0 0 0 0" mesh="collision_wrist_pitch_l_j5_link_3" group="3" />
         <body name="wrist_yaw_l_j6_link" quat="0.5 0.5 -0.5 0.5">
          <inertial pos="0.00032659 0.00531336 -0.00030182" quat="0.718188 -0.0225408 0.00407878 0.695472" mass="0.72496" diaginertia="0.000517351 0.000460362 0.000425057" />
          <joint name="WRIST_YAW_L_J6" pos="0 0 0" axis="0 0 1" range="-1.0472 1.0472" actuatorfrcrange="-18 18" damping="2" armature="0.02" />
          <geom type="mesh" contype="0" conaffinity="0" group="1" density="0" rgba="0.8823529411764706 0.8941176470588236 0.8980392156862745 1.0" mesh="visual_wrist_yaw_l_j6_link_0" />
          <geom type="mesh" rgba="0 0 0 0" mesh="collision_wrist_yaw_l_j6_link_0" group="3" />
          <geom type="mesh" rgba="0 0 0 0" mesh="collision_wrist_yaw_l_j6_link_1" group="3" />
          <geom type="mesh" rgba="0 0 0 0" mesh="collision_wrist_yaw_l_j6_link_2" group="3" />
          <geom type="mesh" rgba="0 0 0 0" mesh="collision_wrist_yaw_l_j6_link_3" group="3" />
          <body name="wrist_roll_l_j7_link" quat="0.5 0.5 -0.5 0.5">
           <inertial pos="-9.108e-05 -0.0315325 0.00889371" quat="0.84481 0.535026 0.00229584 -0.00609725" mass="0.68606" diaginertia="0.00173691 0.00153911 0.000745263" />
           <joint name="WRIST_ROLL_L_J7" pos="0 0 0" axis="0 0 1" range="-1.5708 1.5708" actuatorfrcrange="-18 18" damping="2" armature="0.02" />
           <geom type="mesh" contype="0" conaffinity="0" group="1" density="0" rgba="0.8823529411764706 0.8941176470588236 0.8980392156862745 1.0" mesh="visual_wrist_roll_l_j7_link_0" />
           <geom type="mesh" contype="0" conaffinity="0" group="1" density="0" rgba="0.5137254901960784 0.5411764705882353 0.5647058823529412 1.0" mesh="visual_wrist_roll_l_j7_link_1" />
           <geom type="mesh" rgba="0 0 0 0" mesh="collision_wrist_roll_l_j7_link_0" group="3" />
           <geom type="mesh" rgba="0 0 0 0" mesh="collision_wrist_roll_l_j7_link_1" group="3" />
           <geom type="mesh" rgba="0 0 0 0" mesh="collision_wrist_roll_l_j7_link_2" group="3" />
           <geom type="mesh" rgba="0 0 0 0" mesh="collision_wrist_roll_l_j7_link_3" group="3" />
           <body name="left_ee" pos="0 -0.095 0" quat="0.5 0.5 -0.5 0.5">
            <site name="left_flange" pos="0 0 0" size="0.008" rgba="0.9 0.2 0.15 1" group="5" />
           </body>
          </body>
         </body>
        </body>
       </body>
      </body>
     </body>
    </body>
   </body>
   <body name="right_arm_base" pos="2.9142e-05 0 -1.121" quat="0.707107 0 0 0.707107">
    <body name="shoulder_pitch_r_j1_link" pos="-0.2215 2.9142e-05 1.121" quat="0.5 0.5 -0.5 -0.5">
     <inertial pos="2.347e-05 0.0055715 -0.03076" quat="0.711599 0.0343691 -0.0341702 0.700912" mass="1.9705" diaginertia="0.00529754 0.00492285 0.00184874" />
     <joint name="SHOULDER_PITCH_R_J1" pos="0 0 0" axis="0 0 1" range="-3.10669 3.10669" actuatorfrcrange="-108 108" damping="2" armature="0.02" />
     <geom type="mesh" contype="0" conaffinity="0" group="1" density="0" rgba="0.8823529411764706 0.8941176470588236 0.8980392156862745 1.0" mesh="visual_shoulder_pitch_r_j1_link_0" />
     <geom type="mesh" contype="0" conaffinity="0" group="1" density="0" rgba="0.611764705882353 0.6313725490196078 0.6509803921568628 1.0" mesh="visual_shoulder_pitch_r_j1_link_1" />
     <geom type="mesh" contype="0" conaffinity="0" group="1" density="0" rgba="0.01568627450980392 0.0196078431372549 0.023529411764705882 1.0" mesh="visual_shoulder_pitch_r_j1_link_2" />
     <geom type="mesh" rgba="0 0 0 0" mesh="collision_shoulder_pitch_r_j1_link_0" group="3" />
     <geom type="mesh" rgba="0 0 0 0" mesh="collision_shoulder_pitch_r_j1_link_1" group="3" />
     <geom type="mesh" rgba="0 0 0 0" mesh="collision_shoulder_pitch_r_j1_link_2" group="3" />
     <geom type="mesh" rgba="0 0 0 0" mesh="collision_shoulder_pitch_r_j1_link_3" group="3" />
     <body name="shoulder_roll_r_j2_link" quat="0.707107 0.707107 0 0">
      <inertial pos="0.00013483 0.0617046 0.00950639" quat="0.643375 0.765551 -3.57328e-05 0.000294349" mass="2.24398" diaginertia="0.0119493 0.0112156 0.00338374" />
      <joint name="SHOULDER_ROLL_R_J2" pos="0 0 0" axis="0 0 1" range="-2.0944 2.0944" actuatorfrcrange="-108 108" damping="2" armature="0.02" />
      <geom type="mesh" contype="0" conaffinity="0" group="1" density="0" rgba="0.8823529411764706 0.8941176470588236 0.8980392156862745 1.0" mesh="visual_shoulder_roll_r_j2_link_0" />
      <geom type="mesh" rgba="0 0 0 0" mesh="collision_shoulder_roll_r_j2_link_0" group="3" />
      <geom type="mesh" rgba="0 0 0 0" mesh="collision_shoulder_roll_r_j2_link_1" group="3" />
      <geom type="mesh" rgba="0 0 0 0" mesh="collision_shoulder_roll_r_j2_link_2" group="3" />
      <geom type="mesh" rgba="0 0 0 0" mesh="collision_shoulder_roll_r_j2_link_3" group="3" />
      <body name="elbow_pitch_r_j3_link" pos="0 0.287 0" quat="0.707107 -0.707107 0 0">
       <inertial pos="0.00968562 0.00246599 -0.046273" quat="0.782446 -0.0355285 -0.0735516 0.617337" mass="1.9242" diaginertia="0.00765215 0.00730789 0.0016338" />
       <joint name="ELBOW_PITCH_R_J3" pos="0 0 0" axis="0 0 1" range="-3.10669 3.10669" actuatorfrcrange="-66 66" damping="2" armature="0.02" />
       <geom type="mesh" contype="0" conaffinity="0" group="1" density="0" rgba="0.8823529411764706 0.8941176470588236 0.8980392156862745 1.0" mesh="visual_elbow_pitch_r_j3_link_0" />
       <geom type="mesh" rgba="0 0 0 0" mesh="collision_elbow_pitch_r_j3_link_0" group="3" />
       <geom type="mesh" rgba="0 0 0 0" mesh="collision_elbow_pitch_r_j3_link_1" group="3" />
       <geom type="mesh" rgba="0 0 0 0" mesh="collision_elbow_pitch_r_j3_link_2" group="3" />
       <geom type="mesh" rgba="0 0 0 0" mesh="collision_elbow_pitch_r_j3_link_3" group="3" />
       <body name="elbow_yaw_r_j4_link" pos="0.018 0 0" quat="0 0 -0.707107 0.707107">
        <inertial pos="0.00850411 -0.0471822 0.00941509" quat="0.741754 0.628694 0.0774999 -0.220317" mass="1.6085" diaginertia="0.00603244 0.00535875 0.00198228" />
        <joint name="ELBOW_YAW_R_J4" pos="0 0 0" axis="0 0 1" range="-2.53073 1.0472" actuatorfrcrange="-66 66" damping="2" armature="0.02" />
        <geom type="mesh" contype="0" conaffinity="0" group="1" density="0" rgba="0.8823529411764706 0.8941176470588236 0.8980392156862745 1.0" mesh="visual_elbow_yaw_r_j4_link_0" />
        <geom type="mesh" rgba="0 0 0 0" mesh="collision_elbow_yaw_r_j4_link_0" group="3" />
        <geom type="mesh" rgba="0 0 0 0" mesh="collision_elbow_yaw_r_j4_link_1" group="3" />
        <geom type="mesh" rgba="0 0 0 0" mesh="collision_elbow_yaw_r_j4_link_2" group="3" />
        <geom type="mesh" rgba="0 0 0 0" mesh="collision_elbow_yaw_r_j4_link_3" group="3" />
        <body name="wrist_pitch_r_j5_link" pos="0.018 -0.314 0" quat="0 0 -0.707107 0.707107">
         <inertial pos="-0.00051127 -0.00101064 -0.112717" quat="0.999438 0.00995046 0.00675781 0.0312997" mass="2.0883" diaginertia="0.00626924 0.00564262 0.00243436" />
         <joint name="WRIST_PITCH_R_J5" pos="0 0 0" axis="0 0 1" range="-3.10669 3.10669" actuatorfrcrange="-18 18" damping="2" armature="0.02" />
         <geom type="mesh" contype="0" conaffinity="0" group="1" density="0" rgba="0.8823529411764706 0.8941176470588236 0.8980392156862745 1.0" mesh="visual_wrist_pitch_r_j5_link_0" />
         <geom type="mesh" rgba="0 0 0 0" mesh="collision_wrist_pitch_r_j5_link_0" group="3" />
         <geom type="mesh" rgba="0 0 0 0" mesh="collision_wrist_pitch_r_j5_link_1" group="3" />
         <geom type="mesh" rgba="0 0 0 0" mesh="collision_wrist_pitch_r_j5_link_2" group="3" />
         <body name="wrist_yaw_r_j6_link" quat="0.5 0.5 -0.5 0.5">
          <inertial pos="0.00032659 -0.00531336 0.00030182" quat="0.695472 -0.00407878 0.0225408 0.718188" mass="0.72496" diaginertia="0.000517351 0.000460362 0.000425057" />
          <joint name="WRIST_YAW_R_J6" pos="0 0 0" axis="0 0 1" range="-1.0472 1.0472" actuatorfrcrange="-18 18" damping="2" armature="0.02" />
          <geom type="mesh" contype="0" conaffinity="0" group="1" density="0" rgba="0.8823529411764706 0.8941176470588236 0.8980392156862745 1.0" mesh="visual_wrist_yaw_r_j6_link_0" />
          <geom type="mesh" rgba="0 0 0 0" mesh="collision_wrist_yaw_r_j6_link_0" group="3" />
          <geom type="mesh" rgba="0 0 0 0" mesh="collision_wrist_yaw_r_j6_link_1" group="3" />
          <geom type="mesh" rgba="0 0 0 0" mesh="collision_wrist_yaw_r_j6_link_2" group="3" />
          <geom type="mesh" rgba="0 0 0 0" mesh="collision_wrist_yaw_r_j6_link_3" group="3" />
          <body name="wrist_roll_r_j7_link" quat="0.5 0.5 -0.5 0.5">
           <inertial pos="-9.108e-05 -0.0315325 0.00889371" quat="0.84481 0.535026 0.00229584 -0.00609725" mass="0.68606" diaginertia="0.00173691 0.00153911 0.000745263" />
           <joint name="WRIST_ROLL_R_J7" pos="0 0 0" axis="0 0 1" range="-1.5708 1.5708" actuatorfrcrange="-18 18" damping="2" armature="0.02" />
           <geom type="mesh" contype="0" conaffinity="0" group="1" density="0" rgba="0.8823529411764706 0.8941176470588236 0.8980392156862745 1.0" mesh="visual_wrist_roll_r_j7_link_0" />
           <geom type="mesh" contype="0" conaffinity="0" group="1" density="0" rgba="0.5137254901960784 0.5411764705882353 0.5647058823529412 1.0" mesh="visual_wrist_roll_r_j7_link_1" />
           <geom type="mesh" rgba="0 0 0 0" mesh="collision_wrist_roll_r_j7_link_0" group="3" />
           <geom type="mesh" rgba="0 0 0 0" mesh="collision_wrist_roll_r_j7_link_1" group="3" />
           <geom type="mesh" rgba="0 0 0 0" mesh="collision_wrist_roll_r_j7_link_2" group="3" />
           <geom type="mesh" rgba="0 0 0 0" mesh="collision_wrist_roll_r_j7_link_3" group="3" />
           <body name="right_ee" pos="0 -0.095 0" quat="0.5 0.5 -0.5 0.5">
            <site name="right_flange" pos="0 0 0" size="0.008" rgba="0.9 0.2 0.15 1" group="5" />
           </body>
          </body>
         </body>
        </body>
       </body>
      </body>
     </body>
    </body>
   </body>
  </body>
 </body>
 <contact>
  <exclude body1="base_link" body2="shoulder_pitch_l_j1_link" />
  <exclude body1="wrist_pitch_l_j5_link" body2="wrist_roll_l_j7_link" />
  <exclude body1="base_link" body2="shoulder_pitch_r_j1_link" />
  <exclude body1="wrist_pitch_r_j5_link" body2="wrist_roll_r_j7_link" />
 </contact>
 <actuator>
  <position name="SHOULDER_PITCH_L_J1_target" joint="SHOULDER_PITCH_L_J1" kp="700" kv="48" ctrllimited="true" ctrlrange="-3.1066860685499065 3.1066860685499065" forcelimited="true" forcerange="-108.0 108.0" />
  <position name="SHOULDER_ROLL_L_J2_target" joint="SHOULDER_ROLL_L_J2" kp="700" kv="48" ctrllimited="true" ctrlrange="-2.0943951023931953 2.0943951023931953" forcelimited="true" forcerange="-108.0 108.0" />
  <position name="ELBOW_PITCH_L_J3_target" joint="ELBOW_PITCH_L_J3" kp="700" kv="48" ctrllimited="true" ctrlrange="-3.1066860685499065 3.1066860685499065" forcelimited="true" forcerange="-66.0 66.0" />
  <position name="ELBOW_YAW_L_J4_target" joint="ELBOW_YAW_L_J4" kp="700" kv="48" ctrllimited="true" ctrlrange="-2.530727415391778 1.0471975511965976" forcelimited="true" forcerange="-66.0 66.0" />
  <position name="WRIST_PITCH_L_J5_target" joint="WRIST_PITCH_L_J5" kp="700" kv="48" ctrllimited="true" ctrlrange="-3.1066860685499065 3.1066860685499065" forcelimited="true" forcerange="-18.0 18.0" />
  <position name="WRIST_YAW_L_J6_target" joint="WRIST_YAW_L_J6" kp="700" kv="48" ctrllimited="true" ctrlrange="-1.0471975511965976 1.0471975511965976" forcelimited="true" forcerange="-18.0 18.0" />
  <position name="WRIST_ROLL_L_J7_target" joint="WRIST_ROLL_L_J7" kp="700" kv="48" ctrllimited="true" ctrlrange="-1.5707963267948966 1.5707963267948966" forcelimited="true" forcerange="-18.0 18.0" />
  <position name="SHOULDER_PITCH_R_J1_target" joint="SHOULDER_PITCH_R_J1" kp="700" kv="48" ctrllimited="true" ctrlrange="-3.1066860685499065 3.1066860685499065" forcelimited="true" forcerange="-108.0 108.0" />
  <position name="SHOULDER_ROLL_R_J2_target" joint="SHOULDER_ROLL_R_J2" kp="700" kv="48" ctrllimited="true" ctrlrange="-2.0943951023931953 2.0943951023931953" forcelimited="true" forcerange="-108.0 108.0" />
  <position name="ELBOW_PITCH_R_J3_target" joint="ELBOW_PITCH_R_J3" kp="700" kv="48" ctrllimited="true" ctrlrange="-3.1066860685499065 3.1066860685499065" forcelimited="true" forcerange="-66.0 66.0" />
  <position name="ELBOW_YAW_R_J4_target" joint="ELBOW_YAW_R_J4" kp="700" kv="48" ctrllimited="true" ctrlrange="-2.530727415391778 1.0471975511965976" forcelimited="true" forcerange="-66.0 66.0" />
  <position name="WRIST_PITCH_R_J5_target" joint="WRIST_PITCH_R_J5" kp="700" kv="48" ctrllimited="true" ctrlrange="-3.1066860685499065 3.1066860685499065" forcelimited="true" forcerange="-18.0 18.0" />
  <position name="WRIST_YAW_R_J6_target" joint="WRIST_YAW_R_J6" kp="700" kv="48" ctrllimited="true" ctrlrange="-1.0471975511965976 1.0471975511965976" forcelimited="true" forcerange="-18.0 18.0" />
  <position name="WRIST_ROLL_R_J7_target" joint="WRIST_ROLL_R_J7" kp="700" kv="48" ctrllimited="true" ctrlrange="-1.5707963267948966 1.5707963267948966" forcelimited="true" forcerange="-18.0 18.0" />
 </actuator>
</marvin>"""


class RigError(ValueError):
    """An asset, scene or argument of the arm rig is invalid."""


def _hands_module():
    """The shared DexHand hand-selection module (beside this file in task dirs, or scripts/dexhand/shared)."""
    try:
        import hands

        return hands
    except ModuleNotFoundError:
        path = Path(__file__).resolve().parent / "hands.py"
        spec = importlib.util.spec_from_file_location("hands", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules["hands"] = module
        spec.loader.exec_module(module)
        return module


hands = _hands_module()


# --------------------------------------------------------------------------------------------- assets
def tianji_dir(folder=None) -> Path:
    """``folder``, else ``DEXHAND_TIANJI_DIR``, else the image path, else a sibling of the Sharpa asset folder."""
    if folder:
        return Path(folder)
    if os.environ.get("DEXHAND_TIANJI_DIR"):
        return Path(os.environ["DEXHAND_TIANJI_DIR"])
    for candidate in (Path("/opt/dexhand/tianji"), hands.sharpa_dir().parent / "tianji"):
        if (candidate / "manifest.json").is_file():
            return candidate
    raise RigError("Tianji Marvin assets not found (set DEXHAND_TIANJI_DIR or use the eai-dexhand image)")


_VERIFIED: set[str] = set()


def verify_tianji(folder: Path) -> None:
    """Check every mesh the rig uses against the image's pinned Tianji manifest (sha256 + size)."""
    key = str(folder.resolve())
    if key in _VERIFIED:
        return
    manifest = json.loads((folder / "manifest.json").read_text())["files"]
    for relative in sorted(set(_template_meshes())):
        expected = manifest.get(relative)
        path = folder / relative
        if expected is None or not path.is_file():
            raise RigError(f"Tianji asset missing or unpinned: {relative}")
        data = path.read_bytes()
        if len(data) != expected["bytes"] or hashlib.sha256(data).hexdigest() != expected["sha256"]:
            raise RigError(f"Tianji asset integrity failure: {relative}")
    _VERIFIED.add(key)


def _template_meshes():
    for mesh in ET.fromstring(_MARVIN_XML).find("asset"):
        yield mesh.get("file").removeprefix("@TIANJI@/")


def sharpa_root(folder=None):
    """A fresh MJCF tree of the genuine right Sharpa Wave (``right_hand.xml``, absolute meshdir): the usual start of
    a DexHand family scene."""
    folder = Path(folder or hands.sharpa_dir())
    root = ET.parse(folder / "right_hand.xml").getroot()
    root.find("compiler").set("meshdir", str((folder / "assets/right").resolve()))
    return root


# --------------------------------------------------------------------------------------------- composition
def _numbers(text):
    return np.array([float(x) for x in text.split()])


def _text(values):
    return " ".join(f"{float(x):.17g}" for x in values)


def _section(root, tag):
    found = root.find(tag)
    return found if found is not None else ET.SubElement(root, tag)


def _reflect(element):
    """Mirror local frames in y (S = diag(1, -1, 1)): positions S p, rotations S R S, hinge axes det(S) S a."""
    for item in element.iter():
        if "pos" in item.attrib:
            item.set("pos", _text(_numbers(item.attrib["pos"]) * (1, -1, 1)))
        if "quat" in item.attrib:
            item.set("quat", _text(_numbers(item.attrib["quat"]) * (1, -1, 1, -1)))
        if "axis" in item.attrib:
            item.set("axis", _text(_numbers(item.attrib["axis"]) * (-1, 1, -1)))
        if "fromto" in item.attrib:
            item.set("fromto", _text(_numbers(item.attrib["fromto"]) * (1, -1, 1, 1, -1, 1)))
        if "fullinertia" in item.attrib:
            item.set("fullinertia", _text(_numbers(item.attrib["fullinertia"]) * (1, 1, 1, -1, 1, -1)))
        if "xyaxes" in item.attrib:
            raise RigError("The Wave asset is expected to use quaternion frames")


def mirrored_left_wave(root=None, folder=None):
    """The left Sharpa Wave: the right Wave reflected in y, every hand name renamed ``right_x`` / ``x`` -> ``left_x``
    (the convention of grinder_crank / picture_hang / tray_glass_carry). The right hand is taken from ``root`` when it
    holds ``right_hand_C_MC`` (so a family's tweaks to the right hand - fingertip friction, finger bias - are mirrored
    too), else from a fresh ``right_hand.xml``. Returns (body, meshes, excludes, actuators), all new elements."""
    folder = Path(folder or hands.sharpa_dir())
    fresh = ET.parse(folder / "right_hand.xml").getroot()
    names = {item.attrib["name"] for item in fresh.iter() if "name" in item.attrib and item.tag != "material"}
    mapping = {name: "left_" + name.removeprefix("right_") for name in names}
    source = root if root is not None and _find_body(root, WAVE_ROOT["right"])[1] is not None else fresh
    compiler = source.find("compiler")
    meshdir = Path(compiler.get("meshdir", "") if compiler is not None else "")
    if not meshdir.is_absolute():
        meshdir = (folder / meshdir).resolve()
    body = copy.deepcopy(_find_body(source, WAVE_ROOT["right"])[1])
    meshes = [copy.deepcopy(m) for m in source.find("asset").findall("mesh") if m.get("name") in mapping]
    excludes = [copy.deepcopy(e) for e in source.find("contact")
                if e.get("body1") in mapping and e.get("body2") in mapping]
    actuators = [copy.deepcopy(a) for a in source.find("actuator") if a.get("joint") in mapping]
    refs = {"name", "mesh", "joint", "body1", "body2", "geom1", "geom2", "site"}
    for item in [body, *meshes, *excludes, *actuators]:
        for sub in item.iter():
            for attr in refs & sub.attrib.keys():
                if sub.attrib[attr] in mapping:
                    sub.set(attr, mapping[sub.attrib[attr]])
    for mesh in meshes:
        mesh.set("file", str(meshdir / mesh.get("file")))
        mesh.set("scale", _text(_numbers(mesh.get("scale", "1 1 1")) * (1, -1, 1)))
    _reflect(body)
    return body, meshes, excludes, actuators


def _find_body(root, name):
    for parent in root.iter():
        for child in parent.findall("body"):
            if child.get("name") == name:
                return parent, child
    return None, None


def _yaw_quat(yaw):
    return (np.cos(yaw / 2), 0.0, 0.0, np.sin(yaw / 2))


def mount_marvin(root, base_pos=(0.0, 0.0, 0.0), base_yaw=0.0, hand="sharpa", active=("right",), *,
                 sharpa_folder=None, tianji_folder=None, wuji_folder=None, mount_names=None, wave_roots=None):
    """Mount the Marvin stand, both arms and both hands into the MJCF tree ``root`` (in place); return a record.

    ``root`` is the family's scene tree started from ``right_hand.xml`` (``sharpa_root()``), i.e. it holds the right
    Sharpa body ``right_hand_C_MC`` (anywhere; it is moved) with its defaults, meshes, excludes and finger actuators;
    a ``left_hand_C_MC`` body is used if present, otherwise the mirrored left Wave is added. Do not create a wrist
    stage. Apply your own hand tweaks (fingertip friction, finger bias) after this call, then compile.

    * ``base_pos`` / ``base_yaw``: world position of the stand origin (floor point under the torso; shoulders are
      1.121 m above it) and its heading (rad about +z; 0 = the robot faces world +x).
    * ``hand``: ``sharpa`` or ``wuji`` (genuine Wuji Hand 2.2 on both flanges via ``hands.replace_wave_hands``).
    * ``active``: the arm(s) the task drives; the others should be held at ``PARK`` (``default_targets``).
    * ``mount_names``: names of the fixed bodies on each flange that carry the hand ({"right": "wrist_stage"} keeps
      a family checker's ``model.body("wrist_stage")`` hand-root lookup working unchanged).
    * ``wave_roots``: names of the scene's existing Wave root bodies when they are not ``right_hand_C_MC`` /
      ``left_hand_C_MC`` (pot-style scenes: {"right": "r_hand_palm", "left": "l_hand_palm"}).
    """
    hand = hands.canonical(hand)
    active = tuple(active)
    if not active or any(side not in SIDES for side in active) or len(set(active)) != len(active):
        raise RigError(f"active must name 'left' and/or 'right', got {active!r}")
    mounts = dict(DEFAULT_MOUNTS, **(mount_names or {}))
    roots = dict(WAVE_ROOT, **(wave_roots or {}))
    sharpa_folder = Path(sharpa_folder or hands.sharpa_dir())
    tianji = tianji_dir(tianji_folder).resolve()
    verify_tianji(tianji)
    world, asset, actuator = root.find("worldbody"), _section(root, "asset"), _section(root, "actuator")
    contact = _section(root, "contact")
    for name in ("base_link", *FLANGE_BODY.values()):
        if _find_body(root, name)[1] is not None:
            raise RigError(f"scene already has a body named {name!r}")
    # The two Wave bodies (right from the scene, left mirrored unless present).
    bodies = {}
    for side in SIDES:
        parent, body = _find_body(root, roots[side])
        if body is None and side == "left":
            body, meshes, excludes, finger_actuators = mirrored_left_wave(root, sharpa_folder)
            asset.extend(meshes)
            contact.extend(excludes)
            actuator.extend(finger_actuators)
        elif body is None:
            raise RigError(f"the scene has no right Sharpa body {roots['right']} (start from sharpa_root())")
        else:
            parent.remove(body)
        bodies[side] = body
    # The Marvin stand and arms (pot_shelf_transfer's frozen robot, Tianji meshes resolved to absolute paths).
    template = ET.fromstring(_MARVIN_XML.replace("@TIANJI@", str(tianji)))
    asset.extend(list(template.find("asset")))
    base = template.find("body")
    base.set("pos", _text(base_pos))
    base.set("quat", _text(_yaw_quat(float(base_yaw))))
    world.append(base)
    contact.extend(list(template.find("contact")))
    for side in SIDES:
        _, flange = _find_body(base, FLANGE_BODY[side])
        mount = ET.SubElement(flange, "body", name=mounts[side], pos="0 0 0", quat="1 0 0 0")
        body = bodies[side]
        body.set("pos", "0 0 0")
        body.set("quat", "1 0 0 0")
        mount.append(body)
        # The palm shell sits on the wrist-roll link: never a self-contact (pot_shelf_transfer had no such pair).
        ET.SubElement(contact, "exclude", body1=WRIST_LINK[side], body2=body.get("name"))
    # Actuators: arms first, then the left hand's fingers, then the right hand's, then anything else.
    arm = list(template.find("actuator"))
    current = list(actuator)
    for item in current:
        actuator.remove(item)

    def hand_side(item):
        return _side_of(item.get("joint", ""))

    ordered = (arm + [a for a in current if hand_side(a) == "left"] + [a for a in current if hand_side(a) == "right"]
               + [a for a in current if hand_side(a) is None])
    actuator.extend(ordered)
    for keyframes in root.findall("keyframe"):
        root.remove(keyframes)
    records = []
    if hand == "wuji":
        records = hands.replace_wave_hands(root, "wuji", folder=wuji_folder)
    return {
        "robot": ROBOT_ID,
        "hand": hand,
        "active": active,
        "mounts": {side: mounts[side] for side in SIDES},
        "flanges": dict(FLANGE_BODY),
        "arm_actuators": list(ARM_ACTUATORS),
        "base_pos": [float(x) for x in base_pos],
        "base_yaw": float(base_yaw),
        "wuji": records,
    }


def _side_of(joint):
    """Hand side of a finger joint name (Wave ``left_``/``right_``, pot-style ``l_hand_``/``r_hand_``, Wuji)."""
    if joint.startswith(("left_", "l_hand_", "l_wuji_")):
        return "left"
    if joint.startswith(("right_", "r_hand_", "r_wuji_")):
        return "right"
    return None


# --------------------------------------------------------------------------------------------- model helpers
def layout(model) -> dict:
    """Column slices of an action row for a compiled rig model: ``arm[side]``, ``fingers[side]``, ``dim``."""
    names = [model.actuator(i).name for i in range(model.nu)]
    if names[:14] != ARM_ACTUATORS:
        raise RigError("the first 14 actuators are not the Marvin arm targets (left J1-J7, right J1-J7)")
    joints = [model.joint(int(model.actuator_trnid[i, 0])).name for i in range(model.nu)]

    sides = [_side_of(j) for j in joints[14:]]
    n_left = sides.count("left")
    n_right = sides.count("right")
    if sides[:n_left] != ["left"] * n_left or sides[n_left:n_left + n_right] != ["right"] * n_right:
        raise RigError("finger actuators are not ordered left hand, then right hand")
    return {
        "arm": {"left": slice(0, 7), "right": slice(7, 14)},
        "fingers": {"left": slice(14, 14 + n_left), "right": slice(14 + n_left, 14 + n_left + n_right)},
        "dim": model.nu,
        "names": names,
    }


def default_targets(model, arm_pose=None, fingers=None) -> np.ndarray:
    """A full action row: every arm at ``arm_pose[side]`` (default ``PARK``), fingers at ``fingers[side]`` (default
    each finger's lower-bound-clipped zero), clipped to the actuator control ranges."""
    lay = layout(model)
    row = np.zeros(model.nu)
    for side in SIDES:
        row[lay["arm"][side]] = (arm_pose or {}).get(side, PARK[side])
        if fingers and side in fingers:
            row[lay["fingers"][side]] = fingers[side]
    lo, hi = model.actuator_ctrlrange.T
    return np.clip(row, lo, hi)


def arm_qpos_index(model, side):
    """qpos addresses of the seven arm joints of ``side``."""
    return np.array([model.jnt_qposadr[model.joint(j).id] for j in ARM_JOINTS[side]])


def robot_body_ids(model) -> set:
    """Body ids of the stand + both arms (not the hands): contacts of these with the task are arm collisions."""
    import mujoco  # noqa: F401  (model is a mujoco.MjModel)

    base = model.body("base_link").id
    hand_roots = {model.body(name).id for name in _mount_names(model)}
    out = set()
    for b in range(model.nbody):
        chain, x = [], b
        while x not in (0, base) and x not in hand_roots:
            chain.append(x)
            x = int(model.body_parentid[x])
        if x == base:
            out.add(b)
    return out


def hand_body_ids(model, side) -> set:
    """Body ids of the hand on ``side`` (its flange mount body and everything below it)."""
    root = model.body(_mount_names(model)[SIDES.index(side)]).id
    out = set()
    for b in range(model.nbody):
        x = b
        while x > 0 and x != root:
            x = int(model.body_parentid[x])
        if x == root:
            out.add(b)
    return out


def _mount_names(model):
    names = []
    for side in SIDES:
        flange = model.body(FLANGE_BODY[side]).id
        children = [b for b in range(model.nbody) if int(model.body_parentid[b]) == flange]
        if len(children) != 1:
            raise RigError(f"{FLANGE_BODY[side]} must carry exactly one hand mount body")
        names.append(model.body(children[0]).name)
    return names
