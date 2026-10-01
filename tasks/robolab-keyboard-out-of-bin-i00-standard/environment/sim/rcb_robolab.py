"""
rcb_robolab.py — task-local tooling for NVIDIA RoboLab v0.3.1 (Isaac Lab 2.3.2 / Isaac Sim 5.1, the `isaac51` stack):
frozen task instance / privileged primitives / action recording / fresh-process replay. Same shape as the robosuite
example's rcb_traj.py, the BEHAVIOR tasks' rcb_behavior.py and the RoboWits tasks' rcb_robowits.py, so agents and
verifiers share one mental model.

Concepts
--------
instance   : one RoboLab benchmark task (e.g. BananaInBowlTask, registered as RoboLab's DROID joint-position env: Franka +
             Robotiq 2F-85) + the full scene state after the canonical reset (seeded `env.reset()` twice, as RoboLab's own
             evaluation loop does): robot root pose/velocity + joint positions/velocities and every rigid object's root
             pose/velocity, in Isaac Lab's `InteractiveScene.get_state()` layout. `make-instance` writes that state into
             instance.json ("initial_state"), so a task directory is self-contained: Session(instance=...) rebuilds the
             env from the pinned RoboLab code and restores the state with `env.reset_to(...)`, exactly what RoboLab's
             replay tool (examples/run_recorded.py) does. `state_sha` = sha1 over that flattened state. On load,
             `instance_exact` = sha equality and `instance_matches` = sha equality or every object pose / robot joint
             within tolerance (a different GPU or driver may change the last bits; a wrong asset or version moves things).
trajectory : the (T, 8) low-level actions handed to `env.step`, one row per control step (15 Hz: sim dt 1/120 s, decimation 8):
             7 absolute Franka joint-position targets (rad, panda_joint1..7, PD-tracked) + 1 gripper command (0 = open,
             1 = close; RoboLab's binary Robotiq action). Physics is PhysX on the CPU by default (`RCB_ROBOLAB_DEVICE`,
             frozen into instance.json): a live run, in-process replays and fresh-process replays of the same actions
             then all end in the same state. On the GPU pipeline they do not (contact-rich scenes amplify last-bit
             differences), which is why physics is pinned to the CPU.
             Only actions enter scoring: the task's own success predicate (RoboLab termination term `success`) is evaluated
             on the replayed final state.
budget     : there is no step budget: the agent's wall clock is the limit. MAX_STEPS only stops runaway trajectories
             (RoboLab's own episode_length_s is stretched past it, so its time-out term never ends an episode first).

CLI
---
  python rcb_robolab.py make-instance --task banana_in_bowl --seed 0 --out instance.json
  python rcb_robolab.py run-oracle    --task banana_in_bowl --instance instance.json --code oracle.py --out traj.npz
  python rcb_robolab.py replay        --task banana_in_bowl --instance instance.json --traj traj.npz [--repeat 1] [--video replay.mp4]
  python rcb_robolab.py render        --task banana_in_bowl --instance instance.json --traj traj.npz --out replay.mp4
  python rcb_robolab.py selftest      --task banana_in_bowl --seed 0 --code oracle.py --out-dir /tmp/selftest   # 4 fresh processes

Python (what the agent gets)
----------------------------
  from rcb_robolab import Session
  s = Session("banana_in_bowl", instance="/app/instance.json")   # ~1-2 min: Isaac Sim launch + scene build
  s.reset()                          # back to the frozen instance state (unlimited)
  p = s.primitives()                 # thin wrappers of the low-level action: move_ee, move_joints, set_gripper, hold, ...
  s.render_frame("egocentric_mirrored_camera")   # RGB (H, W, 3) uint8; s.render_grid(), s.render_video(actions, path)
  s.objects()                        # task objects: name -> position, orientation_wxyz, bounds, size, velocity
  s.record_start(); ...; actions = s.record_stop()   # (T, 8) low-level actions, one row per control step
  s.status()                         # {'success': bool, 'progress': float, 'sim_steps': int, 'resets': int, 'state_sha': str, 'terminated': bool}
  s.replay(actions)                  # resets, replays open-loop, returns status; the first replay in a process is exact
  s.save_trajectory(actions, "/app/output/trajectory.npz")
  s.camera_info()                    # {cam: intrinsic_cv, extrinsic_cv (world->camera, OpenCV axes), cam2world_gl, image_size, mount, moves}
  s.render_depth("wrist_cam")        # needs Session(..., depth=True): float32 (H, W) z-depth in metres, 0 = no reading
  s.robot_spec(); s.kinematics_spec() # joints (limits), gripper, controller gains, tool frames; what s.kinematics answers
  s.kinematics({"op": "fk", "q": q7}) # stateless FK / IK ({"op": "ik", "targets": {"tcp": pose7}, "seed": q7}) on a numpy model
  s.proprio()                        # measured joint_pos / joint_vel / tcp_pose / gripper_opening / joint_effort / gripper_cmd
None of the camera / kinematics / proprio calls steps physics or changes the simulator state.
"""
from __future__ import annotations

import os
os.environ.setdefault("OMNI_KIT_ACCEPT_EULA", "YES")
os.environ.setdefault("ACCEPT_EULA", "Y")
os.environ.setdefault("OMNI_KIT_ALLOW_ROOT", "1")
os.environ.setdefault("PYTHONUNBUFFERED", "1")

import argparse
import hashlib
import json
import math
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np

ROBOLAB_ROOT = Path(os.environ.get("ROBOLAB_ROOT", "/opt/robolab"))
# Interaction log: every Session (any process) appends one line per session start/reset/record/replay/exit, with the
# control steps consumed, to RCB_SESSION_LOG (default /app/output/rcb_session_log.jsonl, collected with the artifacts).
# It records the agent's whole debugging history, not just the trajectory it hands in (the verifier reports it as
# cost: agent_sessions / agent_resets / agent_sim_steps). Set RCB_SESSION_LOG="" to disable (the verifier does).
# The same line also goes to RCB_SESSION_LOG_KEEP (default /logs/agent/rcb_session_log.jsonl, where that directory
# exists: the agent's log directory). The host's rcb-log-mirror keeps an append-only copy of it, so the record
# survives even if the agent deletes or edits the /app/output copy (user 2026-09-26).
SESSION_LOG = os.environ.get("RCB_SESSION_LOG", "/app/output/rcb_session_log.jsonl")
SESSION_LOG_KEEP = os.environ.get("RCB_SESSION_LOG_KEEP", "/logs/agent/rcb_session_log.jsonl")


def _slog(ev: str, **kw) -> None:
    if not SESSION_LOG:
        return
    line = json.dumps({"ts": time.time(), "pid": os.getpid(), "ev": ev, **kw}) + "\n"
    try:
        os.makedirs(os.path.dirname(SESSION_LOG), exist_ok=True)
        with open(SESSION_LOG, "a") as f:
            f.write(line)
    except OSError:
        pass
    if SESSION_LOG_KEEP and os.path.isdir(os.path.dirname(SESSION_LOG_KEEP)):
        try:
            with open(SESSION_LOG_KEEP, "a") as f:
                f.write(line)
        except OSError:
            pass

# PhysX runs on the CPU by default: measured bit-exact (live == in-process replay == fresh-process replay) and, for these one-env
# tabletop scenes, faster than the GPU pipeline (~15 vs ~8 control steps/s incl. rendering). GPU PhysX reproduces a live run in a
# fresh process too, but in-process replays after reset_to drift by ~1 mm on the manipulated object. Rendering always uses the GPU.
DEFAULT_PHYSICS = {"device": os.environ.get("RCB_ROBOLAB_DEVICE", "cpu"),                          # PhysX on "cpu" or "cuda:0"
                   "enhanced_determinism": os.environ.get("RCB_ROBOLAB_ENHANCED_DETERMINISM", "0") == "1"}

# --------------------------------------------------------------------------- task family registry
TASKS: dict[str, dict] = {
    "banana_in_bowl": dict(
        robolab_task="BananaInBowlTask",
        text="Pick up the banana and place it in the bowl.",
        objects=["banana", "bowl"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "rubiks_cube_left_of_bowl": dict(
        robolab_task="RubiksCubeLeftOfBowlTask",
        text="Put the rubiks cube to the left of the bowl.",
        objects=["rubiks_cube", "banana", "bowl"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "animals_in_bin": dict(
        robolab_task="AnimalsInBinTask",
        text="Put the lizards in the bin.",
        objects=["rubiks_cube", "rubiks_cube_1", "rubiks_cube_2", "grey_bin", "lizard_figurine", "birdhouse", "yellow_block", "red_block", "green_block", "blue_block", "lizard_figurine_01"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "apple_and_yogurt_in_bowl": dict(
        robolab_task="AppleAndYogurtInBowlTask",
        text="Put the apple and yogurt in the bowl.",
        objects=["ceramic_mug", "glasses", "keyboard", "marker", "remote_control", "smartphone", "wooden_bowl", "spoon_big", "computer_mouse", "yogurt_cup", "pitcher", "plasticpail_a02", "apple_01"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "bagels_on_plate": dict(
        robolab_task="BagelsOnPlateTask",
        text="Put the bagels on the plate.",
        objects=["bagel_00", "bagel_06", "banana", "bowl", "plate_large"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "banana_then_rubiks_cube": dict(
        robolab_task="BananaThenRubiksCubeTask",
        text="Put the banana then the cube in the bowl.",
        objects=["rubiks_cube", "banana", "bowl"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "bananas_out_of_bin": dict(
        robolab_task="BananasOutOfBinTask",
        text="Take the bananas out.",
        objects=["banana", "banana_01", "banana_02", "banana_03", "banana_04", "grey_bin"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "bbq_sauce_in_bin": dict(
        robolab_task="BBQSauceInBinTask",
        text="Put the red BBQ sauce bottles in the grey bin.",
        objects=["grey_bin", "mug", "mustard", "bowl", "ranch_dressing", "bbq_sauce_bottle", "oatmeal_raisin_cookies", "canned_tuna", "soft_scrub", "wood_block", "coffee_pot", "bbq_sauce_bottle_01"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "black_items_in_bin": dict(
        robolab_task="BlackItemsInBinTask",
        text="Put the black items in the grey bin.",
        objects=["ceramic_mug", "glasses", "keyboard", "lizard_figurine", "marker", "remote_control", "smartphone", "wooden_bowl", "spoon_big", "computer_mouse", "yogurt_cup", "granola_bars", "grey_bin"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "block_stacking_order_agnostic": dict(
        robolab_task="BlockStackingOrderAgnosticTask",
        text="Stack the blocks into a tower.",
        objects=["red_block", "blue_block", "green_block", "yellow_block"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "block_stacking_specified_order": dict(
        robolab_task="BlockStackingSpecifiedOrderTask",
        text="Stack the blocks in the order from bottom to top: red, blue, green, yellow.",
        objects=["red_block", "blue_block", "green_block", "yellow_block"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "blocks_in_bin": dict(
        robolab_task="BlocksInBinTask",
        text="Sort all colored blocks into the bin.",
        objects=["rubiks_cube", "rubiks_cube_1", "rubiks_cube_2", "grey_bin", "lizard_figurine", "birdhouse", "yellow_block", "red_block", "green_block", "blue_block", "lizard_figurine_01"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "clean_up_toys": dict(
        robolab_task="CleanUpToysTask",
        text="Clean up all the smaller toys and leave the birdhouse on the table.",
        objects=["rubiks_cube", "rubiks_cube_1", "rubiks_cube_2", "grey_bin", "lizard_figurine", "birdhouse", "yellow_block", "red_block", "green_block", "blue_block", "lizard_figurine_01"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "clear_organic_objects": dict(
        robolab_task="ClearOrganicObjectsTask",
        text="Clear away the organic objects.",
        objects=["lemon_01", "lemon_02", "lime01", "lime01_01", "orange_01", "orange_02", "pomegranate01", "pumpkinlarge", "pumpkinsmall", "red_onion", "whitepackerbottle_a01", "avocado01", "crabbypenholder", "milkjug_a01", "serving_bowl", "utilityjug_a03", "right_bin"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "clutter_plastic": dict(
        robolab_task="ClutterPlasticTask",
        text="Put all plastic bottles away in the bin.",
        objects=["lemon_01", "lemon_02", "lime01", "lime01_01", "orange_01", "orange_02", "pomegranate01", "pumpkinlarge", "pumpkinsmall", "red_onion", "whitepackerbottle_a01", "avocado01", "crabbypenholder", "milkjug_a01", "serving_bowl", "utilityjug_a03", "right_bin"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "clutter_pumpkin": dict(
        robolab_task="ClutterPumpkinTask",
        text="Put all the pumpkins away in the bin.",
        objects=["lemon_01", "lemon_02", "lime01", "lime01_01", "orange_01", "orange_02", "pomegranate01", "pumpkinlarge", "pumpkinsmall", "red_onion", "whitepackerbottle_a01", "avocado01", "crabbypenholder", "milkjug_a01", "serving_bowl", "utilityjug_a03", "right_bin"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "condiments_in_bin": dict(
        robolab_task="CondimentsInBinTask",
        text="Sort the sauce condiments into the grey bin.",
        objects=["grey_bin", "mug", "mustard", "bowl", "ranch_dressing", "bbq_sauce_bottle", "oatmeal_raisin_cookies", "canned_tuna", "soft_scrub", "wood_block", "coffee_pot", "bbq_sauce_bottle_01"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "cooking_clear_plate": dict(
        robolab_task="CookingClearPlateTask",
        text="Put the two measuring cups outside of the plate.",
        objects=["redonion", "serving_bowl", "clay_plates", "wooden_spoons", "spatula", "storage_box", "tomato_sauce_can", "measuring_cups_1", "pink_spaghetti_spoon", "spoon_1", "green_serving_spoon", "storage_box_01", "ladle", "wooden_bowl", "potato_masher"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "cubes_and_blocks_in_bin": dict(
        robolab_task="CubesAndBlocksInBinTask",
        text="Put all the cubes and blocks in the bin.",
        objects=["rubiks_cube", "rubiks_cube_1", "rubiks_cube_2", "grey_bin", "lizard_figurine", "birdhouse", "yellow_block", "red_block", "green_block", "blue_block", "lizard_figurine_01"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "dishes_in_bin": dict(
        robolab_task="DishesInBinTask",
        text="Put the dishware in the grey bin.",
        objects=["mug", "mug_01", "bowl", "grey_bin", "banana_near", "banana_far", "rubiks_cube_top", "rubiks_cube_middle", "rubiks_cube_bottom", "ketchup_bottle"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "electronics_in_bin": dict(
        robolab_task="ElectronicsInBinTask",
        text="Put the electronic devices in the grey bin.",
        objects=["ceramic_mug", "glasses", "keyboard", "lizard_figurine", "marker", "remote_control", "smartphone", "wooden_bowl", "spoon_big", "computer_mouse", "yogurt_cup", "granola_bars", "grey_bin"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "food_packing2_boxes": dict(
        robolab_task="FoodPacking2BoxesTask",
        text="Pack boxed foods into the bin.",
        objects=["bin_a06", "cheez_it", "mustard", "sugar_box", "tomato_soup_can", "tuna_can"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "food_packing2_cans": dict(
        robolab_task="FoodPacking2CansTask",
        text="Pack canned foods into the bin.",
        objects=["bin_a06", "cheez_it", "mustard", "sugar_box", "tomato_soup_can", "tuna_can"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "food_packing3_boxes": dict(
        robolab_task="FoodPacking3BoxesTask",
        text="Pack boxed foods into the bin.",
        objects=["bin_a06", "cheez_it", "chocolate_pudding", "mustard", "spam_can", "sugar_box", "tomato_soup_can", "tuna_can"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "food_packing3_cans": dict(
        robolab_task="FoodPacking3CansTask",
        text="Pack canned foods into the bin.",
        objects=["bin_a06", "cheez_it", "chocolate_pudding", "mustard", "spam_can", "sugar_box", "tomato_soup_can", "tuna_can"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "food_packing_by_color": dict(
        robolab_task="FoodPackingByColorTask",
        text="Pack yellow objects in right container and blue object in the left container.",
        objects=["bin_a06", "cheez_it", "chocolate_pudding", "coffee_can", "mustard", "spam_can", "sugar_box", "tomato_soup_can", "bin_b03"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "fruits_green_limes_on_plate": dict(
        robolab_task="FruitsGreenLimesOnPlateTask",
        text="Put all the green fruit on the plate.",
        objects=["lemon_01", "lemon_02", "lime01", "lime01_01", "orange_01", "orange_02", "pomegranate01", "pumpkinlarge", "pumpkinsmall", "redonion", "serving_bowl", "clay_plates", "wooden_spoons", "spatula", "storage_box"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "fruits_on_plate": dict(
        robolab_task="FruitsOnPlateTask",
        text="Put all the fruits on the plate.",
        objects=["lemon_01", "lemon_02", "lime01", "lime01_01", "orange_01", "orange_02", "pomegranate01", "pumpkinlarge", "pumpkinsmall", "redonion", "serving_bowl", "clay_plates", "wooden_spoons", "spatula", "storage_box"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "fruits_on_plate3": dict(
        robolab_task="FruitsOnPlate3Task",
        text="Put three (3) fruits on the plate.",
        objects=["lemon_01", "lemon_02", "lime01", "lime01_01", "orange_01", "orange_02", "pomegranate01", "pumpkinlarge", "pumpkinsmall", "redonion", "serving_bowl", "clay_plates", "wooden_spoons", "spatula", "storage_box"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "green_spoons_in_pot": dict(
        robolab_task="GreenSpoonsInPotTask",
        text="Put the green spoons in the pot.",
        objects=["anza_medium", "ladle", "plate_large", "plate_small", "fork_big", "fork_small", "spatula_13", "spatula_14", "spatula_15", "pink_spaghetti_spoon", "ladle_01", "red_serving_spoon", "green_serving_spoon"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "hammers_in_left_bin": dict(
        robolab_task="HammersInLeftBinTask",
        text="Put the red hammer and black hammer in the left bin.",
        objects=["left_bin", "right_bin", "red_hammer", "husky_hammer", "cordless_drill", "spring_clamp"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "jugs_on_shelf": dict(
        robolab_task="JugsOnShelfTask",
        text="Put all the jugs on the shelf.",
        objects=["large_storage_rack", "whitepackerbottle_a01", "whitepackerbottle_a02", "utilityjug_a01", "utilityjug_a02", "squarepail_a01", "plasticpail_a02", "whitepackerbottle_a03"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "move_banana_to_bagel_plate": dict(
        robolab_task="MoveBananaToBagelPlateTask",
        text="Move the bananas to the bagel plate.",
        objects=["bowl", "banana", "bagel_07", "coffee_can", "banana_01", "yogurt_cup", "coffee_pot", "ceramic_mug", "pitcher", "fork_big", "spoon_big", "apple_01", "orange2", "milk_carton", "orange_juice_carton", "bagel_01", "bagel_02", "plate_small", "plate_large"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "non_hammer_tools_in_right_bin": dict(
        robolab_task="NonHammerToolsInRightBinTask",
        text="Put the non-hammer tools in the right bin.",
        objects=["left_bin", "right_bin", "red_hammer", "husky_hammer", "cordless_drill", "spring_clamp"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "plastic_bottles_in_square_pail": dict(
        robolab_task="PlasticBottlesInSquarePailTask",
        text="Put all the small plastic bottles in the square pail.",
        objects=["large_storage_rack", "whitepackerbottle_a01", "whitepackerbottle_a02", "utilityjug_a01", "utilityjug_a02", "squarepail_a01", "plasticpail_a02", "whitepackerbottle_a03"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "put_mugs_on_shelf": dict(
        robolab_task="PutMugsOnShelfTask",
        text="Put the two mugs on the shelf.",
        objects=["ceramic_mug", "mug", "rack_l04", "serving_bowl", "utilityjug_a01"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "put_two_mugs_on_shelf": dict(
        robolab_task="PutTwoMugsOnShelfTask",
        text="Put two (2) mugs on the wire shelf.",
        objects=["wireshelving_a01", "spatula_01", "plate_small", "fork_big", "fork_small", "ceramic_mug", "mug", "mug_01"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "recycle_carton": dict(
        robolab_task="RecycleCartonTask",
        text="Put the recyclable cartons in the grey bin.",
        objects=["container_a01", "milk_carton", "orange_juice_carton", "alphabet_soup_can", "smartphone", "mayonnaise_bottle", "ketchup_bottle", "mug"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "recycle_cartons_on_box": dict(
        robolab_task="RecycleCartonsOnBoxTask",
        text="Put the cartons that can be recycled on the box.",
        objects=["cubebox_a02", "milk_carton", "orange_juice_carton", "alphabet_soup_can", "smartphone", "mayonnaise_bottle", "ketchup_bottle", "mug"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "recycle_cartons_vertical_crate": dict(
        robolab_task="RecycleCartonsVerticalCrateTask",
        text="Put the cartons that can be recycled in the vertical crate.",
        objects=["container_a01", "milk_carton", "orange_juice_carton", "alphabet_soup_can", "smartphone", "mayonnaise_bottle", "ketchup_bottle", "mug"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "red_dishes_in_bin": dict(
        robolab_task="RedDishesInBinTask",
        text="Put the red dishware in the grey bin.",
        objects=["mug", "bowl", "grey_bin", "banana", "rubiks_cube"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "reorient_all_mugs": dict(
        robolab_task="ReorientAllMugsTask",
        text="Reorient all the mugs upright so that the opening is facing upwards.",
        objects=["red_mug", "bowl", "ceramic_mug", "upright_white_mug", "sideways_white_mug", "cordless_drill", "measuring_cup"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "reorient_jug": dict(
        robolab_task="ReorientJugTask",
        text="Stand the jug upright.",
        objects=["large_storage_rack", "whitepackerbottle_a01", "whitepackerbottle_a02", "utilityjug_a01", "utilityjug_a02", "squarepail_a01", "plasticpail_a02", "whitepackerbottle_a03"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "reorient_red_mug": dict(
        robolab_task="ReorientRedMugTask",
        text="Put the red mug upright so that the opening is facing upwards.",
        objects=["red_mug", "bowl", "ceramic_mug", "upright_white_mug", "sideways_white_mug", "cordless_drill", "measuring_cup"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "reorient_white_mugs": dict(
        robolab_task="ReorientWhiteMugsTask",
        text="Make sure all the white mugs are upright so that the opening is facing upwards.",
        objects=["red_mug", "bowl", "ceramic_mug", "upright_white_mug", "sideways_white_mug", "cordless_drill", "measuring_cup"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "rubiks_cube_and_banana": dict(
        robolab_task="RubiksCubeAndBananaTask",
        text="Put the cube and the banana in the bowl.",
        objects=["rubiks_cube", "banana", "bowl"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "rubiks_cube_then_banana": dict(
        robolab_task="RubiksCubeThenBananaTask",
        text="Put the cube then the banana in the bowl.",
        objects=["rubiks_cube", "banana", "bowl"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "rubiks_cubes_in_bin": dict(
        robolab_task="RubiksCubesInBinTask",
        text="Sort all rubiks cubes into the bin.",
        objects=["rubiks_cube", "rubiks_cube_1", "rubiks_cube_2", "grey_bin", "lizard_figurine", "birdhouse", "yellow_block", "red_block", "green_block", "blue_block", "lizard_figurine_01"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "spoons_in_pot": dict(
        robolab_task="SpoonsInPotTask",
        text="Put all of the serving spoons with no holes in the pot.",
        objects=["anza_medium", "ladle", "plate_large", "plate_small", "fork_big", "fork_small", "spatula_13", "spatula_14", "spatula_15", "pink_spaghetti_spoon", "ladle_01", "red_serving_spoon", "green_serving_spoon"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "stack3_rubiks_cube": dict(
        robolab_task="Stack3RubiksCubeTask",
        text="Stack the rubiks cubes in a tower.",
        objects=["rubiks_cube", "rubiks_cube_1", "rubiks_cube_2"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "take_mugs_off_of_shelf": dict(
        robolab_task="TakeMugsOffOfShelfTask",
        text="Take the mugs off the shelf.",
        objects=["ceramic_mug", "mug", "rack_l04", "serving_bowl", "utilityjug_a01"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "throw_away_snacks": dict(
        robolab_task="ThrowAwaySnacksTask",
        text="Put away the snacks in the bin.",
        objects=["ceramic_mug", "glasses", "keyboard", "marker", "remote_control", "smartphone", "wooden_bowl", "spoon_big", "computer_mouse", "yogurt_cup", "pitcher", "plasticpail_a02", "apple_01"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "tool_organization_both": dict(
        robolab_task="ToolOrganizationBothTask",
        text="Put hammers in the right bin and do not touch anything else.",
        objects=["left_bin", "right_bin", "red_hammer", "husky_hammer", "cordless_drill", "spring_clamp"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "tools_picking_all_hammers": dict(
        robolab_task="ToolsPickingAllHammersTask",
        text="Take out all the hammers and put them on the table.",
        objects=["clamp", "cordless_drill", "spring_clamp", "husky_hammer", "blue_hammer", "red_hammer", "wood_hammer", "left_bin", "center_bin", "right_bin", "clamp_01"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "unstack_rubiks_cube": dict(
        robolab_task="UnstackRubiksCubeTask",
        text="Unstack the rubiks cube tower.",
        objects=["mug", "banana", "ketchup_bottle", "rubiks_cube_middle", "rubiks_cube_top", "rubiks_cube_bottom", "bowl", "grey_bin"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "utensils_in_mug": dict(
        robolab_task="UtensilsInMugTask",
        text="Put the fork and spoon in the ceramicmug.",
        objects=["bowl", "banana", "bagel_07", "coffee_can", "banana_01", "yogurt_cup", "coffee_pot", "ceramic_mug", "pitcher", "fork_big", "spoon_big", "apple_01", "orange2", "milk_carton", "orange_juice_carton", "bagel_01", "bagel_02", "plate_small", "plate_large"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "white_mugs_in_bin": dict(
        robolab_task="WhiteMugsInBinTask",
        text="Clean up the white mugs.",
        objects=["mug", "mug_01", "grey_bin", "banana_near", "banana_far", "rubiks_cube_middle", "rubiks_cube_top", "rubiks_cube_bottom", "ketchup_bottle", "bowl"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "yellow_and_white_objects_in_bin": dict(
        robolab_task="YellowAndWhiteObjectsInBinTask",
        text="Put all white objects and yellow objects in the grey bin.",
        objects=["mug", "banana", "grey_bin", "bowl", "ketchup_bottle", "rubiks_cube_top", "rubiks_cube_middle", "rubiks_cube_bottom"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "rubiks_cube_behind_bowl": dict(
        robolab_task="RubiksCubeBehindBowlTask",
        text="Put the rubiks cube behind the bowl.",
        objects=["rubiks_cube", "banana", "bowl"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "rubiks_cube_in_front_of_bowl": dict(
        robolab_task="RubiksCubeInFrontOfBowlTask",
        text="Put the rubiks cube in front of the bowl.",
        objects=["rubiks_cube", "banana", "bowl"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "rubiks_cube_right_of_bowl": dict(
        robolab_task="RubiksCubeRightOfBowlTask",
        text="Put the rubiks cube to the right of the bowl.",
        objects=["rubiks_cube", "banana", "bowl", "mug", "grey_bin"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "white_mug_in_center_of_table": dict(
        robolab_task="WhiteMugInCenterOfTableTask",
        text="Put the white mug in the center of the table.",
        objects=["mug", "bowl", "alphabet_soup_can", "orange_juice_carton", "smartphone", "milk_carton", "banana", "rubiks_cube"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "stack_white_mugs": dict(
        robolab_task="StackWhiteMugsTask",
        text="Stack the white mugs on top of each other.",
        objects=["red_mug", "bowl", "ceramic_mug", "upright_white_mug", "sideways_white_mug", "cordless_drill", "measuring_cup"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "stack_yellow_on_red": dict(
        robolab_task="StackYellowOnRedTask",
        text="Stack the yellow block on the red block.",
        objects=["rubiks_cube", "rubiks_cube_1", "rubiks_cube_2", "grey_bin", "lizard_figurine", "birdhouse", "yellow_block", "red_block", "green_block", "blue_block", "lizard_figurine_01"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "pick_up_blue_pitcher": dict(
        robolab_task="PickUpBluePitcherTask",
        text="Pick up the large blue pitcher.",
        objects=["plasticjerrican_a02", "plasticpail_a02", "pitcher"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "bananas_in_bin_one_more": dict(
        robolab_task="BananasInBinOneMoreTask",
        text="Put one (1) more bananas in the grey bin.",
        objects=["banana", "banana_01", "banana_02", "banana_03", "banana_04", "grey_bin"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "bananas_in_bin_three_total": dict(
        robolab_task="BananasInBinThreeTotalTask",
        text="Make sure there are 3 (three) bananas in the grey bin.",
        objects=["banana", "banana_01", "banana_02", "banana_03", "banana_04", "grey_bin"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "marker_in_mug": dict(
        robolab_task="MarkerInMugTask",
        text="Put the whiteboard marker in the mug.",
        objects=["ceramic_mug", "glasses", "keyboard", "lizard_figurine", "marker", "remote_control", "rubiks_cube", "smartphone", "wooden_bowl", "spoon_big", "computer_mouse", "yogurt_cup", "oatmeal_raisin_cookies", "granola_bars"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "pink_spoon_in_pot": dict(
        robolab_task="PinkSpoonInPotTask",
        text="Put the pink spaghetti spoon in the pot.",
        objects=["anza_medium", "ladle", "plate_large", "plate_small", "fork_big", "fork_small", "spatula_13", "spatula_14", "spatula_15", "pink_spaghetti_spoon", "ladle_01", "red_serving_spoon", "green_serving_spoon"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "spoon_in_mug": dict(
        robolab_task="SpoonInMugTask",
        text="Put the metal spoon that's in the wooden bowl in the mug.",
        objects=["ceramic_mug", "glasses", "keyboard", "lizard_figurine", "marker", "remote_control", "smartphone", "wooden_bowl", "spoon_big", "computer_mouse", "yogurt_cup", "granola_bars", "grey_bin"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "take_spatula_off_shelf": dict(
        robolab_task="TakeSpatulaOffShelfTask",
        text="Take the spatula off the shelf and put it on the table.",
        objects=["wireshelving_a01", "spatula_01", "plate_small", "fork_big", "fork_small", "ceramic_mug", "mug", "mug_01"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "put_bowl_on_shelf_top": dict(
        robolab_task="PutBowlOnShelfTopTask",
        text="Put the serving bowl anywhere on the shelf in front of you.",
        objects=["ceramic_mug", "mug", "rack_l04", "serving_bowl", "utilityjug_a01"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "bowl_stacking_left_on_right": dict(
        robolab_task="BowlStackingLeftOnRightTask",
        text="Stack the left bowl on the right bowl.",
        objects=["bowl_1", "bowl_2"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "bowl_stacking_right_on_left": dict(
        robolab_task="BowlStackingRightOnLeftTask",
        text="Stack the right bowl on the left bowl.",
        objects=["bowl_1", "bowl_2"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "butter_above_raisin": dict(
        robolab_task="ButterAboveRaisinTask",
        text="Pick up the butter box and place it on top of the raisin box.",
        objects=["butter", "raisin_box"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "clamp_in_right_bin": dict(
        robolab_task="ClampInRightBinTask",
        text="Put the spring clamp in the right bin.",
        objects=["left_bin", "right_bin", "red_hammer", "husky_hammer", "cordless_drill", "spring_clamp"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "cooking_pick_pasta_tool": dict(
        robolab_task="CookingPickPastaToolTask",
        text="Move the pink tool from this utensil container to the other utensil holder.",
        objects=["redonion", "serving_bowl", "clay_plates", "wooden_spoons", "spatula", "storage_box", "tomato_sauce_can", "measuring_cups_1", "pink_spaghetti_spoon", "spoon_1", "green_serving_spoon", "storage_box_01", "ladle", "wooden_bowl", "potato_masher"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "keyboard_out_of_bin": dict(
        robolab_task="KeyboardOutOfBinTask",
        text="Take the keyboard out of the bin and put it on the table.",
        objects=["ceramic_mug", "glasses", "keyboard", "lizard_figurine", "marker", "remote_control", "smartphone", "wooden_bowl", "spoon_big", "computer_mouse", "yogurt_cup", "granola_bars", "grey_bin"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "mustard_above_raisin": dict(
        robolab_task="MustardAboveRaisinTask",
        text="Place the mustard on the raisin box.",
        objects=["mustard_bottle", "raisin_box"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "mustard_in_left_bin": dict(
        robolab_task="MustardInLeftBinTask",
        text="Put the mustard in the left bin.",
        objects=["mustard", "grey_bin_right", "grey_bin_left"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "mustard_in_right_bin": dict(
        robolab_task="MustardInRightBinTask",
        text="Put the mustard in the right bin.",
        objects=["mustard", "grey_bin_right", "grey_bin_left"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "pick_glasses": dict(
        robolab_task="PickGlassesTask",
        text="Pick up the eye glasses.",
        objects=["ceramic_mug", "glasses", "keyboard", "lizard_figurine", "marker", "remote_control", "rubiks_cube", "smartphone", "wooden_bowl", "spoon_big", "computer_mouse", "yogurt_cup", "oatmeal_raisin_cookies", "granola_bars"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "pick_orange_object": dict(
        robolab_task="PickOrangeObjectTask",
        text="Pick up the orange measuring cup.",
        objects=["redonion", "serving_bowl", "clay_plates", "wooden_spoons", "spatula", "storage_box", "tomato_sauce_can", "measuring_cups_1", "pink_spaghetti_spoon", "spoon_1", "green_serving_spoon", "storage_box_01", "ladle", "wooden_bowl", "potato_masher"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "pick_up_green_object": dict(
        robolab_task="PickUpGreenObjectTask",
        text="Pick up the green vegetable block.",
        objects=["frozen_vegetable_block", "blackandbrassbowl_large", "screwtoppail_a01", "utilityjug_a02"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "tools_picking_drill": dict(
        robolab_task="ToolsPickingDrillTask",
        text="Select the cordless drill and put it on the table.",
        objects=["clamp", "cordless_drill", "spring_clamp", "husky_hammer", "blue_hammer", "red_hammer", "wood_hammer", "left_bin", "center_bin", "right_bin", "clamp_01"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "tools_picking_hammer": dict(
        robolab_task="ToolsPickingHammerTask",
        text="Select the blue hammer and put it on the table.",
        objects=["clamp", "cordless_drill", "spring_clamp", "husky_hammer", "blue_hammer", "red_hammer", "wood_hammer", "left_bin", "center_bin", "right_bin", "clamp_01"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "larger_object_raisin_box_in_bin": dict(
        robolab_task="LargerObjectRaisinBoxInBinTask",
        text="Place the larger object in the grey bin.",
        objects=["butter", "grey_bin", "raisin_box"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
    "take_measuring_spoon_out": dict(
        robolab_task="TakeMeasuringSpoonOutTask",
        text="Take the white colored measuring spoon out of the red bowl and put it on the table.",
        objects=["red_mug", "bowl", "ceramic_mug", "upright_white_mug", "sideways_white_mug", "cordless_drill", "measuring_cup"],
        simulator="robolab", robot="franka-robotiq-2f85", image="robolab",
    ),
}

ACTION_DIM = 8
CONTROL_HZ = 15                      # sim dt 1/120 s x decimation 8
DEFAULT_SEED = 0
MAX_STEPS = 100_000                  # no step budget (the wall clock is); this only stops a runaway trajectory (~1.9 h of sim time)
ARM_SLICE = slice(0, 7)
GRIP_INDEX = 7
GRIPPER_OPEN, GRIPPER_CLOSE = 0.0, 1.0
TCP_DISTANCE = 0.162    # gripper flange (RoboLab's `eef_frame` = base_link) -> ends of the CLOSED fingertips along the approach axis
                        # (measured by lowering the closed gripper onto the table: 0.162 m; open fingertips end at 0.149 m; the pads
                        # extend ~5.7 cm back from the tips). Robotiq 2F-85 spec: 162.8 mm.
ACTION_LAYOUT = ("8 entries per control step (15 Hz): panda_joint1..7 absolute joint-position targets (rad, PD-tracked, "
                 "RoboLab DroidJointPositionActionCfg) + gripper command (0 = open, 1 = close; Robotiq 2F-85 binary action). "
                 "Poses are in the env-local frame (= robot root frame for the Franka: base at the origin, x forward, z up), "
                 "quaternions are WXYZ.")
# Depth: every camera also renders Isaac's "distance_to_image_plane" (z-depth, metres) when the Session has depth on: off by
# default (the default behaviour and cost are unchanged; about 13 % slower steps with it on), Session(..., depth=True) turns it
# on, the limited service always does, the replay CLI never. Rendering reads the state, it never steps it: the state hashes
# of live runs and replays are the same with and without it.
DEPTH_TYPE = "distance_to_image_plane"
DEPTH_MAX_M = 65.535                 # farther readings are reported as 0 (no reading), as in the limited protocol
DEFAULT_DEPTH = os.environ.get("RCB_ROBOLAB_DEPTH", "0") == "1"
GL2CV = np.diag([1.0, -1.0, -1.0, 1.0])     # OpenGL camera axes (x right, y up, z back) <-> OpenCV (x right, y down, z forward)
TCP_FRAME, EEF_FRAME = "tcp", "eef_frame"   # the fingertip-centre tool frame; RoboLab's eef_frame (the flange, rotated)
FLANGE_BODY = "base_link"                   # the Robotiq 2F-85 base body: RoboLab's eef_frame and the wrist camera sit on it
GRIPPER_OPENING_M = (0.0018, 0.085)         # pad-to-pad distance closed on nothing (finger_joint pi/4) / fully open, measured
                                            # on the pad meshes (0.0018 / 0.08497 m); Robotiq 2F-85 stroke: 85 mm
# The arm is a Franka Emika Panda (panda_joint*, the Panda's position limits, not an FR3's): its datasheet's rated joint velocity
# (rad/s) and torque (N m), reported next to the limits the simulator enforces
PANDA_RATED = {f"panda_joint{i}": (2.175, 87.0) if i <= 4 else (2.61, 12.0) for i in range(1, 8)}

_APP = None


def _log(*a: Any) -> None:
    print("[rcb]", *a, file=sys.stderr, flush=True)


class PrimitiveError(RuntimeError):
    """A primitive could not be planned or executed (the episode is still alive unless said otherwise)."""


# --------------------------------------------------------------------------- small geometry helpers (numpy, wxyz)
def quat_to_mat(q) -> np.ndarray:
    w, x, y, z = [float(v) for v in q]
    n = math.sqrt(w * w + x * x + y * y + z * z) or 1.0
    w, x, y, z = w / n, x / n, y / n, z / n
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def mat_to_quat(R) -> np.ndarray:
    R = np.asarray(R, dtype=np.float64)
    t = np.trace(R)
    if t > 0:
        s = math.sqrt(t + 1.0) * 2; w = 0.25 * s; x = (R[2, 1] - R[1, 2]) / s; y = (R[0, 2] - R[2, 0]) / s; z = (R[1, 0] - R[0, 1]) / s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2; w = (R[2, 1] - R[1, 2]) / s; x = 0.25 * s; y = (R[0, 1] + R[1, 0]) / s; z = (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2; w = (R[0, 2] - R[2, 0]) / s; x = (R[0, 1] + R[1, 0]) / s; y = 0.25 * s; z = (R[1, 2] + R[2, 1]) / s
    else:
        s = math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2; w = (R[1, 0] - R[0, 1]) / s; x = (R[0, 2] + R[2, 0]) / s; y = (R[1, 2] + R[2, 1]) / s; z = 0.25 * s
    q = np.array([w, x, y, z]); return q / np.linalg.norm(q)


def quat_mul(a, b) -> np.ndarray:
    w1, x1, y1, z1 = a; w2, x2, y2, z2 = b
    return np.array([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2])


def quat_inv(q) -> np.ndarray:
    q = np.asarray(q, dtype=np.float64); return np.array([q[0], -q[1], -q[2], -q[3]]) / float(q @ q)


def quat_from_axis_angle(axis, angle: float) -> np.ndarray:
    a = np.asarray(axis, dtype=np.float64); a = a / np.linalg.norm(a); s = math.sin(angle / 2)
    return np.array([math.cos(angle / 2), a[0] * s, a[1] * s, a[2] * s])


def rot_angle(Ra, Rb) -> float:
    c = (np.trace(np.asarray(Ra).T @ np.asarray(Rb)) - 1.0) / 2.0
    return float(math.acos(max(-1.0, min(1.0, c))))


def quat_angle(qa, qb) -> float:
    return rot_angle(quat_to_mat(qa), quat_to_mat(qb))


def wrap_angle(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


def pose_compose(p1, q1, p2, q2) -> tuple[np.ndarray, np.ndarray]:
    """T1 * T2 for (position, wxyz quaternion) pairs."""
    return np.asarray(p1, dtype=np.float64) + quat_to_mat(q1) @ np.asarray(p2, dtype=np.float64), quat_mul(q1, q2)


def pose_inverse(p, q) -> tuple[np.ndarray, np.ndarray]:
    qi = quat_inv(q); return -(quat_to_mat(qi) @ np.asarray(p, dtype=np.float64)), qi


def hom(R=None, p=None) -> np.ndarray:
    """4x4 homogeneous transform from a rotation matrix and a translation."""
    T = np.eye(4)
    if R is not None:
        T[:3, :3] = R
    if p is not None:
        T[:3, 3] = np.asarray(p, dtype=np.float64).reshape(3)
    return T


def pose7(T) -> list[float]:
    """4x4 -> [x, y, z, qw, qx, qy, qz] (qw >= 0)."""
    q = mat_to_quat(np.asarray(T)[:3, :3])
    q = -q if q[0] < 0 else q
    return [float(v) for v in np.asarray(T)[:3, 3]] + [float(v) for v in q]


def pose7_to_T(p) -> np.ndarray:
    p = np.asarray(p, dtype=np.float64).reshape(7)
    return hom(quat_to_mat(p[3:]), p[:3])


def axis_rot(axis, a: float) -> np.ndarray:
    x, y, z = [float(v) for v in axis]; c, s = math.cos(a), math.sin(a); C = 1.0 - c
    return np.array([[c + x * x * C, x * y * C - z * s, x * z * C + y * s], [y * x * C + z * s, c + y * y * C, y * z * C - x * s],
                     [z * x * C - y * s, z * y * C + x * s, c + z * z * C]])


def rotvec(R) -> np.ndarray:
    """Axis * angle (rad) of a rotation matrix."""
    R = np.asarray(R, dtype=np.float64)
    ang = math.acos(max(-1.0, min(1.0, (float(np.trace(R)) - 1.0) / 2.0)))
    v = np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]])
    if ang < 1e-9:
        return v / 2.0
    if math.pi - ang < 1e-4:                                   # near 180 deg the antisymmetric part vanishes
        A = (R + np.eye(3)) / 2.0; i = int(np.argmax(np.diag(A))); ax = A[:, i] / math.sqrt(max(A[i, i], 1e-12))
        return ax / np.linalg.norm(ax) * ang
    return v / (2.0 * math.sin(ang)) * ang


class ArmModel:
    """Stateless kinematics of a fixed-base serial arm in numpy (no simulator call): revolute joints given by their USD joint
    frames (child = parent . A . Rot(axis, q) . B), then fixed mounts and named tool frames. FK, the geometric Jacobian and a
    damped-least-squares IK that starts from the seed (then the home pose, then mid-range) and clamps every step to the limits."""

    def __init__(self, root: str, base_T, joints: list, fixed: list, lo, hi, home):
        self.root, self.base_T = root, np.asarray(base_T, dtype=np.float64)
        self.joints, self.fixed = joints, fixed                # joints: (name, parent, child, A, axis, B); fixed: (parent, child, M)
        self.lo, self.hi, self.home = (np.asarray(x, dtype=np.float64) for x in (lo, hi, home))
        self.links = [root] + [j[2] for j in joints] + [f[1] for f in fixed]
        parent = {j[2]: j[1] for j in joints}; parent.update({f[1]: f[0] for f in fixed})
        jidx = {j[2]: i for i, j in enumerate(joints)}
        self._n_moving = {}
        for f in self.links:                                   # how many leading joints move frame f
            g = f
            while g not in jidx and g in parent:
                g = parent[g]
            self._n_moving[f] = jidx[g] + 1 if g in jidx else 0

    def _fk(self, q):
        T = {self.root: self.base_T}; P, Ax = [], []
        for i, (_n, parent, child, A, axis, B) in enumerate(self.joints):
            J = T[parent] @ A
            P.append(J[:3, 3].copy()); Ax.append(J[:3, :3] @ axis)
            T[child] = J @ hom(axis_rot(axis, float(q[i]))) @ B
        for parent, child, M in self.fixed:
            T[child] = T[parent] @ M
        return T, P, Ax

    def fk(self, q) -> dict[str, np.ndarray]:
        """{frame: 4x4 pose} of every frame for joint positions q."""
        return self._fk(np.asarray(q, dtype=np.float64).reshape(-1))[0]

    def jacobian(self, T, P, Ax, frame: str) -> np.ndarray:
        J = np.zeros((6, len(self.joints))); pf = T[frame][:3, 3]
        for i in range(self._n_moving[frame]):
            J[:3, i] = np.cross(Ax[i], pf - P[i]); J[3:, i] = Ax[i]
        return J

    def ik(self, targets: dict, seed=None, tol_p: float = 1e-3, tol_r: float = 1e-2, max_iters: int = 300,
           lam: float = 0.05, max_step: float = 0.25):
        """targets {frame: 4x4} -> (q, ok, {frame: (position error m, rotation error rad)}) of the best q found."""
        best = None
        seeds = ([np.asarray(seed, dtype=np.float64).reshape(-1)] if seed is not None else []) + [self.home, (self.lo + self.hi) / 2.0]
        for s0 in seeds:
            q = np.clip(s0, self.lo, self.hi)
            for _ in range(int(max_iters)):
                T, P, Ax = self._fk(q)
                es, Js, errs = [], [], {}
                for f, Tt in targets.items():
                    ep = Tt[:3, 3] - T[f][:3, 3]; er = rotvec(Tt[:3, :3] @ T[f][:3, :3].T)
                    errs[f] = (float(np.linalg.norm(ep)), float(np.linalg.norm(er)))
                    es += [ep, er]; Js.append(self.jacobian(T, P, Ax, f))
                score = max(max(e[0] / tol_p, e[1] / tol_r) for e in errs.values())
                if best is None or score < best[0]:
                    best = (score, q.copy(), errs)
                if score <= 1.0:
                    return q, True, errs
                e = np.concatenate(es); Jm = np.vstack(Js)
                dq = Jm.T @ np.linalg.solve(Jm @ Jm.T + lam * lam * np.eye(len(e)), e)
                m = float(np.max(np.abs(dq)))
                q = np.clip(q + (dq * (max_step / m) if m > max_step else dq), self.lo, self.hi)
        return best[1], False, best[2]


# --------------------------------------------------------------------------- Isaac app (one per process)
def _launch_app():
    global _APP
    if _APP is None:
        import cv2  # noqa: F401  RoboLab: must be imported before isaaclab
        from isaaclab.app import AppLauncher
        argv, sys.argv = sys.argv, [sys.argv[0]]   # Kit must not see our CLI flags
        try:
            _APP = AppLauncher({"headless": True, "enable_cameras": True, "device": "cuda:0"}).app
        finally:
            sys.argv = argv
    return _APP


def _tt(x):
    """warp array (Isaac Lab 2.3 returns those for some physx views) or torch tensor -> torch tensor."""
    import torch
    if isinstance(x, torch.Tensor):
        return x
    import warp as wp
    return wp.to_torch(x)


# --------------------------------------------------------------------------- session
class Session:
    def __init__(self, task: str, instance: str | Path | None = None, *, seed: int | None = None, strict: bool = False,
                 max_steps: int | None = None, output_dir: str | None = None, physics: dict | None = None, depth: bool | None = None):
        if task not in TASKS:
            raise KeyError(f"unknown task {task!r}; known: {list(TASKS)}")
        self.task, self.spec = task, TASKS[task]
        self.depth_enabled = DEFAULT_DEPTH if depth is None else bool(depth)
        inst = None
        if instance is not None:
            inst = json.load(open(instance))
            if inst.get("task") != task:
                raise ValueError(f"instance task {inst.get('task')} != session task {task}")
            seed = int(inst["seed"])
            if inst.get("physics"):
                physics = dict(inst["physics"])          # the frozen instance decides the physics configuration
        self.physics = dict(DEFAULT_PHYSICS, **(physics or {}))
        self.seed = DEFAULT_SEED if seed is None else int(seed)
        max_steps = int(max_steps or MAX_STEPS)
        t0 = time.time()
        _log(f"launching Isaac Sim (headless, cameras on) for {self.spec['robolab_task']} seed {self.seed}; ~1-2 min ...")
        self.app = _launch_app()
        import torch
        self.th = torch
        import robolab.constants as C
        C.VERBOSE = False; C.DEBUG = False; C.RECORD_IMAGE_DATA = False
        from robolab.constants import set_output_dir
        self.output_dir = output_dir or tempfile.mkdtemp(prefix="rcb_robolab_")
        set_output_dir(self.output_dir)
        from robolab.registrations.droid.auto_env_registrations_jointpos import auto_register_droid_envs
        from robolab.core.environments.factory import get_envs
        from robolab.core.environments.runtime import create_env
        from robolab.core.world.world_state import get_world
        auto_register_droid_envs(task=self.spec["robolab_task"])
        envs = get_envs(task=self.spec["robolab_task"])
        if not envs:
            raise RuntimeError(f"RoboLab registered no env for task {self.spec['robolab_task']}")
        self.env_name = envs[0]
        _log(f"app up in {time.time() - t0:.0f}s; building env {self.env_name} (physics {self.physics}) ...")
        from robolab.core.environments.config import parse_env_cfg
        dev = str(self.physics["device"])
        cfg = parse_env_cfg(self.env_name, device=dev, seed=self.seed, num_envs=1, use_fabric=True)
        # RoboLab ends an episode at the task's own episode_length_s (banana_in_bowl: 50 s = 750 control steps): its
        # time_out term freezes the env. There is no step budget here, so stretch it past the runaway guard MAX_STEPS;
        # never shorten it.
        step_dt = float(cfg.sim.dt) * int(cfg.decimation)
        if max_steps and int(max_steps) > math.ceil(float(cfg.episode_length_s) / step_dt - 1e-9):
            cfg.episode_length_s = (int(max_steps) + 2) * step_dt
            _log(f"episode_length_s raised to {cfg.episode_length_s:.1f} s so the {int(max_steps)}-step budget ends first")
        if self.physics.get("enhanced_determinism") and hasattr(cfg.sim.physx, "enable_enhanced_determinism"):
            cfg.sim.physx.enable_enhanced_determinism = True
        if self.depth_enabled:              # every camera also renders z-depth (read by render_depth; never touches physics)
            from isaaclab.sensors import CameraCfg
            for name, cam in list(vars(cfg.scene).items()):
                if isinstance(cam, CameraCfg) and DEPTH_TYPE not in cam.data_types and "depth" not in cam.data_types:
                    setattr(cfg.scene, name, cam.replace(data_types=[*cam.data_types, DEPTH_TYPE]))
        self.env, self.env_cfg = create_env(cfg, device=dev, seed=self.seed, num_envs=1, use_fabric=True, instruction_type="default")
        self.world = get_world(self.env)
        self.device = self.env.device
        self.robot = self.env.scene["robot"]
        self.arm_ids, self.arm_names = self.robot.find_joints(["panda_joint.*"], preserve_order=True)
        self.arm_ids = list(self.arm_ids)
        if len(self.arm_ids) != 7:
            raise RuntimeError(f"expected 7 arm joints, found {self.arm_names}")
        self.finger_id = int(self.robot.find_joints(["finger_joint"])[0][0])
        self.instruction = str(self.env_cfg.instruction)
        self.control_dt = float(self.env_cfg.sim.dt) * int(self.env_cfg.decimation)
        self._recording: list[np.ndarray] | None = None
        self._video: dict | None = None
        self._obs = None
        self.episode_done = False
        self.n_steps = 0
        self._resets = 0
        self._total_steps = 0
        self._end_logged = False
        _slog("session_start", task=task, seed=self.seed)
        import atexit
        atexit.register(self._log_end)
        self._ik = None
        self._ik_body = None

        # canonical reset (RoboLab's evaluation loop resets twice before an episode), then the frozen state if given
        self.env.reset(); self._obs, _ = self.env.reset()
        self.reset_state = self._tree_to_lists(self.env.scene.get_state(is_relative=True))
        if inst is not None:
            self._restore(inst["initial_state"])
        self.initial_state = self._tree_to_lists(self.env.scene.get_state(is_relative=True))
        self.instance_sha = self.state_sha()
        self.max_steps = int(max_steps or self.env.max_episode_length)
        expected = inst.get("state_sha") if inst else None
        self.instance_exact = expected is None or expected == self.instance_sha
        self.instance_matches = self.instance_exact or (inst is not None and self._poses_match(inst))
        if not self.instance_exact:
            if self.instance_matches:
                _log(f"WARNING: state sha {self.instance_sha} != {expected} but every object / joint pose matches within tolerance (different host?)")
            else:
                msg = f"instance state sha {self.instance_sha} != expected {expected} and poses differ (asset / simulator version drift?)"
                if strict:
                    raise RuntimeError(msg)
                _log("WARNING:", msg)
        self._targets = self._current_targets()
        self._table_top = self._table_top_z()
        self._tool_setup()
        self._reset_ee_quat = self.ee_pose()[1]                 # the Franka's reset pose points the gripper straight down
        self.reset_closing_dir = self.finger_closing_dir()      # measured, not assumed
        self._model, self._cams = None, {}                      # the 2.2 extras never break a Session (replays and grading need none)
        try:
            self._kin_setup()                                   # reads the USD and the current link poses; writes nothing
        except Exception as exc:  # noqa: BLE001
            self._model = None; _log(f"WARNING: no kinematic model / robot spec / proprio extras: {repr(exc)[:200]}")
        try:
            self._camera_setup()
        except Exception as exc:  # noqa: BLE001
            self._cams = {}; _log(f"WARNING: no camera info / depth: {repr(exc)[:200]}")
        _log(f"instance ready in {time.time() - t0:.0f}s; state_sha={self.instance_sha}; max_steps={self.max_steps} "
             f"({self.max_steps * self.control_dt:.0f} s at {1 / self.control_dt:.0f} Hz); instruction: {self.instruction!r}")

    # ---- state tree helpers (InteractiveScene.get_state layout, env 0)
    def _tree_to_lists(self, tree: dict) -> dict:
        out = {}
        for k in sorted(tree):
            v = tree[k]
            out[k] = self._tree_to_lists(v) if isinstance(v, dict) else v[0].detach().cpu().numpy().astype(np.float32).tolist()
        return out

    def _flat_state(self) -> np.ndarray:
        parts: list[np.ndarray] = []

        def rec(t):
            for k in sorted(t):
                v = t[k]
                if isinstance(v, dict):
                    rec(v)
                else:
                    parts.append(v[0].detach().cpu().numpy().astype(np.float32).ravel())
        rec(self.env.scene.get_state(is_relative=True))
        return np.concatenate(parts) if parts else np.zeros(0, np.float32)

    def state_sha(self) -> str:
        return hashlib.sha1(np.ascontiguousarray(self._flat_state()).tobytes()).hexdigest()[:16]

    def _restore(self, tree_lists: dict) -> None:
        """env.reset_to(...) with the stored state overlaid on the scene's current full state (RoboLab's replay recipe)."""
        cur = self.env.scene.get_state(is_relative=True)

        def overlay(c, r):
            for k, v in r.items():
                if k not in c:
                    _log(f"WARNING: stored state has {k!r} which is not in the scene; skipping")
                    continue
                if isinstance(v, dict):
                    overlay(c[k], v)
                else:
                    row = self.th.as_tensor(np.asarray(v, dtype=np.float32), device=self.device).unsqueeze(0)
                    c[k] = row.repeat(self.env.num_envs, *([1] * (row.ndim - 1)))
        overlay(cur, tree_lists)
        self.env.reset_eval_state()          # RobolabEnv would otherwise FREEZE instead of reset after stepping
        self._obs, _ = self.env.reset_to(cur, env_ids=None, is_relative=True)

    def _poses_match(self, inst: dict, pos_tol: float = 2e-3, quat_tol: float = 2e-2, joint_tol: float = 2e-3) -> bool:
        try:
            objs = self.objects()
            for name, ref in (inst.get("objects") or {}).items():
                cur = objs.get(name)
                if cur is None:
                    return False
                if np.max(np.abs(np.asarray(cur["position"]) - np.asarray(ref["position"]))) > pos_tol:
                    return False
                q0, q1 = np.asarray(cur["orientation_wxyz"]), np.asarray(ref["orientation_wxyz"])
                if min(np.max(np.abs(q0 - q1)), np.max(np.abs(q0 + q1))) > quat_tol:
                    return False
            ref_q = inst.get("robot_joint_positions")
            if ref_q is not None and np.max(np.abs(self.joint_positions() - np.asarray(ref_q))) > joint_tol:
                return False
            return bool(inst.get("objects"))
        except Exception as exc:  # noqa: BLE001
            _log("pose comparison failed:", repr(exc)[:120])
            return False

    def _table_top_z(self) -> float | None:
        try:
            lo, hi = self.object_bounds("table")
            return float(hi[2])
        except Exception:  # noqa: BLE001
            return None

    # ---- episode control
    def reset(self) -> None:
        """Return to the frozen instance state (exact state restore through env.reset_to; controller targets back to the
        reset pose; RoboLab's termination bookkeeping cleared)."""
        _slog("reset", task=self.task, n=self._resets + 1, sim_steps_before=self.n_steps)
        self._resets += 1
        self._total_steps += self.n_steps
        self._recording = None
        self.episode_done = False
        self.n_steps = 0
        self._restore(self.initial_state)
        self._targets = self._current_targets()

    def _current_targets(self) -> np.ndarray:
        q = self.robot.data.joint_pos[0].detach().cpu().numpy().astype(np.float64)
        grip = GRIPPER_CLOSE if q[self.finger_id] > math.pi / 8 else GRIPPER_OPEN
        return np.concatenate([q[self.arm_ids], [grip]])

    def step(self, action) -> bool:
        """Apply one low-level action (7 joint targets + gripper command, see ACTION_LAYOUT) for one control step (1/15 s).
        Returns True when the episode is over: the task terminated (success) or MAX_STEPS ran (a runaway guard, not a
        budget); further steps raise."""
        a = np.asarray(action, dtype=np.float32).reshape(-1)
        if a.size != ACTION_DIM:
            raise ValueError(f"action must have {ACTION_DIM} entries, got {a.size}")
        if not np.all(np.isfinite(a)):
            raise ValueError("action contains nan/inf")
        if self.episode_done:
            raise PrimitiveError("episode is over (task terminated, or the runaway guard); call reset() before stepping again")
        if self._recording is not None:
            self._recording.append(a.copy())
        self._obs, _, term, trunc, _ = self.env.step(self.th.as_tensor(a, device=self.device).unsqueeze(0))
        self._targets = a.astype(np.float64)
        self.n_steps += 1
        if self._video is not None and self.n_steps % self._video["every"] == 0:
            self._video_add()
        if bool(self.env.all_terminated) or self.n_steps >= self.max_steps:
            self.episode_done = True
        return self.episode_done

    def hold_action(self) -> np.ndarray:
        """The action that keeps the current joint targets and gripper command (what the robot does when idle)."""
        return self._targets.copy()

    def status(self) -> dict[str, Any]:
        res = self.env.get_env_results()[0]
        success = res.get("success")
        if success is None:
            try:
                success = bool(self.env.termination_manager.get_term("success")[0].item())
            except Exception:  # noqa: BLE001
                success = False
        progress = 0.0
        try:
            from robolab.core.logging.results import get_current_subtask_info
            info = get_current_subtask_info(self.env, 0) or {}
            progress = float(info.get("score") or 0.0)
        except Exception:  # noqa: BLE001
            pass
        return {"success": bool(success), "progress": round(progress, 4), "sim_steps": int(self.n_steps), "resets": self._resets,
                "state_sha": self.state_sha(), "terminated": bool(self.env.all_terminated)}

    # ---- recording / trajectories
    def record_start(self) -> None:
        self._recording = []

    def record_stop(self) -> np.ndarray:
        acts = np.stack(self._recording) if self._recording else np.zeros((0, ACTION_DIM), np.float32)
        self._recording = None
        _slog("record", task=self.task, n_actions=int(len(acts)))
        return acts.astype(np.float32)

    def save_trajectory(self, actions: np.ndarray, path: str | Path, meta: dict | None = None) -> None:
        np.savez(path, actions=np.asarray(actions, dtype=np.float32), task=self.task, robolab_task=self.spec["robolab_task"],
                 seed=self.seed, instance_sha=self.instance_sha, action_dim=ACTION_DIM, action_layout=ACTION_LAYOUT,
                 meta=json.dumps(meta or {}))

    def replay(self, actions: np.ndarray) -> dict[str, Any]:
        """Open-loop replay after reset(). The FIRST replay in a process reproduces a fresh process (and the live run) bit
        for bit; later in-process replays can differ in the last bits (env.reset_to does not restore every PhysX internal),
        which is why the verifier replays in two fresh processes. Stops when the task terminates (success ends the episode)."""
        self.reset()
        for a in np.asarray(actions, dtype=np.float32):
            if self.step(a):
                break
        st = self.status()
        _slog("replay", task=self.task, n_actions=int(len(actions)), success=st["success"])
        return st

    # ---- rendering (same API as the RoboTwin tasks' Session: render_frame / render_grid / render_video). Isaac Lab renders
    # every camera with each control step; these return the frames of the current state.
    VIDEO_CAMERAS: tuple[str, ...] = ("egocentric_mirrored_camera", "over_shoulder_left_camera", "wrist_cam")

    def _images(self) -> dict[str, np.ndarray]:
        from robolab.core.observations.observation_utils import unpack_image_obs, unpack_viewport_cams
        out = {}
        for fn in (unpack_viewport_cams, unpack_image_obs):
            try:
                for k, v in fn(self._obs, env_id=0).items():
                    if k != "combined_image":
                        out[k] = np.ascontiguousarray(np.asarray(v)[..., :3].astype(np.uint8))
            except Exception:  # noqa: BLE001
                pass
        return out

    def render_frame(self, camera: str = "egocentric_mirrored_camera", size: tuple[int, int] | None = None) -> np.ndarray:
        """RGB (H, W, 3) uint8 of one camera for the current state (see VIDEO_CAMERAS); `size=(w, h)` resizes."""
        imgs = self._images()
        if camera not in imgs:
            raise KeyError(f"unknown camera {camera!r}; known: {sorted(imgs)}")
        img = imgs[camera]
        if size is not None and (img.shape[1], img.shape[0]) != tuple(size):
            import cv2
            img = cv2.resize(img, tuple(size), interpolation=cv2.INTER_LINEAR)
        return img

    def render_depth(self, camera: str = "egocentric_mirrored_camera") -> np.ndarray:
        """float32 (H, W) z-depth in metres of one camera for the current state: the distance from the camera plane along the
        optical axis, for the same pixels as render_frame(camera) (same render); 0 = no reading (nothing rendered there, or
        farther than 65.535 m). Reads the renderer's output, never steps."""
        if not self.depth_enabled:
            raise RuntimeError("this Session renders no depth: create it with Session(..., depth=True) (every camera then also "
                               "renders z-depth; steps are about 13 % slower)")
        sen = self.env.scene.sensors.get(camera) if camera in self._cams else None
        if sen is None:
            raise KeyError(f"unknown camera {camera!r}; known: {list(self._cams)}")
        out = sen.data.output
        z = np.array(_tt(out[DEPTH_TYPE if DEPTH_TYPE in out else "depth"])[0, ..., 0].detach().cpu().numpy(), dtype=np.float32)
        z[~np.isfinite(z) | (z <= 0) | (z > DEPTH_MAX_M)] = 0.0
        return z

    def _camera_setup(self) -> None:
        """Per camera, once: Isaac's pinhole intrinsics, the image size, the clipping range and the mount. A camera prim under a
        robot link rides on it (link -> camera read from the USD; its world pose is then the link's measured pose times that
        offset, which is what the renderer draws: Isaac Lab's cached sensor pose is the pose at startup); any other is static."""
        from pxr import Usd, UsdGeom, UsdPhysics
        cache = UsdGeom.XformCache(Usd.TimeCode.Default())
        origin = _tt(self.env.scene.env_origins)[0].detach().cpu().numpy().astype(np.float64)
        bodies = set(self.robot.body_names)
        self._cams: dict[str, dict] = {}
        for cam in self.VIDEO_CAMERAS:
            sen = self.env.scene.sensors.get(cam)
            if sen is None or not getattr(sen, "_sensor_prims", None):
                continue
            prim = sen._sensor_prims[0].GetPrim(); parent = prim.GetParent()
            K = _tt(sen.data.intrinsic_matrices)[0].detach().cpu().numpy().astype(np.float64)
            H, W = (int(x) for x in sen.data.image_shape)
            near, far = (float(x) for x in UsdGeom.Camera(prim).GetClippingRangeAttr().Get())
            m = {"K": K, "size": [W, H], "range": [near, min(far, DEPTH_MAX_M)], "link_T_cv": None, "world_T_cv": None}
            if parent.GetName() in bodies and parent.HasAPI(UsdPhysics.RigidBodyAPI):
                m["link_T_cv"] = np.array(cache.ComputeRelativeTransform(prim, parent)[0], dtype=np.float64).T @ GL2CV
                m["mount"] = {"type": "link", "parent_link": parent.GetName(), "link_T_cam_cv": m["link_T_cv"].tolist()}
            else:
                gl = np.array(cache.GetLocalToWorldTransform(prim), dtype=np.float64).T; gl[:3, 3] -= origin
                m["world_T_cv"] = gl @ GL2CV
                m["mount"] = {"type": "static", "extrinsic_cv": np.linalg.inv(m["world_T_cv"])[:3].tolist(), "cam2world_gl": gl.tolist()}
            self._cams[cam] = m

    def _cam_world_T_cv(self, cam: str) -> np.ndarray:
        m = self._cams[cam]
        if m["world_T_cv"] is not None:
            return m["world_T_cv"]
        p, q = self.body_pose(m["mount"]["parent_link"])
        return hom(quat_to_mat(q), p) @ m["link_T_cv"]

    def camera_info(self, cameras=None) -> dict[str, dict]:
        """{cam: {"intrinsic_cv": 3x3, "extrinsic_cv": 3x4 world -> camera (OpenCV axes: x right, y down, z forward),
        "cam2world_gl": 4x4 camera -> world (OpenGL axes: x right, y up, z back), "image_size": [W, H], "mount": static world
        pose | parent link + fixed link_T_cam_cv, "moves": bool, "depth_range_m": [near, far]}} for the current state, as
        nested lists; world = the env-local frame. A pixel (u, v) of a point X_cam: u = fx X/Z + cx, v = fy Y/Z + cy. Reads only."""
        out = {}
        for c in (list(cameras) if cameras is not None else list(self._cams)):
            if c not in self._cams:
                raise KeyError(f"unknown camera {c!r}; known: {list(self._cams)}")
            m = self._cams[c]; Tw = self._cam_world_T_cv(c)
            out[c] = {"intrinsic_cv": m["K"].tolist(), "extrinsic_cv": np.linalg.inv(Tw)[:3].tolist(), "cam2world_gl": (Tw @ GL2CV).tolist(),
                      "image_size": list(m["size"]), "mount": json.loads(json.dumps(m["mount"])), "moves": m["mount"]["type"] == "link",
                      "depth_range_m": list(m["range"])}
        return out

    def render_grid(self, cameras: tuple[str, ...] = VIDEO_CAMERAS, cols: int = 3, size: tuple[int, int] = (320, 240)) -> np.ndarray:
        """One image tiling `cameras` (row-major, `cols` per row; each resized to `size`)."""
        tiles = [self.render_frame(c, size=size) for c in cameras]
        while len(tiles) % cols:
            tiles.append(np.zeros_like(tiles[0]))
        return np.concatenate([np.concatenate(tiles[i:i + cols], axis=1) for i in range(0, len(tiles), cols)], axis=0)

    def render_video(self, actions: np.ndarray, path: str | Path, *, every: int = 1, fps: int = 15,
                     cameras: tuple[str, ...] = VIDEO_CAMERAS, cols: int = 3, size: tuple[int, int] = (320, 240)) -> dict[str, Any]:
        """Replay `actions` from the frozen instance (reset() first) and write an MP4 of `cameras` tiled, one frame every
        `every` control steps (+ `<path>.last.png`). Returns the final status plus n_frames and the video path. Like
        replay(), only the first replay in a process is bit-exact (the CLI `render` runs in a fresh process)."""
        import imageio.v2 as imageio
        self.reset()
        path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
        n = 0
        # frames go straight to the encoder: a long episode's frames would not fit in memory
        with imageio.get_writer(str(path), fps=fps, format="FFMPEG", codec="libx264", macro_block_size=1) as w:
            def grab() -> np.ndarray:
                nonlocal n
                f = self.render_grid(cameras, cols=cols, size=size); w.append_data(f); n += 1
                return f
            last = grab()
            for i, a in enumerate(np.asarray(actions, dtype=np.float32)):
                done = self.step(a)
                if (i + 1) % every == 0 or done:
                    last = grab()
                if done:
                    break
        imageio.imwrite(str(path.with_suffix(".last.png")), last)
        return {**self.status(), "n_frames": n, "video": str(path)}

    # ---- video while stepping (viewport camera + wrist camera; the verifier's replay.mp4)
    def start_video(self, path: str | Path, fps: int = 15, every: int | None = None) -> None:
        import imageio.v2 as imageio
        every = every or max(1, CONTROL_HZ // fps)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        # frames go straight to the encoder: a long episode's frames would not fit in memory
        w = imageio.get_writer(str(path), fps=fps, format="FFMPEG", codec="libx264", macro_block_size=1)
        self._video = {"path": str(path), "every": every, "writer": w, "last": None}
        self._video_add()

    def _video_add(self) -> None:
        f = self._video_frame(); self._video["writer"].append_data(f); self._video["last"] = f

    def _video_frame(self) -> np.ndarray:
        from robolab.core.observations.observation_utils import unpack_image_obs, unpack_viewport_cams
        main = None; wrist = None
        try:
            main = unpack_viewport_cams(self._obs, env_id=0).get("combined_image")
        except Exception:  # noqa: BLE001
            pass
        try:
            wrist = unpack_image_obs(self._obs, env_id=0).get("combined_image")
        except Exception:  # noqa: BLE001
            pass
        if main is None and wrist is None:
            return np.zeros((240, 320, 3), np.uint8)
        if main is None:
            return np.ascontiguousarray(np.asarray(wrist)[..., :3].astype(np.uint8))
        main = np.asarray(main)[..., :3].astype(np.uint8)
        if wrist is not None:
            import cv2
            w = np.asarray(wrist)[..., :3].astype(np.uint8)
            h = main.shape[0]
            w = cv2.resize(w, (int(w.shape[1] * h / w.shape[0]), h))
            main = np.concatenate([main, w], axis=1)
        return np.ascontiguousarray(main)

    def stop_video(self) -> str | None:
        if self._video is None:
            return None
        import imageio.v2 as imageio
        v, self._video = self._video, None
        v["writer"].close()
        imageio.imwrite(str(Path(v["path"]).with_suffix(".last.png")), v["last"])
        return v["path"]

    # ---- objects / robot state (env-local frame = robot root frame for the Franka)
    def object_names(self) -> list[str]:
        return list(self.env.scene.rigid_objects.keys())

    def object_pose(self, name: str) -> tuple[np.ndarray, np.ndarray]:
        """(position(3), quaternion wxyz(4)) of a rigid object in the env-local frame."""
        objs = self.env.scene.rigid_objects
        if name not in objs:
            raise KeyError(f"unknown object {name!r}; known: {self.object_names()}")
        o = objs[name]
        pos = (o.data.root_pos_w[0] - self.env.scene.env_origins[0]).detach().cpu().numpy().astype(np.float64)
        quat = o.data.root_quat_w[0].detach().cpu().numpy().astype(np.float64)
        return pos, quat

    def object_bounds(self, name: str) -> np.ndarray:
        """Axis-aligned bounding box [[xmin,ymin,zmin],[xmax,ymax,zmax]] of an object in the env-local frame (RoboLab WorldState)."""
        def _np(x):
            return np.asarray(x.detach().cpu().numpy() if hasattr(x, "detach") else x, dtype=np.float64)
        try:
            corners, _centroid = self.world.get_bbox(name, env_id=0)      # 8 world-frame corners of the oriented box
            c = _np(corners).reshape(-1, 3)
            lo, hi = c.min(axis=0), c.max(axis=0)
        except Exception:  # noqa: BLE001
            lo, hi = self.world.get_aabb(name)
            lo, hi = _np(lo).reshape(-1)[:3], _np(hi).reshape(-1)[:3]
        origin = self.env.scene.env_origins[0].detach().cpu().numpy().astype(np.float64)
        return np.stack([lo - origin, hi - origin])

    def objects(self) -> dict[str, dict]:
        """Rigid objects by name -> position, orientation_wxyz, bounds (AABB [[min],[max]]), size, velocity (env-local frame)."""
        out = {}
        for n in self.object_names():
            try:
                p, q = self.object_pose(n)
                d = {"position": [round(float(x), 5) for x in p], "orientation_wxyz": [round(float(x), 6) for x in q]}
                try:
                    b = self.object_bounds(n)
                    d["bounds"] = [[round(float(x), 5) for x in row] for row in b]
                    d["size"] = [round(float(x), 5) for x in (b[1] - b[0])]
                except Exception:  # noqa: BLE001
                    pass
                v = self.env.scene.rigid_objects[n].data.root_lin_vel_w[0].detach().cpu().numpy()
                d["velocity"] = [round(float(x), 5) for x in v]
                out[n] = d
            except Exception as exc:  # noqa: BLE001
                _log(f"objects(): {n}: {repr(exc)[:100]}")
        return out

    def object_points(self, name: str, max_points: int = 4000) -> np.ndarray:
        """Surface points (N, 3) of a rigid object's visual meshes in the env-local frame: the USD mesh vertices (cached, in the
        object's frame, scale applied) transformed by the object's current pose. Curved objects (a banana) have their bounding-box
        centre off the body, so grasp points should come from these points rather than from the pose."""
        if not hasattr(self, "_pts_cache"):
            self._pts_cache = {}
        if name not in self._pts_cache:
            import omni.usd
            from pxr import Usd, UsdGeom
            from robolab.core.utils import usd_utils
            obj = self.env.scene.rigid_objects[name]
            stage = omni.usd.get_context().get_stage()
            import re
            path = re.sub(r"env_\.\*", "env_0", str(obj.cfg.prim_path).replace("{ENV_REGEX_NS}", "/World/envs/env_0"))
            prim = stage.GetPrimAtPath(path)
            if not prim or not prim.IsValid():
                raise KeyError(f"no USD prim at {path} for object {name!r}")
            cache = UsdGeom.XformCache(Usd.TimeCode.Default())
            groups: dict[str, list] = {"visual": [], "collision": []}
            for q in Usd.PrimRange(prim):
                if not q.IsA(UsdGeom.Mesh):
                    continue
                arr = UsdGeom.Mesh(q).GetPointsAttr().Get()
                if not arr:
                    continue
                M = np.array(cache.ComputeRelativeTransform(q, prim)[0]).reshape(4, 4)        # mesh -> object frame (row-vector convention)
                a = np.array([[v[0], v[1], v[2], 1.0] for v in arr], dtype=np.float64) @ M
                groups["collision" if "collision" in str(q.GetPath()).lower() else "visual"].append(a[:, :3])
            pts_l = groups["visual"] or groups["collision"]
            pts = np.concatenate(pts_l) if pts_l else np.zeros((0, 3))
            try:
                sc = usd_utils.get_scale(prim); pts = pts * np.array([sc[0], sc[1], sc[2]], dtype=np.float64)
            except Exception:  # noqa: BLE001
                pass
            if len(pts) > max_points:
                pts = pts[np.linspace(0, len(pts) - 1, max_points).astype(int)]
            self._pts_cache[name] = pts
        p, q = self.object_pose(name)
        return (quat_to_mat(q) @ self._pts_cache[name].T).T + p

    def robot_link_points(self, body: str, max_points: int = 3000, collision: bool = False) -> np.ndarray:
        """Surface points (N, 3, env-local) of the visual meshes under the robot link prim named `body`, at the link's current
        pose (debug/measurement helper: where are the finger pads really?)."""
        import re
        import omni.usd
        from pxr import Usd, UsdGeom, UsdPhysics
        if not hasattr(self, "_link_pts_cache"):
            self._link_pts_cache = {}
        key = (body, collision)
        if key not in self._link_pts_cache:
            stage = omni.usd.get_context().get_stage()
            root_path = re.sub(r"env_\.\*", "env_0", str(self.robot.cfg.prim_path).replace("{ENV_REGEX_NS}", "/World/envs/env_0"))
            root = stage.GetPrimAtPath(root_path)
            link_prim = None
            for q in Usd.PrimRange(root):
                if q.GetName() == body:
                    link_prim = q; break
            if link_prim is None:
                raise KeyError(f"no prim named {body!r} under {root_path}")
            cache = UsdGeom.XformCache(Usd.TimeCode.Default()); pts = []
            for q in Usd.PrimRange(link_prim):
                is_col = "collision" in str(q.GetPath()).lower() or q.HasAPI(UsdPhysics.CollisionAPI) if hasattr(q, "HasAPI") else False
                if q.IsA(UsdGeom.Mesh) and (is_col == collision):
                    arr = UsdGeom.Mesh(q).GetPointsAttr().Get()
                    if arr:
                        M = np.array(cache.ComputeRelativeTransform(q, link_prim)[0]).reshape(4, 4)
                        pts.append((np.array([[v[0], v[1], v[2], 1.0] for v in arr]) @ M)[:, :3])
            pts = np.concatenate(pts) if pts else np.zeros((0, 3))
            if len(pts) > max_points:
                pts = pts[np.linspace(0, len(pts) - 1, max_points).astype(int)]
            self._link_pts_cache[key] = pts
        p, q = self.body_pose(body)
        return (quat_to_mat(q) @ self._link_pts_cache[key].T).T + p

    def robot_mesh_inventory(self, filter_substr: str = "Gripper") -> list[tuple[str, int, bool]]:
        """(prim path relative to the robot, point count, has CollisionAPI) of every mesh prim whose path contains `filter_substr`."""
        import re
        import omni.usd
        from pxr import Usd, UsdGeom, UsdPhysics
        stage = omni.usd.get_context().get_stage()
        root_path = re.sub(r"env_\.\*", "env_0", str(self.robot.cfg.prim_path).replace("{ENV_REGEX_NS}", "/World/envs/env_0"))
        out = []
        for q in Usd.PrimRange(stage.GetPrimAtPath(root_path)):
            if q.IsA(UsdGeom.Mesh) and filter_substr in str(q.GetPath()):
                arr = UsdGeom.Mesh(q).GetPointsAttr().Get()
                out.append((str(q.GetPath())[len(root_path):], len(arr) if arr else 0, q.HasAPI(UsdPhysics.CollisionAPI)))
        return out

    def joint_positions(self) -> np.ndarray:
        """The 7 arm joint positions (rad, panda_joint1..7)."""
        return self.robot.data.joint_pos[0, self.arm_ids].detach().cpu().numpy().astype(np.float64)

    def gripper_angle(self) -> float:
        """Robotiq finger_joint angle (rad): 0 = fully open .. ~0.785 = fully closed."""
        return float(self.robot.data.joint_pos[0, self.finger_id].item())

    def eef_frame_pose(self) -> tuple[np.ndarray, np.ndarray]:
        """(position(3), quaternion wxyz(4)) of RoboLab's `eef_frame` (= the gripper flange, Robotiq base_link) in the env-local frame."""
        p, q = self.world.get_frame_pose("eef_frame", env_id=0)
        p = p.detach().cpu().numpy().astype(np.float64) - self.env.scene.env_origins[0].detach().cpu().numpy()
        return p, q.detach().cpu().numpy().astype(np.float64)

    def _finger_positions(self) -> tuple[np.ndarray, np.ndarray] | None:
        """World positions of the two inner fingers: link origins if they carry geometry, else the links' centres of mass
        (the flattened Franka+Robotiq USD authors every gripper link at the flange origin)."""
        origin = self.env.scene.env_origins[0].detach().cpu().numpy().astype(np.float64)
        li, ri = int(self.robot.find_bodies("left_inner_finger")[0][0]), int(self.robot.find_bodies("right_inner_finger")[0][0])
        cands = []
        l, _ = self.body_pose("left_inner_finger"); r, _ = self.body_pose("right_inner_finger"); cands.append((l, r, "origins"))
        if hasattr(self.robot.data, "body_com_pos_w"):
            com = _tt(self.robot.data.body_com_pos_w)[0].detach().cpu().numpy().astype(np.float64)
            cands.append((com[li] - origin, com[ri] - origin, "centres of mass"))
        for l, r, how in cands:
            if np.linalg.norm(r - l) > 0.01:
                _log(f"finger positions from link {how}: separation {np.linalg.norm(r - l):.3f} m")
                return l, r
        return None

    def _tool_setup(self) -> None:
        """Tool frame = eef_frame translated TCP_DISTANCE along the eef frame's local +z (RoboLab's eef_frame is the flange
        frame whose +z points from the flange to the fingertips: at the Franka reset pose it points straight down)."""
        ep, eq = self.eef_frame_pose()
        approach_world = quat_to_mat(eq)[:, 2]
        if approach_world[2] > -0.9:
            _log(f"WARNING: eef_frame +z does not point down at the reset pose ({np.round(approach_world, 3).tolist()}); tool offset may be wrong")
        self._tcp_local = np.array([0.0, 0.0, TCP_DISTANCE])
        fp = self._finger_positions()
        if fp is not None:
            d_local = quat_to_mat(eq).T @ ((fp[0] + fp[1]) / 2 - ep)
            _log(f"tool frame: fingers at {np.round(d_local, 4).tolist()} in the eef frame (TCP offset {self._tcp_local.tolist()})")
        else:
            _log(f"tool frame: TCP offset {self._tcp_local.tolist()} (finger links carry no geometry; closing direction assumed along eef local x)")

    def ee_pose(self) -> tuple[np.ndarray, np.ndarray]:
        """(position(3), quaternion wxyz(4)) of the fingertip-centre tool frame (RoboLab's eef_frame moved TCP_DISTANCE along the
        approach axis), env-local frame. Orientation = eef_frame orientation."""
        if not hasattr(self, "_tcp_local"):
            self._tool_setup()
        p, q = self.eef_frame_pose()
        return p + quat_to_mat(q) @ self._tcp_local, q

    def body_pose(self, body: str) -> tuple[np.ndarray, np.ndarray]:
        idx = int(self.robot.find_bodies(body)[0][0])
        pose = _tt(self.robot.data.body_pose_w)[0, idx] if hasattr(self.robot.data, "body_pose_w") else _tt(self.robot.data.body_state_w)[0, idx, :7]
        pose = pose.detach().cpu().numpy().astype(np.float64)
        return pose[:3] - self.env.scene.env_origins[0].detach().cpu().numpy(), pose[3:7]

    def finger_closing_dir(self) -> np.ndarray:
        """Unit vector (env-local frame) along which the two Robotiq fingertips close (left inner finger -> right inner finger),
        measured from the finger links; falls back to the eef frame's local x axis when the links carry no geometry."""
        fp = self._finger_positions()
        if fp is not None:
            d = fp[1] - fp[0]; return d / float(np.linalg.norm(d))
        _, q = self.eef_frame_pose()
        return quat_to_mat(q)[:, 0]

    def state_summary(self) -> dict:
        """Compact final-state summary for tolerance comparisons: object positions / quaternions and arm joint positions."""
        out = {"joints": [round(float(x), 6) for x in self.joint_positions()], "gripper_angle": round(self.gripper_angle(), 6), "objects": {}}
        for n in self.object_names():
            p, q = self.object_pose(n)
            out["objects"][n] = {"position": [round(float(x), 6) for x in p], "orientation_wxyz": [round(float(x), 6) for x in q]}
        return out

    # ---- measured proprioception (reads only)
    def joint_velocities(self) -> np.ndarray:
        """The 7 arm joint velocities (rad/s, panda_joint1..7)."""
        return _tt(self.robot.data.joint_vel)[0, self.arm_ids].detach().cpu().numpy().astype(np.float64)

    def _need_model(self) -> None:
        if self._model is None:
            raise RuntimeError("the robot model could not be built at startup (see the [rcb] WARNING in the log)")

    def joint_efforts(self) -> np.ndarray:
        """Drive-effort estimate of the 7 arm joints (N m): stiffness * (target - q) + damping * (target velocity - qdot) of
        their PD drives, clipped to the effort limit (a motor-current analogue: it grows when the arm pushes on something)."""
        self._need_model(); d = self.robot.data; ids = self.arm_ids
        g = lambda x: _tt(x)[0, ids].detach().cpu().numpy().astype(np.float64)  # noqa: E731
        e = self._kp * (g(d.joint_pos_target) - g(d.joint_pos)) + self._kd * (g(d.joint_vel_target) - g(d.joint_vel))
        return np.clip(e, -self._effort_lim, self._effort_lim)

    def gripper_opening(self) -> float:
        """Distance (m) between the two Robotiq finger pads along the closing axis, measured on the pad meshes at their current
        pose: ~0.085 fully open, ~0.002 closed on nothing; closed on an object it stays at about the object's width."""
        self._need_model(); d = self._closing_axis()
        return float(max(0.0, float((self._pad_points("right") @ d).min()) - float((self._pad_points("left") @ d).max())))

    def proprio(self) -> dict[str, Any]:
        """Measured proprioception: joint_pos (panda_joint1..7, finger_joint; rad), joint_vel (same joints, rad/s), tcp_pose
        (the fingertip-centre frame: x y z + quaternion wxyz, env-local), gripper_opening (m), joint_effort (7 arm joints, N m,
        see joint_efforts), gripper_cmd (the gripper command in force: 0 open / 1 closed). Reads, never steps."""
        p, q = self.ee_pose()
        return {"joint_pos": [float(x) for x in self.joint_positions()] + [self.gripper_angle()],
                "joint_vel": [float(x) for x in self.joint_velocities()] + [float(_tt(self.robot.data.joint_vel)[0, self.finger_id].item())],
                "tcp_pose": [float(x) for x in p] + [float(x) for x in q], "gripper_opening": self.gripper_opening(),
                "joint_effort": [float(x) for x in self.joint_efforts()], "gripper_cmd": float(self._targets[GRIP_INDEX])}

    # ---- the robot's kinematic model and spec sheet (read once at startup; stateless afterwards)
    def _robot_root_path(self) -> str:
        import re
        return re.sub(r"env_\.\*", "env_0", str(self.robot.cfg.prim_path).replace("{ENV_REGEX_NS}", "/World/envs/env_0"))

    def _kin_setup(self) -> None:
        """Numpy model of the arm from the robot's USD joint frames (panda_link0 -> panda_joint1..7 -> fixed mounts -> the
        Robotiq base_link) + the eef_frame / tcp tool frames measured on it, checked against the simulator's link poses; the
        finger pad meshes and the closing axis for gripper_opening(); the robot spec sheet. Reads the stage, writes nothing."""
        import omni.usd
        from pxr import Usd, UsdGeom, UsdPhysics
        stage = omni.usd.get_context().get_stage()
        root = stage.GetPrimAtPath(self._robot_root_path())
        gq = lambda q: np.array([q.GetReal(), *q.GetImaginary()], dtype=np.float64)  # noqa: E731
        rev, fixed, local0 = {}, {}, {}
        for p in Usd.PrimRange(root):
            if not p.IsA(UsdPhysics.Joint):
                continue
            j = UsdPhysics.Joint(p)
            b0, b1 = j.GetBody0Rel().GetTargets(), j.GetBody1Rel().GetTargets()
            if not b0 or not b1:
                continue
            A = hom(quat_to_mat(gq(j.GetLocalRot0Attr().Get())), list(j.GetLocalPos0Attr().Get()))
            B = hom(quat_to_mat(gq(j.GetLocalRot1Attr().Get())), list(j.GetLocalPos1Attr().Get()))
            local0[p.GetName()] = A[:3, 3].copy()
            if p.IsA(UsdPhysics.RevoluteJoint):
                axis = np.zeros(3); axis["XYZ".index(str(UsdPhysics.RevoluteJoint(p).GetAxisAttr().Get()))] = 1.0
                rev[p.GetName()] = (b0[0].name, b1[0].name, A, axis, np.linalg.inv(B))
            elif p.IsA(UsdPhysics.FixedJoint):
                fixed.setdefault(b0[0].name, []).append((b0[0].name, b1[0].name, A @ np.linalg.inv(B)))
        joints = [(n, *rev[n]) for n in self.arm_names]
        mounts, cur = [], joints[-1][2]
        while len(fixed.get(cur, [])) == 1 and cur != FLANGE_BODY:          # panda_link7 -> panda_link8 -> base_link
            mounts.append(fixed[cur][0]); cur = fixed[cur][0][1]
        if cur != FLANGE_BODY:
            raise RuntimeError(f"kinematic model: no fixed chain from {joints[-1][2]} to {FLANGE_BODY} (ended at {cur})")
        T_b = hom(quat_to_mat(self.body_pose(FLANGE_BODY)[1]), self.body_pose(FLANGE_BODY)[0])
        ep, eq = self.eef_frame_pose()
        M_eef = np.linalg.inv(T_b) @ hom(quat_to_mat(eq), ep)                   # flange -> eef_frame (measured)
        M_tcp = hom(None, self._tcp_local)                                       # eef_frame -> tcp
        d = self.robot.data
        arr = lambda x: _tt(x)[0].detach().cpu().numpy().astype(np.float64)  # noqa: E731
        lim, vel, eff, kp, kd, home = (arr(x) for x in (d.joint_pos_limits, d.joint_vel_limits, d.joint_effort_limits,
                                                         d.joint_stiffness, d.joint_damping, d.default_joint_pos))
        ids = list(self.arm_ids)
        self._kp, self._kd, self._effort_lim = kp[ids], kd[ids], eff[ids]
        bp, bq = self.body_pose(joints[0][1])
        self._model = ArmModel(joints[0][1], hom(quat_to_mat(bq), bp), [(n, pa, ch, A, ax, Bi) for n, pa, ch, A, ax, Bi in joints],
                               mounts + [(FLANGE_BODY, EEF_FRAME, M_eef), (EEF_FRAME, TCP_FRAME, M_tcp)], lim[ids, 0], lim[ids, 1], home[ids])
        # check the model against the simulator now
        T = self._model.fk(self.joint_positions()); ep_max = er_max = 0.0
        for name in self._model.links:
            if name in self.robot.body_names:
                p, q = self.body_pose(name)
                ep_max = max(ep_max, float(np.linalg.norm(T[name][:3, 3] - p))); er_max = max(er_max, rot_angle(T[name][:3, :3], quat_to_mat(q)))
        tp, tq = self.ee_pose()
        self.kinematics_check = {"links_max_pos_err_m": ep_max, "links_max_rot_err_rad": er_max,
                                 "tcp_pos_err_m": float(np.linalg.norm(T[TCP_FRAME][:3, 3] - tp)), "tcp_rot_err_rad": rot_angle(T[TCP_FRAME][:3, :3], quat_to_mat(tq))}
        _log("kinematic model vs simulator: links {:.4f} mm / {:.4f} deg, tcp {:.4f} mm".format(ep_max * 1e3, math.degrees(er_max), self.kinematics_check["tcp_pos_err_m"] * 1e3))
        if ep_max > 1e-3 or er_max > 1e-2:
            _log(f"WARNING: the kinematic model disagrees with the simulator: {self.kinematics_check}")
        # finger pads (their mesh points in the finger link frames) and the closing axis (left -> right knuckle, flange frame)
        cache = UsdGeom.XformCache(Usd.TimeCode.Default()); self._pads = {}
        for side in ("left", "right"):
            link = next((q for q in Usd.PrimRange(root) if q.GetName() == f"{side}_inner_finger"), None)
            meshes = [q for q in Usd.PrimRange(link) if q.IsA(UsdGeom.Mesh)] if link else []
            pads = [q for q in meshes if "fingertip" in q.GetName().lower()] or meshes
            pts = [np.array([[v[0], v[1], v[2], 1.0] for v in UsdGeom.Mesh(q).GetPointsAttr().Get()]) @ np.array(cache.ComputeRelativeTransform(q, link)[0])
                   for q in pads if UsdGeom.Mesh(q).GetPointsAttr().Get()]
            self._pads[side] = (f"{side}_inner_finger", np.concatenate(pts)[:, :3] if pts else np.zeros((1, 3)))
        ax = local0.get("right_outer_knuckle_joint", np.array([0.0, -1.0, 0.0])) - local0.get("finger_joint", np.array([0.0, 1.0, 0.0]))
        self._closing_local = ax / np.linalg.norm(ax)
        _log(f"gripper opening now {self.gripper_opening() * 1000:.1f} mm (finger_joint {self.gripper_angle():.3f} rad)")
        self._build_specs(lim, vel, eff, kp, kd, home, M_eef, M_tcp)

    def _pad_points(self, side: str) -> np.ndarray:
        link, pts = self._pads[side]
        p, q = self.body_pose(link)
        return pts @ quat_to_mat(q).T + p

    def _closing_axis(self) -> np.ndarray:
        return quat_to_mat(self.body_pose(FLANGE_BODY)[1]) @ self._closing_local

    def _build_specs(self, lim, vel, eff, kp, kd, home, M_eef, M_tcp) -> None:
        ids = list(self.arm_ids) + [self.finger_id]; names = list(self.arm_names) + ["finger_joint"]
        r6 = lambda x: round(float(x), 6)  # noqa: E731
        joints = [{"name": n, "type": "revolute", "unit": "rad", "position_limits": [r6(lim[i, 0]), r6(lim[i, 1])],
                   "velocity_limit": r6(vel[i]), "effort_limit": r6(eff[i]), "group": "gripper" if n == "finger_joint" else "arm"}
                  for n, i in zip(names, ids)]
        for j in joints:
            if j["name"] in PANDA_RATED:
                j.update(rated_velocity=PANDA_RATED[j["name"]][0], rated_effort=PANDA_RATED[j["name"]][1], rated_source="Franka Emika Panda datasheet")
        joints[-1]["note"] = ("the Robotiq's driven knuckle (0 = open .. pi/4 = closed by the command); the other finger joints "
                              "follow it (mimic joints) and are not listed")
        self._robot_spec = {
            "name": self.spec["robot"],
            "description": "Franka Emika Panda arm (7 revolute joints, fixed base) with a Robotiq 2F-85 parallel gripper: NVIDIA "
                           "RoboLab's DROID setup (Isaac Lab 2.3 / Isaac Sim 5.1)",
            "base": {"type": "fixed", "link": self._model.root, "pose": pose7(self._model.base_T)},
            "joints": joints,
            "grippers": {"robotiq_2f85": {
                "joints": ["finger_joint"], "opening_m": list(GRIPPER_OPENING_M),
                "command": {"index": GRIP_INDEX, "range": [0.0, 1.0], "rule": "> 0.5 closes (finger_joint target pi/4 rad), otherwise "
                            "opens (target 0)", "switch": "binary: switched at the row it is given in, never interpolated"},
                "tcp_frame": TCP_FRAME}},
            "controller": {
                "type": "joint-position PD: PhysX implicit joint drives tracking absolute targets that are held for each control step",
                "control_hz": round(1.0 / self.control_dt, 6), "physics_hz": round(1.0 / float(self.env_cfg.sim.dt), 6),
                "gains": {n: {"stiffness": r6(kp[i]), "damping": r6(kd[i])} for n, i in zip(names, ids)},
                "note": "effort = stiffness * (target - q) + damping * (0 - qdot), clipped to effort_limit; stiffness N m/rad, damping "
                        "N m s/rad. position_limits / velocity_limit / effort_limit are what the simulator enforces (velocity: the "
                        "robot USD's 10 rad/s; RoboLab's configured 2.175 / 2.61 rad/s are not applied by Isaac Lab's implicit "
                        "drives); rated_velocity / rated_effort are the Panda datasheet's"},
            "tcp": {TCP_FRAME: {"parent_link": FLANGE_BODY, "link_T_frame": (M_eef @ M_tcp).tolist(),
                                "definition": f"the fingertip centre: {EEF_FRAME} moved {TCP_DISTANCE} m along its +z (approach) axis "
                                              "to the ends of the closed fingertips; the ee_pose action, ee_pose() and the proprio "
                                              "tcp_pose use it"},
                    EEF_FRAME: {"parent_link": FLANGE_BODY, "link_T_frame": M_eef.tolist(),
                                "definition": "RoboLab's eef_frame: the Robotiq 2F-85 base (the gripper flange, on panda_link8) with "
                                              "its axes rotated so that +z points from the flange to the fingertips"}}}
        self._kin_spec = {
            "endpoint": "/kinematics", "joint_names": list(self.arm_names), "frame": "world", "quaternion_order": "wxyz",
            "links": list(self._model.links), "tcp_frames": [TCP_FRAME], "ee_frames": [TCP_FRAME], "ik_targets": [TCP_FRAME, EEF_FRAME, FLANGE_BODY],
            "ik": {"solver": "damped least squares on the model's Jacobian from the seed (then the home pose, then mid-range); "
                             "every step is clamped to the joint limits", "joints": list(self.arm_names), "tol_pos_m": 0.001,
                   "tol_rot_rad": 0.01, "max_iters": 300, "default_seed": [r6(x) for x in home[list(self.arm_ids)]],
                   "collision_checking": "none"},
            "stateless": True,
            "note": "a numpy model of the chain read from the robot's USD joint frames at startup; checked against the simulator's "
                    "link poses then (max error {:.1e} m). world = the env-local frame. The ee_pose action itself runs Isaac Lab's "
                    "differential IK on the simulator (closed loop, one update per control step)".format(self.kinematics_check["links_max_pos_err_m"])}

    def robot_spec(self) -> dict:
        """The robot's spec sheet (the /spec "robot_spec" of the standard mode): joints with the simulator's limits, the gripper and
        its command, the controller and its gains, the tool frames. Nothing about the scene."""
        self._need_model(); return json.loads(json.dumps(self._robot_spec))

    def kinematics_spec(self) -> dict:
        """What kinematics() answers (the /spec "kinematics"): joint order, frames, IK defaults."""
        self._need_model(); return json.loads(json.dumps(self._kin_spec))

    def kinematics(self, req: dict) -> dict:
        """Stateless FK / IK on the numpy model (never reads or changes the simulator; the answer depends only on the request):
          {"op": "fk", "q": [7], "links": [...]?}  -> {"ok": True, "op": "fk", "frame": "world", "poses": {link: [x,y,z, qw,qx,qy,qz]}}
          {"op": "ik", "targets": {frame: [x,y,z, qw,qx,qy,qz]}, "seed": [7]?, "tol_pos_m"?, "tol_rot_rad"?, "max_iters"?}
            -> {"ok": bool, "op": "ik", "frame": "world", "q": [7] (the best found, within the joint limits), "error": {frame: {"pos_m", "rot_rad"}}}
        Frames: kinematics_spec()["links"]; IK targets: kinematics_spec()["ik_targets"]. Raises ValueError on a malformed request."""
        self._need_model(); ks = self._kin_spec; n = len(ks["joint_names"])
        if not isinstance(req, dict):
            raise ValueError("the request must be a dict")
        if req.get("base_pose") is not None:
            raise ValueError("base_pose is only accepted by a mobile robot (this arm has a fixed base; kinematics frame 'world')")

        def vec(x, what):
            a = None if x is None else np.asarray(x, dtype=np.float64).reshape(-1)
            if a is None or a.size != n or not np.all(np.isfinite(a)):
                raise ValueError(f"{what} must be {n} finite numbers")
            return a

        def tpose(x, what):
            a = None if x is None else np.asarray(x, dtype=np.float64).reshape(-1)
            if a is None or a.size != 7 or not np.all(np.isfinite(a)) or np.linalg.norm(a[3:]) < 1e-6:
                raise ValueError(f"{what} must be [x, y, z, qw, qx, qy, qz] with a non-zero quaternion")
            return pose7_to_T(a)
        if req.get("op") == "fk":
            links = req.get("links") or ks["links"]
            if not isinstance(links, (list, tuple)) or any(k not in ks["links"] for k in links):
                raise ValueError(f"links must be names from {ks['links']}")
            T = self._model.fk(vec(req.get("q"), "q"))
            return {"ok": True, "op": "fk", "frame": ks["frame"], "poses": {k: pose7(T[k]) for k in links}}
        if req.get("op") == "ik":
            tg = req.get("targets")
            if not isinstance(tg, dict) or not tg or any(k not in ks["ik_targets"] for k in tg):
                raise ValueError(f"targets must map frames from {ks['ik_targets']} to poses")
            tol_p = float(req.get("tol_pos_m") or ks["ik"]["tol_pos_m"]); tol_r = float(req.get("tol_rot_rad") or ks["ik"]["tol_rot_rad"])
            it = int(req.get("max_iters") or ks["ik"]["max_iters"])
            if not (1e-5 <= tol_p <= 0.5 and 1e-4 <= tol_r <= 3.2 and 1 <= it <= 5000):
                raise ValueError("tol_pos_m in [1e-5, 0.5], tol_rot_rad in [1e-4, 3.2], max_iters in [1, 5000]")
            seed = None if req.get("seed") is None else vec(req["seed"], "seed")
            q, ok, errs = self._model.ik({k: tpose(v, f"targets[{k}]") for k, v in tg.items()}, seed=seed, tol_p=tol_p, tol_r=tol_r, max_iters=it)
            return {"ok": bool(ok), "op": "ik", "frame": ks["frame"], "q": [float(v) for v in q],
                    "error": {k: {"pos_m": float(e[0]), "rot_rad": float(e[1])} for k, e in errs.items()}}
        raise ValueError("op must be 'fk' or 'ik'")

    # ---- differential IK (Isaac Lab's DLS controller on the PhysX Jacobian; closed loop, one update per control step)
    def _ik_setup(self) -> None:
        from isaaclab.controllers import DifferentialIKController, DifferentialIKControllerCfg
        cfg = DifferentialIKControllerCfg(command_type="pose", use_relative_mode=False, ik_method="dls")
        self._ik = DifferentialIKController(cfg, num_envs=1, device=self.device)
        names = list(self.robot.body_names)
        body = "base_link" if "base_link" in names else ("panda_link8" if "panda_link8" in names else "panda_hand")
        self._ik_body = names.index(body)
        # the eef_frame (fingertip centre) is rigidly attached to that body: measure the constant offset once
        bp, bq = self.body_pose(body); ep, eq = self.ee_pose()
        self._ik_offset = pose_compose(*pose_inverse(bp, bq), ep, eq)   # body -> eef
        self._ik_jac_idx = self._ik_body - 1 if self.robot.is_fixed_base else self._ik_body
        _log(f"IK on body {body!r} (index {self._ik_body}, fixed_base={self.robot.is_fixed_base}); eef offset {np.round(self._ik_offset[0], 4).tolist()}")

    def ik_step(self, pos, quat_wxyz) -> np.ndarray:
        """One differential-IK update towards eef_frame pose (pos, quat) in the env-local frame -> 7 joint targets (rad)."""
        if self._ik is None:
            self._ik_setup()
        from isaaclab.utils.math import subtract_frame_transforms
        th = self.th
        # eef target -> tracked-body target
        off_p, off_q = pose_inverse(*self._ik_offset)
        bp, bq = pose_compose(np.asarray(pos, dtype=np.float64), np.asarray(quat_wxyz, dtype=np.float64), off_p, off_q)
        jac = _tt(self.robot.root_physx_view.get_jacobians())[:, self._ik_jac_idx, :, self.arm_ids]
        body = _tt(self.robot.data.body_pose_w)[:, self._ik_body] if hasattr(self.robot.data, "body_pose_w") else _tt(self.robot.data.body_state_w)[:, self._ik_body, :7]
        root = _tt(self.robot.data.root_pose_w) if hasattr(self.robot.data, "root_pose_w") else _tt(self.robot.data.root_state_w)[:, :7]
        ee_pos_b, ee_quat_b = subtract_frame_transforms(root[:, :3], root[:, 3:7], body[:, :3], body[:, 3:7])
        tgt_w = th.as_tensor(np.concatenate([bp + self.env.scene.env_origins[0].detach().cpu().numpy(), bq]), dtype=th.float32, device=self.device).unsqueeze(0)
        tgt_pos_b, tgt_quat_b = subtract_frame_transforms(root[:, :3], root[:, 3:7], tgt_w[:, :3], tgt_w[:, 3:7])
        q = self.robot.data.joint_pos[:, self.arm_ids]
        self._ik.set_command(th.cat([tgt_pos_b, tgt_quat_b], dim=-1))
        q_des = self._ik.compute(ee_pos_b, ee_quat_b, jac, q)
        lo = self.robot.data.soft_joint_pos_limits[0, self.arm_ids, 0]; hi = self.robot.data.soft_joint_pos_limits[0, self.arm_ids, 1]
        return th.clamp(q_des[0], lo, hi).detach().cpu().numpy().astype(np.float64)

    # ---- primitives for the agent: deliberately thin wrappers of the low-level action (joint targets, gripper command,
    # differential-IK moves). Grasping, placing and every other skill are the agent's to build.
    def primitives(self) -> dict[str, Callable]:
        s = self

        def get_object_pose(name: str):
            """-> (position(3), quaternion wxyz(4)) of `name` (env-local frame)."""
            return s.object_pose(name)

        def get_object_bounds(name: str):
            """-> AABB [[xmin,ymin,zmin],[xmax,ymax,zmax]] of `name` (env-local frame)."""
            return s.object_bounds(name)

        def get_ee_pose():
            """-> (position(3), quaternion wxyz(4)) of the fingertip-centre frame (eef_frame)."""
            return s.ee_pose()

        def get_joint_targets():
            """-> the currently commanded action (7 joint targets + gripper command)."""
            return s.hold_action()

        def hold(steps: int = 10):
            """Keep the current targets for `steps` control steps (lets objects settle). No-op once the episode is over."""
            if s.episode_done:
                return
            for _ in range(int(steps)):
                if s.step(s.hold_action()):
                    break

        def set_joint_targets(targets, steps: int = 1):
            """Command a full 8-vector (7 joint targets + gripper command) for `steps` control steps (no interpolation)."""
            if s.episode_done:
                return
            for _ in range(int(steps)):
                if s.step(targets):
                    break

        def set_gripper(close: bool | float, steps: int = 15):
            """Command the Robotiq gripper (True/1 = close, False/0 = open) and hold for `steps` control steps (~1 s)."""
            if s.episode_done:
                return
            t = s.hold_action(); t[GRIP_INDEX] = GRIPPER_CLOSE if float(close) > 0.5 else GRIPPER_OPEN
            for _ in range(int(steps)):
                if s.step(t):
                    break

        def open_gripper(steps: int = 15):
            """Open the gripper fully."""
            set_gripper(False, steps)

        def close_gripper(steps: int = 15):
            """Close the gripper (the binary action squeezes whatever is between the fingers)."""
            set_gripper(True, steps)

        def move_joints(q7, *, max_dq: float = 0.05, steps: int | None = None, settle: int = 0):
            """Interpolate the 7 joint targets linearly from the current targets to `q7` (rad), at most `max_dq` rad per
            control step (or exactly `steps` steps), then hold `settle` steps."""
            if s.episode_done:
                return
            cur = s.hold_action(); goal = cur.copy(); goal[ARM_SLICE] = np.asarray(q7, dtype=np.float64)
            n = int(steps) if steps else max(2, int(math.ceil(float(np.max(np.abs(goal - cur))) / max_dq)))
            for i in range(1, n + 1):
                if s.step(cur + (goal - cur) * (i / n)):
                    return
            for _ in range(int(settle)):
                if s.step(goal):
                    return

        def move_ee(pos, quat_wxyz=None, *, speed: float = 0.25, max_dq: float = 0.08, tol: float = 0.006, rot_tol: float = 0.06,
                    max_steps: int = 240, settle: int = 0):
            """Move the fingertip-centre frame to env-local pose (pos, quat_wxyz; default: keep the current orientation) along
            a straight line at `speed` m/s: every control step one differential-IK update towards the moving waypoint
            (joint change clamped to `max_dq` rad/step), until the pose is within `tol` m / `rot_tol` rad, then hold
            `settle` steps. Raises PrimitiveError if `max_steps` pass without converging. Returns the final position error (m)."""
            if s.episode_done:
                return None
            p1 = np.asarray(pos, dtype=np.float64)
            p0, q0 = s.ee_pose()
            q1 = np.asarray(quat_wxyz if quat_wxyz is not None else q0, dtype=np.float64)
            dist = float(np.linalg.norm(p1 - p0))
            n_way = max(1, int(math.ceil(dist / (speed * s.control_dt))))
            best = None
            for i in range(int(max_steps)):
                wp = p1 if i >= n_way else p0 + (p1 - p0) * ((i + 1) / n_way)
                q_des = s.ik_step(wp, q1)
                cur = s.hold_action(); dq = np.clip(q_des - cur[ARM_SLICE], -max_dq, max_dq)
                a = cur.copy(); a[ARM_SLICE] = cur[ARM_SLICE] + dq
                if s.step(a):
                    break
                pe, qe = s.ee_pose()
                err = float(np.linalg.norm(pe - p1)); rerr = quat_angle(qe, q1)
                best = err if best is None else min(best, err)
                if i >= n_way and err < tol and rerr < rot_tol:
                    for _ in range(int(settle)):
                        if s.step(s.hold_action()):
                            break
                    return err
            if s.episode_done:
                return None
            pe, qe = s.ee_pose()
            raise PrimitiveError(f"move_ee to {np.round(p1, 3).tolist()} did not converge in {max_steps} steps "
                                 f"(pos err {np.linalg.norm(pe - p1) * 1000:.1f} mm, rot err {math.degrees(quat_angle(qe, q1)):.1f} deg)")

        def top_down_quat(yaw: float = 0.0):
            """Fingertip-frame orientation (wxyz) for a vertical, top-down approach, rotated by `yaw` (rad) about the world z
            axis relative to the robot's reset-pose gripper orientation (at yaw 0 the fingers close along
            `get_finger_closing_dir()`, measured at the reset pose)."""
            return quat_mul(quat_from_axis_angle([0, 0, 1], yaw), s.reset_ee_quat)

        def get_finger_closing_dir():
            """-> unit vector (env-local) along which the fingers currently close (left fingertip -> right fingertip)."""
            return s.finger_closing_dir()

        def yaw_for_closing_dir(direction_xy):
            """-> the `yaw` for top_down_quat()/grasp() that makes the fingers close along the horizontal direction
            `direction_xy` (closing is symmetric, so the result is in (-pi/2, pi/2])."""
            d = np.asarray(direction_xy, dtype=np.float64)[:2]
            want = math.atan2(d[1], d[0]); have = math.atan2(s.reset_closing_dir[1], s.reset_closing_dir[0])
            yaw = wrap_angle(want - have)
            if yaw > math.pi / 2:
                yaw -= math.pi
            if yaw <= -math.pi / 2:
                yaw += math.pi
            return yaw

        def get_object_points(name: str):
            """-> (N, 3) surface points of `name`'s visual mesh in the env-local frame (current pose applied)."""
            return s.object_points(name)

        return {"get_object_pose": get_object_pose, "get_object_bounds": get_object_bounds, "get_ee_pose": get_ee_pose,
                "get_joint_targets": get_joint_targets, "hold": hold, "set_joint_targets": set_joint_targets,
                "set_gripper": set_gripper, "open_gripper": open_gripper, "close_gripper": close_gripper, "move_joints": move_joints,
                "move_ee": move_ee, "ik_step": s.ik_step, "top_down_quat": top_down_quat, "get_finger_closing_dir": get_finger_closing_dir,
                "yaw_for_closing_dir": yaw_for_closing_dir, "get_object_points": get_object_points}

    @property
    def reset_ee_quat(self) -> np.ndarray:
        """Fingertip-frame orientation at the robot's reset pose (pointing straight down; the reference for top_down_quat)."""
        return self._reset_ee_quat

    def exec_code(self, code: str, extra: dict | None = None) -> dict[str, Any]:
        """Run agent/oracle code with the primitives in scope (also: session, objects, TASK, np, math, PrimitiveError)."""
        g: dict[str, Any] = {"__name__": "__main__", "np": np, "math": math, "session": self, "objects": self.objects,
                             "TASK": dict(self.spec, table_top_z=self._table_top, instruction=self.instruction),
                             "PrimitiveError": PrimitiveError, "quat_to_mat": quat_to_mat, "mat_to_quat": mat_to_quat, "quat_mul": quat_mul,
                             "quat_inv": quat_inv, "quat_from_axis_angle": quat_from_axis_angle, "wrap_angle": wrap_angle,
                             **self.primitives(), **(extra or {})}
        try:
            exec(code, g, g)
            return {"ok": True}
        except BaseException as exc:  # noqa: BLE001
            import traceback
            traceback.print_exc(file=sys.stderr)
            return {"ok": False, "error": repr(exc)[:300]}

    def _log_end(self) -> None:
        if not self._end_logged:           # Isaac's app.close() can end the process before atexit handlers run
            self._end_logged = True
            _slog("session_end", task=self.task, resets=self._resets, sim_steps=self._total_steps + self.n_steps)

    def close(self) -> None:
        self._log_end()
        try:
            self.env.close()
        except Exception as exc:  # noqa: BLE001
            _log("env.close:", repr(exc)[:120])
        try:
            if _APP is not None:
                _APP.close()
        except Exception as exc:  # noqa: BLE001
            _log("app.close:", repr(exc)[:120])


# --------------------------------------------------------------------------- CLI
def _load_traj(path: str) -> dict[str, Any]:
    d = np.load(path, allow_pickle=False)
    return {k: (d[k].item() if d[k].shape == () else d[k]) for k in d.files}


def _versions() -> dict:
    out = {}
    for mod in ("robolab", "isaaclab", "isaacsim", "torch"):
        try:
            m = __import__(mod); out[mod] = str(getattr(m, "__version__", ""))
        except Exception:  # noqa: BLE001
            pass
    try:
        out["robolab_commit"] = subprocess.run(["git", "-C", str(ROBOLAB_ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10).stdout.strip()[:12]
    except Exception:  # noqa: BLE001
        pass
    return out


def cmd_make_instance(a) -> None:
    s = Session(a.task, seed=a.seed, depth=False)
    out = {"task": a.task, "robolab_task": s.spec["robolab_task"], "env_name": s.env_name, "seed": s.seed, "instruction": s.instruction,
           "text": s.spec["text"], "initial_state": s.initial_state, "state_sha": s.instance_sha, "action_dim": ACTION_DIM,
           "control_hz": round(1 / s.control_dt, 3), "sim_dt": float(s.env_cfg.sim.dt), "decimation": int(s.env_cfg.decimation), "physics": s.physics,
           "robot_joint_positions": [round(float(x), 6) for x in s.joint_positions()], "arm_joint_names": list(s.arm_names),
           "objects": s.objects(), "table_top_z": s._table_top, "versions": _versions()}
    Path(a.out).write_text(json.dumps(out, indent=1))
    print(json.dumps({"instance": a.out, "state_sha": s.instance_sha, "objects": list(out["objects"])}), flush=True)
    s.close()


def cmd_run_oracle(a) -> None:
    """Run the reference code on the frozen instance in this fresh process and record every low-level action."""
    s = Session(a.task, instance=a.instance, strict=True, depth=False)
    code = open(a.code).read()
    t0 = time.time()
    s.record_start()
    r = s.exec_code(code)
    acts = s.record_stop()
    st = s.status()
    s.save_trajectory(acts, a.out, meta={"source": "oracle", "exec": r, "wall_s": round(time.time() - t0, 1)})
    print(json.dumps({"traj": a.out, "n_actions": int(len(acts)), "exec": r, **st, "wall_s": round(time.time() - t0, 1)}), flush=True)
    s.close()


def cmd_replay(a) -> None:
    traj = _load_traj(a.traj)
    if str(traj.get("task")) != a.task:
        print(json.dumps({"error": f"trajectory task {traj.get('task')} != {a.task}"}), flush=True); sys.exit(2)
    s = Session(a.task, instance=a.instance, strict=a.strict, depth=False)   # replays render no depth (faster; same physics)
    acts = np.asarray(traj["actions"], dtype=np.float32)
    t0 = time.time()
    outs = []
    for i in range(a.repeat):
        if a.video and i == 0:
            s.start_video(a.video, fps=a.fps)   # the video shows the first (fresh-process-exact) replay
        outs.append(s.replay(acts))
        if a.video and i == 0:
            s.stop_video()
    out = {"n_actions": int(len(acts)), "instance_sha": s.instance_sha, "instance_matches": s.instance_matches,
           "instance_exact": s.instance_exact, "replays": outs, "all_success": all(o["success"] for o in outs),
           "deterministic": len({o["state_sha"] for o in outs}) == 1, "wall_s": round(time.time() - t0, 1), "video": a.video}
    print(json.dumps(out), flush=True)
    s.close()


def cmd_render(a) -> None:
    s = Session(a.task, instance=a.instance, depth=False)
    cams = tuple(a.cameras.split(",")) if a.cameras else Session.VIDEO_CAMERAS
    print(json.dumps(s.render_video(_load_traj(a.traj)["actions"], a.out, every=a.every, fps=a.fps, cameras=cams, cols=a.cols)), flush=True)
    s.close()


def cmd_selftest(a) -> None:
    """Determinism evidence in 4 fresh processes: make-instance, run-oracle, replay, replay (fresh == fresh == live)."""
    here, out = Path(__file__).resolve(), Path(a.out_dir); out.mkdir(parents=True, exist_ok=True)
    inst, traj = out / "instance.json", out / "trajectory.npz"

    def run(*args):
        cmd = [sys.executable, str(here), *map(str, args)]
        _log("selftest>", " ".join(cmd[2:]))
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=open(out / "selftest.stderr.log", "ab"), text=True)
        lines = [l for l in p.stdout.splitlines() if l.startswith("{")]
        return json.loads(lines[-1]) if lines else {"error": f"no json output (rc={p.returncode})"}

    r0 = run("make-instance", "--task", a.task, "--seed", a.seed, "--out", inst)
    r1 = run("run-oracle", "--task", a.task, "--instance", inst, "--code", a.code, "--out", traj)
    r2 = run("replay", "--task", a.task, "--instance", inst, "--traj", traj, "--strict")
    r3 = run("replay", "--task", a.task, "--instance", inst, "--traj", traj, "--strict")
    sha = [((r.get("replays") or [{}])[0]).get("state_sha") for r in (r2, r3)]
    ok = bool(r1.get("success")) and bool(r2.get("all_success")) and bool(r3.get("all_success")) and sha[0] == sha[1] == r1.get("state_sha") \
        and bool(r2.get("instance_matches")) and bool(r3.get("instance_matches"))
    print(json.dumps({"make_instance": r0, "oracle": r1, "replay_1": r2, "replay_2": r3, "PASS": ok}, indent=1), flush=True)
    sys.exit(0 if ok else 1)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("make-instance"); q.add_argument("--task", required=True); q.add_argument("--seed", type=int, default=DEFAULT_SEED)
    q.add_argument("--out", required=True); q.set_defaults(fn=cmd_make_instance)
    q = sub.add_parser("run-oracle"); q.add_argument("--task", required=True); q.add_argument("--instance", required=True)
    q.add_argument("--code", required=True); q.add_argument("--out", required=True); q.set_defaults(fn=cmd_run_oracle)
    q = sub.add_parser("replay"); q.add_argument("--task", required=True); q.add_argument("--instance", required=True); q.add_argument("--traj", required=True)
    q.add_argument("--repeat", type=int, default=1, help="in-process repeats; only the first is fresh-process exact"); q.add_argument("--video", default=None); q.add_argument("--fps", type=int, default=15)
    q.add_argument("--strict", action="store_true", help="fail if the rebuilt frozen scene does not match instance.json (poses within tolerance)"); q.set_defaults(fn=cmd_replay)
    q = sub.add_parser("render"); q.add_argument("--task", required=True); q.add_argument("--instance", required=True); q.add_argument("--traj", required=True)
    q.add_argument("--out", required=True); q.add_argument("--every", type=int, default=1); q.add_argument("--fps", type=int, default=15)
    q.add_argument("--cameras", default=None); q.add_argument("--cols", type=int, default=3); q.set_defaults(fn=cmd_render)
    q = sub.add_parser("selftest"); q.add_argument("--task", default="banana_in_bowl"); q.add_argument("--seed", type=int, default=DEFAULT_SEED)
    q.add_argument("--code", required=True); q.add_argument("--out-dir", required=True); q.set_defaults(fn=cmd_selftest)
    a = p.parse_args(); a.fn(a)


if __name__ == "__main__":
    main()
