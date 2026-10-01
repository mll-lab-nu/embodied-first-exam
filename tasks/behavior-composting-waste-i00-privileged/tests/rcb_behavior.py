"""
rcb_behavior.py — task-local tooling for BEHAVIOR-1K (OmniGibson 3.9.2, the 2026 BEHAVIOR Challenge version):
frozen challenge instance / thin primitives + privileged state / action recording / fresh-process deterministic replay.
Same shape as the robosuite example's rcb_traj.py so agents and verifiers share one mental model.

Concepts
--------
instance   : a 2026 BEHAVIOR Challenge task instance (task name + instance id, e.g. picking_up_trash / 301) loaded through
             the official evaluator (omnigibson.eval.evaluator.Evaluator): scene template + task-relevant object states +
             robot start pose, settled for 25 physics steps. The frozen initial state is what Evaluator.reset() yields right
             after load_task_instance(); its sha1 over og.sim.dump_state(serialized=True) is stored in instance.json and
             checked whenever the instance is loaded again (dataset / simulator drift => mismatch).
trajectory : the (T, A) low-level robot actions handed to env.step, one row per control step (30 Hz control, 120 Hz
             physics), A = robot.action_dim = 25 with the primitives controller config (base 3, trunk 4, left arm 7,
             left gripper 2, right arm 7, right gripper 2; see robot.controller_action_idx). Replaying them open-loop from
             the frozen instance in a FRESH process reproduces the final state bit-exactly (measured on CPU PhysX).
             In-process reset() is only approximate (~1e-6): the first replay in a process (no reset needed) is exact,
             later ones drift, so the verifier replays in two fresh processes (the `replay` CLI).
budget     : there is no step budget: the agent's wall clock is the limit. The challenge's timeout termination is lifted to
             MAX_STEPS, which only stops runaway trajectories; the episode still ends the moment the BDDL goal holds.

CLI
---
  python rcb_behavior.py make-instance --task picking_up_trash --instance-id 301 --robot-config r1pro_primitives_eval.yaml --out instance.json
  python rcb_behavior.py run-oracle    --task picking_up_trash --instance instance.json --code oracle.py --out traj.npz
  python rcb_behavior.py replay        --task picking_up_trash --instance instance.json --traj traj.npz [--video replay.mp4] [--strict]
  python rcb_behavior.py render        --task picking_up_trash --instance instance.json --traj traj.npz --out replay.mp4
  python rcb_behavior.py selftest      --task picking_up_trash --instance-id 301 --code oracle.py --out-dir /tmp/selftest   # 4 fresh processes

Python (what the agent gets)
----------------------------
  from rcb_behavior import Session
  s = Session("picking_up_trash", instance="/app/instance.json")   # ~3 min: launches Isaac Sim + loads the scene
  s.reset()                          # back to the frozen instance state (approximate in-process; fresh process is exact)
  p = s.primitives()                 # thin wrappers of the low-level action: move_joints, move_base, move_ee, set_gripper, hold
  s.objects()                        # task objects: BDDL name -> category, position
  s.ik({"left": (pos, quat_xyzw)})   # cuRobo IK -> {"trunk": q4, "left": q7}
  s.render_frame("robot_r1:zed_link:Camera:0")   # RGB of a robot camera, 224x224; Session(..., cameras="tiny"): 16x16, cheaper rendering
  s.render_depth("robot_r1:zed_link:Camera:0")   # z-depth (H, W) float32 in metres, 0 = no reading, pixel-aligned with render_frame
  s.camera_info()                    # per camera: intrinsic_cv, extrinsic_cv (world -> camera, OpenCV), cam2world_gl, image_size, mount
  s.robot_spec(); s.robot_state()    # joints with real limits, gripper rule, drive gains, TCP, mobile base; measured q/qd/effort, poses
  s.kinematics({"op": "fk", "q": q}) # stateless FK / IK in the robot base frame (s.kinematics_spec()); the standard mode's /kinematics
  s.record_start(); ...; actions = s.record_stop()   # (T, 25) low-level actions, one row per env step
  s.status()                         # {'success': bool, 'q_score': float, 'sim_steps': int, 'resets': int, 'state_sha': str}
  s.replay(actions)                  # the first replay in a process is exact; the CLI `replay` (fresh process) is the grader's view
  s.save_trajectory(actions, "/app/output/trajectory.npz")
"""
from __future__ import annotations

import os
os.environ.setdefault("OMNIGIBSON_HEADLESS", "1")
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")  # before torch initialises CUDA

import argparse
import hashlib
import json
import math
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np

# Interaction log: every Session (any process) appends one line per session start/reset/record/replay/exit, with the
# control steps consumed, to RCB_SESSION_LOG (default /app/output/rcb_session_log.jsonl, collected with the artifacts).
# It records the agent's whole debugging history, not just the trajectory it hands in (the verifier reports it as
# cost: agent_sessions / agent_resets / agent_sim_steps). Set RCB_SESSION_LOG="" to disable (the verifier does).
# The same line also goes to RCB_SESSION_LOG_KEEP (default /logs/agent/rcb_session_log.jsonl, where that directory
# exists: the agent's log directory). The host's rcb-log-mirror keeps an append-only copy of it, so the record
# survives even if the agent deletes or edits the /app/output copy (user 2026-09-26).
SESSION_LOG = os.environ.get("RCB_SESSION_LOG", "/app/output/rcb_session_log.jsonl")
SESSION_LOG_KEEP = os.environ.get("RCB_SESSION_LOG_KEEP", "/logs/agent/rcb_session_log.jsonl")
MAX_STEPS = 200_000        # no step budget (the wall clock is); this only stops a runaway trajectory (~1.9 h of sim time)


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


# --------------------------------------------------------------------------- task family registry
TASKS: dict[str, dict] = {
    "picking_up_trash": dict(
        challenge_task="picking_up_trash",
        scene="house_double_floor_lower",
        text="Put the three cans of soda from the living room inside the trash can in the kitchen.",
        cans=["can__of__soda.n.01_1", "can__of__soda.n.01_2", "can__of__soda.n.01_3"],
        trash="ashcan.n.01_1",
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    "putting_shoes_on_rack": dict(
        challenge_task="putting_shoes_on_rack",
        scene="house_double_floor_lower",
        text="Put the two pairs of shoes (two gym shoes, two sandals) on the hall tree in the corridor: every shoe must "
             "touch the hall tree and not the floor, and the two shoes of each pair must be next to each other.",
        gym_shoes=["gym_shoe.n.01_1", "gym_shoe.n.01_2"],
        sandals=["sandal.n.01_1", "sandal.n.01_2"],
        rack="hallstand.n.01_1",
        movable=["gym_shoe.n.01_1", "gym_shoe.n.01_2", "sandal.n.01_1", "sandal.n.01_2"],  # picked up: never base obstacles
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    "composting_waste": dict(
        challenge_task="composting_waste",
        scene="Rs_int",
        text="Put the half banana and the half pomegranate, which lie on the kitchen countertop, inside the trash can that stands on the kitchen floor.",
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    "make_rose_centerpieces": dict(
        challenge_task="make_rose_centerpieces",
        scene="house_double_floor_lower",
        text="Make a centerpiece. The vase and three roses lie on the cabinet in the living room; put all three roses into the vase and stand the vase on the living-room coffee table.",
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    "organizing_art_supplies": dict(
        challenge_task="organizing_art_supplies",
        scene="house_double_floor_upper",
        text="In the bedroom, pack the art supplies lying on the desk (a glue stick, a rubber eraser, a paintbrush and a marker) into the carryall, which stands on the floor, and put the carryall on the desk.",
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    "set_up_a_coffee_station_in_your_kitchen": dict(
        challenge_task="set_up_a_coffee_station_in_your_kitchen",
        scene="house_single_floor",
        text="Set up a coffee station on the kitchen countertop. The coffee maker stays on the countertop; bring the bottle of coffee from the kitchen shelf to stand next to it, put the paper coffee filter on top of the coffee maker, stand the saucer next to the coffee maker with the coffee cup on the saucer, and stand the electric kettle next to the coffee maker.",
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    "hiding_Easter_eggs": dict(
        challenge_task="hiding_Easter_eggs",
        scene="house_double_floor_lower",
        text="Hide the Easter eggs in the garden. The three eggs are inside the wicker basket on the lawn; take all three out and lay them on the lawn next to one tree (any tree in the garden, but the same tree for all three).",
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    "sorting_books_on_shelf": dict(
        challenge_task="sorting_books_on_shelf",
        scene="house_double_floor_upper",
        text="Sort the books in the living-room bookcase into stacks by kind. There are three comic books, two notebooks and two hardbacks; some are inside the bookcase and some are lying on top of books of another kind. Keep all seven inside the bookcase, stack the three comic books together, lay one notebook on the other, and lay one hardback on the other.",
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    "clean_up_broken_glass": dict(
        challenge_task="clean_up_broken_glass",
        scene="restaurant_diner",
        text="Three pieces of broken glass lie on the dining-room floor; put all of them inside the trash can that stands on the corridor floor.",
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    "packing_meal_for_delivery": dict(
        challenge_task="packing_meal_for_delivery",
        scene="restaurant_diner",
        text="Pack three hamburgers for delivery. The three wrapped hamburgers lie on a tray on the kitchen countertop, next to three sacks and a storage container; put each hamburger into its own sack and stand all three sacks on top of the storage container.",
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    "dispose_of_glass": dict(
        challenge_task="dispose_of_glass",
        scene="hotel_suite_large",
        text="Four water glasses stand on the bathroom sink; put all four inside the trash can that stands on the bedroom floor.",
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    "setting_mousetraps": dict(
        challenge_task="setting_mousetraps",
        scene="house_double_floor_upper",
        text="Set the four mousetraps, which lie on the bathroom cabinet, on the bathroom floor, with exactly two of them under or next to one of the bathroom sinks.",
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    "carrying_out_garden_furniture": dict(
        challenge_task="carrying_out_garden_furniture",
        scene="house_single_floor",
        text="Carry the garden furniture out of the house. The lawn chair and the wheelbarrow stand on the living-room floor; put the lawn chair on the garden floor and the wheelbarrow on a lawn.",
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    "putting_up_Christmas_decorations_inside": dict(
        challenge_task="putting_up_Christmas_decorations_inside",
        scene="house_single_floor",
        text="Decorate the house for Christmas. In the living room stand a Christmas tree, three gift boxes and a wicker basket holding a wreath, three candy canes and two pillar candles. Put the gift boxes by the tree, both candles on one dining-room table, one candy cane on a table, and the wreath and the two other candy canes on a sofa.",
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    "stacking_wood": dict(
        challenge_task="stacking_wood",
        scene="house_single_floor",
        text="Six logs lie spread out on the driveway in the garden; stack them so that every log touches at least one other log.",
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    "setting_the_table": dict(
        challenge_task="setting_the_table",
        scene="house_single_floor",
        text="Set the dining-room breakfast table for two. The two plates are inside a kitchen cabinet, the two cupcakes inside the kitchen refrigerator, and two forks and two table knives lie on the kitchen sink. Put both plates on the breakfast table, one cupcake on each plate, and one fork and one knife next to each plate.",
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    "boxing_food_after_dinner": dict(
        challenge_task="boxing_food_after_dinner",
        scene="house_single_floor",
        text="Box up the leftovers. Two tacos lie on two plates on the kitchen countertop and an empty tupperware is inside a kitchen cabinet; put both tacos into the tupperware, the tupperware into the refrigerator, and both plates into the sink, and leave the refrigerator closed.",
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    "rearranging_kitchen_furniture": dict(
        challenge_task="rearranging_kitchen_furniture",
        scene="house_double_floor_lower",
        text="Put the toaster, the food processor and the French press, which stand on the kitchen countertop, away into one kitchen cabinet, and close that cabinet.",
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    "bringing_paper_to_recycling": dict(
        challenge_task="bringing_paper_to_recycling",
        scene="house_double_floor_lower",
        text="Take the paper out to recycling. A sack stands on the kitchen floor and a newspaper lies on the kitchen countertop; put both inside the recycling bin that stands on the garden floor, and close the bin.",
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    "put_together_a_basic_pruning_kit": dict(
        challenge_task="put_together_a_basic_pruning_kit",
        scene="house_double_floor_lower",
        text="In the garage, put the pruner and the shears, which lie on the floor, inside the toolbox, which also stands on the floor, and close the toolbox; the toolbox stays on the floor.",
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    "clearing_food_from_table_into_fridge": dict(
        challenge_task="clearing_food_from_table_into_fridge",
        scene="house_double_floor_lower",
        text="Clear the leftovers from the kitchen breakfast table into the fridge. A half chicken and a half apple pie lie on two plates on the table, and two empty tupperwares stand on the countertop; put the chicken and the pie into tupperwares, put both tupperwares into the refrigerator, and leave it closed.",
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    "carrying_in_groceries": dict(
        challenge_task="carrying_in_groceries",
        scene="house_double_floor_lower",
        text="Bring the groceries in from the car. In the garage the car stands open with a sack inside it holding a beefsteak tomato and a carton of milk; put the tomato and the milk into a refrigerator in the kitchen, then close the car and the refrigerator.",
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    "turning_on_radio": dict(
        challenge_task="turning_on_radio",
        scene="house_double_floor_lower",
        text="Switch on the radio receiver that stands on the table in the living room.",
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    "installing_a_scanner": dict(
        challenge_task="installing_a_scanner",
        scene="office_cubicles_right",
        text="On the table in the private office stand a scanner (switched off) and a laptop; stand the scanner next to the laptop and switch the scanner on.",
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    "cook_broccolini": dict(
        challenge_task="cook_broccolini",
        scene="restaurant_diner",
        text="Cook the broccolini with garlic. Three broccolini and two garlic cloves lie on a plate on the kitchen countertop, next to a frying pan; put all of them into the frying pan, put the pan on the stove, and cook them.",
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    "cook_a_brisket": dict(
        challenge_task="cook_a_brisket",
        scene="house_double_floor_lower",
        text="Cook the brisket. It is raw, inside the kitchen refrigerator; a chopping board and a frying pan are on the countertop and there is an oven in the kitchen. Cook the brisket and put it on the chopping board; the frying pan must end up on the countertop.",
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    "thawing_frozen_food": dict(
        challenge_task="thawing_frozen_food",
        scene="house_double_floor_lower",
        text="Thaw the frozen food. A frozen chicken breast and a frozen slice of bread lie on two plates inside the kitchen refrigerator. Put the chicken breast, on a plate, into the microwave oven, close the microwave and switch it on; put the bread slice, on a plate, on the countertop; close the refrigerator; neither food may still be frozen.",
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    "setting_the_fire": dict(
        challenge_task="setting_the_fire",
        scene="house_double_floor_lower",
        text="Light a fire in the living-room fireplace. Two pieces of firewood lie on the floor, and a newspaper and a cigar lighter lie on the table; put the newspaper inside the fireplace with both pieces of firewood on top of it, set the newspaper and both pieces of firewood on fire, and switch the lighter off again.",
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    "hanging_pictures": dict(
        challenge_task="hanging_pictures",
        scene="house_double_floor_lower",
        text="Hang the poster, which lies on the kitchen countertop, on one of the wall nails in the kitchen.",
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    "vacuuming_floors": dict(
        challenge_task="vacuuming_floors",
        scene="house_double_floor_upper",
        text="The bedroom floor is covered with dust and a vacuum cleaner stands on it; remove every bit of dust from the floor.",
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    'store_honey': dict(
        challenge_task='store_honey',
        scene='Rs_int',
        text='Put the jar of honey, which stands on the kitchen countertop, inside the cabinet in the entryway.',
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    'make_gift_bags_for_baby_showers': dict(
        challenge_task='make_gift_bags_for_baby_showers',
        scene='Rs_int',
        text='Make two gift bags in the living room. The two sacks lie on the breakfast table, the two toy dice stand on the cabinet, and the two wafers are inside that cabinet. Move both sacks onto the coffee table and put one toy die and one wafer into each sack.',
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    'preparing_lunch_box': dict(
        challenge_task='preparing_lunch_box',
        scene='house_single_floor',
        text='Pack the lunch box on the kitchen countertop. The two apple halves, the club sandwich and the chocolate chip cookie lie on the chopping board on the countertop; the bottle of tea is inside the kitchen refrigerator. Put all five into the packing box and leave the refrigerator closed.',
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    'bringing_water': dict(
        challenge_task='bringing_water',
        scene='house_single_floor',
        text='Take both bottles out of the kitchen refrigerator, put them on the coffee table in the living room, and leave the refrigerator closed.',
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    'outfit_a_basic_toolbox': dict(
        challenge_task='outfit_a_basic_toolbox',
        scene='house_single_floor',
        text='Pack the toolbox in the utility room. The drill, the pliers, the flashlight, the allen wrench and the screwdriver lie on the table there, next to the toolbox. Put all five tools inside the toolbox, keep the toolbox on the table, and close it.',
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    'store_produce': dict(
        challenge_task='store_produce',
        scene='restaurant_diner',
        text='Store the produce. Two mangos and two pomegranates are in the wicker basket on the kitchen floor; put all four into one of the two kitchen refrigerators, all into the same one.',
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    'putting_dirty_dishes_in_sink': dict(
        challenge_task='putting_dirty_dishes_in_sink',
        scene='restaurant_diner',
        text='Clear the dirty dishes. Two bowls and two plates stand on the booth in the dining room; put all four into the sink in the kitchen (the dirt on them does not matter).',
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    'unloading_the_car': dict(
        challenge_task='unloading_the_car',
        scene='house_double_floor_lower',
        text='Unload the car. The briefcase and the satchel are inside the car in the garage; take both out and put them next to the sofa in the living room.',
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    'tidying_living_room': dict(
        challenge_task='tidying_living_room',
        scene='house_double_floor_upper',
        text='Tidy the living room. Put the potted plant and the newspaper, which lie on the floor, on the coffee table; put the hardback book from the coffee table inside a bookcase; and put the notebook from the coffee table on the desk.',
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    'collecting_aluminum_cans': dict(
        challenge_task='collecting_aluminum_cans',
        scene='hotel_suite_large',
        text='Collect the six soda cans in the bedroom, three lying on the bed and three on the floor, into the bucket that stands on the bedroom floor.',
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    'rearrange_your_room': dict(
        challenge_task='rearrange_your_room',
        scene='hotel_suite_large',
        text='Rearrange the bedroom. Move the tissue dispenser from the armchair onto one of the stands, and put the two pillows that lie on the floor onto the two beds, one pillow on each bed.',
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    'laying_tile_floors': dict(
        challenge_task='laying_tile_floors',
        scene='office_cubicles_right',
        text='Lay the tiles. The four tiles lie on the corridor floor; put all four on the bathroom floor, each tile next to at least one of the other tiles.',
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    'putting_dishes_away_after_cleaning': dict(
        challenge_task='putting_dishes_away_after_cleaning',
        scene='house_single_floor',
        text='Put the clean dishes away. Eight plates lie on the two kitchen countertops, four on each; put all eight inside one and the same kitchen cabinet, and leave every kitchen cabinet closed.',
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    'tidying_bedroom': dict(
        challenge_task='tidying_bedroom',
        scene='house_single_floor',
        text='Tidy the bedroom. The two sandals lie on the bedroom floor and the book lies on the bed. Put one sandal next to the bed and the other sandal next to the first one, and put the book on top of a table in the bedroom.',
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    'can_meat': dict(
        challenge_task='can_meat',
        scene='house_single_floor',
        text='Can the sausages. The four cooked bratwursts lie on the chopping board on the kitchen countertop, and the two hinged jars are inside the kitchen cabinet. Put exactly two bratwursts into each jar, close both jars, have both jars inside that cabinet at the end, and leave the cabinet closed.',
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    'cleaning_up_branches_and_twigs': dict(
        challenge_task='cleaning_up_branches_and_twigs',
        scene='house_double_floor_lower',
        text='Clean up the garden. Four branches lie on the ground in the garden, where the recycling bin also stands; put all four inside the recycling bin and leave the bin standing on the ground.',
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    'tidying_bathroom': dict(
        challenge_task='tidying_bathroom',
        scene='hotel_suite_large',
        text='Tidy the bathroom. The bar of soap, the soap dish and a cork lie on the sink; the tissue dispenser, a roll of toilet tissue and the wastebasket stand on the bathroom floor. Put the bar of soap on the soap dish, the tissue dispenser on the sink, the toilet tissue on the toilet, and the cork inside the wastebasket.',
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    'setup_a_bar_for_a_cocktail_party': dict(
        challenge_task='setup_a_bar_for_a_cocktail_party',
        scene='restaurant_diner',
        text='Set up the bar. On the cabinet in the bar stand three cans of soda, a tray with six ice cubes, an ice bucket, a corkscrew, a wine bottle and two wine glasses. Put the wine bottle on the bar countertop; put the three cans on that countertop, each next to another can; put all six ice cubes inside the bucket and the bucket on the countertop; put both wine glasses on the countertop next to each other, at least one of them next to the wine bottle; and put the corkscrew on the countertop next to the wine bottle.',
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    'dispose_of_batteries': dict(
        challenge_task='dispose_of_batteries',
        scene='office_cubicles_right',
        text='Dispose of the batteries. Two batteries lie on the desk in the private office and one on the cabinet in the copy room; put all three inside the wastebasket that stands on the copy-room floor, and leave the wastebasket standing on the floor.',
        simulator="behavior", robot="r1pro", image="behavior",
    ),
}

TOP_DOWN_XYZW = (1.0, 0.0, 0.0, 0.0)  # end effector pointing straight down (what _sample_grasp_pose returns)

ACTION_LAYOUT = ("robot.action_dim = 25 with r1pro_primitives_eval.yaml: base (3, holonomic base joints x,y,rz as position "
                 "targets in the robot frame), trunk (4), arm_left (7), gripper_left (2), arm_right (7), gripper_right (2); "
                 "all position-mode JointControllers with absolute targets; see robot.controller_action_idx. One row per env "
                 "step (30 Hz control, 120 Hz physics). Quaternions everywhere are XYZW (OmniGibson convention), poses are in "
                 "the world frame.")


def _log(*a: Any) -> None:
    print("[rcb]", *a, file=sys.stderr, flush=True)


def _sha_of_text(s: str) -> str:
    return hashlib.sha1(s.encode()).hexdigest()[:12]


class PrimitiveError(RuntimeError):
    """A primitive could not be planned or executed (the episode is still alive unless said otherwise)."""


# --------------------------------------------------------------------------- rcb-limited/2.2 inputs: geometry helpers
GL2CV = np.diag([1.0, -1.0, -1.0, 1.0])   # camera frame, OpenGL axes (x right, y up, z back) -> OpenCV (x right, y down, z forward)
DEPTH_MAX_M = 65.535                      # z-depth beyond this reads 0 (as the limited service's uint16-millimetre encoding)
KIN_TOL_POS_M, KIN_TOL_ROT_RAD, KIN_MAX_ITERS = 0.001, 0.01, 200   # IK defaults


def _R_of_xyzw(q) -> np.ndarray:
    x, y, z, w = np.asarray(q, dtype=np.float64).reshape(4) / max(1e-12, float(np.linalg.norm(q)))
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
                     [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                     [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])


def _xyzw_of_R(R) -> np.ndarray:
    R = np.asarray(R, dtype=np.float64)
    t = R[0, 0] + R[1, 1] + R[2, 2]
    if t > 0:
        s = 2.0 * math.sqrt(t + 1.0); q = [(R[2, 1] - R[1, 2]) / s, (R[0, 2] - R[2, 0]) / s, (R[1, 0] - R[0, 1]) / s, 0.25 * s]
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = 2.0 * math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]); q = [0.25 * s, (R[0, 1] + R[1, 0]) / s, (R[0, 2] + R[2, 0]) / s, (R[2, 1] - R[1, 2]) / s]
    elif R[1, 1] > R[2, 2]:
        s = 2.0 * math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]); q = [(R[0, 1] + R[1, 0]) / s, 0.25 * s, (R[1, 2] + R[2, 1]) / s, (R[0, 2] - R[2, 0]) / s]
    else:
        s = 2.0 * math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]); q = [(R[0, 2] + R[2, 0]) / s, (R[1, 2] + R[2, 1]) / s, 0.25 * s, (R[1, 0] - R[0, 1]) / s]
    q = np.asarray(q); q = q / np.linalg.norm(q)
    return q if q[3] >= 0 else -q


def _T_of(pos, quat_xyzw) -> np.ndarray:
    T = np.eye(4); T[:3, :3] = _R_of_xyzw(quat_xyzw); T[:3, 3] = np.asarray(pos, dtype=np.float64).reshape(3)
    return T


def _pose7(T) -> list[float]:
    return [float(v) for v in T[:3, 3]] + [float(v) for v in _xyzw_of_R(T[:3, :3])]


def _rotvec(R) -> np.ndarray:
    """Axis * angle of the rotation R (the log map)."""
    c = max(-1.0, min(1.0, (float(np.trace(R)) - 1.0) / 2.0)); a = math.acos(c)
    if a < 1e-9:
        return np.zeros(3)
    if a > math.pi - 1e-6:                           # near pi: the axis from the diagonal
        ax = np.sqrt(np.maximum((np.diag(R) + 1.0) / 2.0, 0.0))
        i = int(np.argmax(ax)); ax[(i + 1) % 3] = math.copysign(ax[(i + 1) % 3], R[i, (i + 1) % 3]); ax[(i + 2) % 3] = math.copysign(ax[(i + 2) % 3], R[i, (i + 2) % 3])
        return ax / np.linalg.norm(ax) * a
    return np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]]) * (a / (2.0 * math.sin(a)))


def _np(x) -> np.ndarray:
    return np.asarray(x.cpu() if hasattr(x, "cpu") else x)


def _clean_depth(z) -> np.ndarray:
    """float32 (H, W) z-depth in metres; no reading (nothing rendered, not finite, <= 0, beyond DEPTH_MAX_M) = 0."""
    z = np.asarray(_np(z), dtype=np.float32).copy()
    if z.ndim == 3:
        z = z[..., 0]
    z[~np.isfinite(z) | (z <= 0) | (z > DEPTH_MAX_M)] = 0.0
    return z


class _Kin:
    """The robot's kinematic model, read at run time from the simulator's own articulation: every USD joint of the robot
    (its two bodies, joint frames and axis) exactly as PhysX simulates it; nothing is copied from the dataset. Forward
    kinematics of the links below the base link for the trunk + arm joints `q` (fingers and wheels at 0), analytic
    Jacobians and a damped-least-squares IK. Every pose is in the base-link frame. Pure numpy: it never touches the
    simulator after construction."""

    def __init__(self, robot, stage, q_names: list[str], base_link: str):
        from pxr import Usd, UsdPhysics
        self.joints: dict[str, dict] = {}
        for prim in Usd.PrimRange(stage.GetPrimAtPath(robot.prim_path)):
            if not prim.IsA(UsdPhysics.Joint):
                continue
            b0, b1 = prim.GetRelationship("physics:body0").GetTargets(), prim.GetRelationship("physics:body1").GetTargets()
            if not b0 or not b1 or not all(str(b[0]).startswith(robot.prim_path + "/") for b in (b0, b1)) or \
                    (prim.HasAttribute("physics:excludeFromArticulation") and prim.GetAttribute("physics:excludeFromArticulation").Get()):
                continue                            # the robot's own articulation only (an assisted grasp's joint is not)
            tn = prim.GetTypeName()
            kind = "revolute" if "Revolute" in tn else "prismatic" if "Prismatic" in tn else "fixed" if "Fixed" in tn else None
            if kind is None:
                continue

            def frame(p, r):
                p = prim.GetAttribute(p).Get(); r = prim.GetAttribute(r).Get()
                im = r.GetImaginary()
                return _T_of([p[0], p[1], p[2]], [im[0], im[1], im[2], r.GetReal()])
            ax = prim.GetAttribute("physics:axis").Get() if prim.HasAttribute("physics:axis") else "X"
            self.joints[prim.GetName()] = {"parent": str(b0[0]).split("/")[-1], "child": str(b1[0]).split("/")[-1], "kind": kind,
                                           "T0": frame("physics:localPos0", "physics:localRot0"),
                                           "T1inv": np.linalg.inv(frame("physics:localPos1", "physics:localRot1")),
                                           "axis": "XYZ".index(str(ax).upper())}
        self.by_child = {j["child"]: n for n, j in self.joints.items()}
        self.base_link, self.q_names = base_link, list(q_names)
        self.qi = {n: i for i, n in enumerate(self.q_names)}
        # links below the base link, parents first
        kids: dict[str, list[str]] = {}
        for n, j in self.joints.items():
            kids.setdefault(j["parent"], []).append(n)
        self.order, todo = [], [base_link]
        while todo:
            p = todo.pop(0)
            for n in sorted(kids.get(p, [])):
                self.order.append(n); todo.append(self.joints[n]["child"])
        self.links = [base_link] + [self.joints[n]["child"] for n in self.order]
        # the chain of q joints above each link
        self.chain = {}
        for l in self.links:
            ch, c = [], l
            while c in self.by_child and c != base_link:
                n = self.by_child[c]
                if n in self.qi:
                    ch.append(n)
                c = self.joints[n]["parent"]
            self.chain[l] = ch[::-1]
        missing = [n for n in self.q_names if n not in self.joints]
        assert not missing, f"joints not found in the robot's articulation: {missing}"

    def _motion(self, j: dict, v: float) -> np.ndarray:
        M_ = np.eye(4)
        if j["kind"] == "revolute":
            c, s = math.cos(v), math.sin(v); a = j["axis"]; b, d = (a + 1) % 3, (a + 2) % 3
            M_[b, b], M_[b, d], M_[d, b], M_[d, d] = c, -s, s, c
        elif j["kind"] == "prismatic":
            M_[j["axis"], 3] = v
        return M_

    def fk(self, q, want_joint_frames: bool = False):
        """{link: 4x4 pose in the base-link frame} (and {q joint: 4x4 joint frame 0 in the base frame})."""
        q = np.asarray(q, dtype=np.float64).reshape(-1)
        T = {self.base_link: np.eye(4)}; JF = {}
        for n in self.order:
            j = self.joints[n]
            Tj = T[j["parent"]] @ j["T0"]
            if n in self.qi:
                JF[n] = Tj
                Tj = Tj @ self._motion(j, float(q[self.qi[n]]))
            T[j["child"]] = Tj @ j["T1inv"]
        return (T, JF) if want_joint_frames else T

    def jacobian(self, JF: dict, link: str, p: np.ndarray, cols: list[int]) -> np.ndarray:
        """6 x len(cols) Jacobian (linear rows first) of a point p (base frame) rigidly attached to `link`."""
        Jm = np.zeros((6, len(cols)))
        on = set(self.chain[link])
        for k, i in enumerate(cols):
            n = self.q_names[i]
            if n not in on:
                continue
            j = self.joints[n]; a = JF[n][:3, j["axis"]]
            if j["kind"] == "revolute":
                Jm[:3, k] = np.cross(a, p - JF[n][:3, 3]); Jm[3:, k] = a
            else:
                Jm[:3, k] = a
        return Jm

    def solve(self, targets: dict, q0, cols: list[int], lo, hi, tol_p: float, tol_r: float, iters: int):
        """Damped least squares from q0 over the joints `cols`: targets = {name: (link, link_T_frame, base_T_target)}.
        Returns (q, {name: (pos err m, rot err rad)}, converged)."""
        q = np.clip(np.asarray(q0, dtype=np.float64).copy(), lo, hi); W = 0.3      # 1 rad of orientation error ~ 0.3 m

        def errors(qq):
            T, JF = self.fk(qq, True); out = {}
            for name, (link, off, Tt) in targets.items():
                Tc = T[link] @ off
                ep = Tt[:3, 3] - Tc[:3, 3]; er = _rotvec(Tt[:3, :3] @ Tc[:3, :3].T)
                out[name] = (ep, er, Tc, link)
            return out, JF

        def cost(e):
            return sum(float(ep @ ep) + W * W * float(er @ er) for ep, er, _, _ in e.values())

        e, JF = errors(q); c = cost(e); lam = 1e-3
        for _ in range(max(1, int(iters))):
            if all(np.linalg.norm(ep) <= tol_p and np.linalg.norm(er) <= tol_r for ep, er, _, _ in e.values()):
                break
            J = np.vstack([np.vstack([Jm[:3], W * Jm[3:]]) for Jm in (self.jacobian(JF, link, Tc[:3, 3], cols) for _, _, Tc, link in e.values())])
            r = np.concatenate([np.concatenate([ep, W * er]) for ep, er, _, _ in e.values()])
            step_ok = False
            for _ in range(8):
                dq = J.T @ np.linalg.solve(J @ J.T + lam * np.eye(J.shape[0]), r)
                s = float(np.max(np.abs(dq)))
                if s > 0.3:
                    dq *= 0.3 / s
                qn = q.copy(); qn[cols] = np.clip(q[cols] + dq, lo[cols], hi[cols])
                en, JFn = errors(qn); cn = cost(en)
                if cn < c:
                    q, e, JF, c = qn, en, JFn, cn; lam = max(lam * 0.3, 1e-6); step_ok = True
                    break
                lam *= 10.0
            if not step_ok:
                break
        err = {name: (float(np.linalg.norm(ep)), float(np.linalg.norm(er))) for name, (ep, er, _, _) in e.items()}
        return q, err, all(p <= tol_p and r_ <= tol_r for p, r_ in err.values())


# --------------------------------------------------------------------------- warp / Isaac quirks
def _import_warp_early() -> None:
    """Bind the pip `warp` package and its `warp.torch` submodule before Isaac Sim's bundled omni.warp (1.8.2) is started:
    otherwise cuRobo can end up calling a mixed, uninitialised warp (measured: 'NoneType has no attribute cuda_devices')."""
    try:
        import warp  # noqa: F401
        import warp.torch  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        _log("warp pre-import skipped:", repr(exc))


def ensure_warp_runtime() -> None:
    """After the Evaluator is built, the `warp` package may expose Isaac's own warp.context with runtime None; initialise it."""
    try:
        pkg = sys.modules.get("warp")
        for ctx in {id(c): c for c in [getattr(pkg, "context", None), sys.modules.get("warp.context")] if c is not None}.values():
            if getattr(ctx, "runtime", None) is None:
                ctx.init()
                _log("warp runtime initialised for", getattr(ctx, "__file__", "?"))
    except Exception as exc:  # noqa: BLE001
        _log("ensure_warp_runtime failed:", repr(exc))


# --------------------------------------------------------------------------- evaluator wrappers (hydra targets)
try:  # only importable inside the simulator image; the module must still import on a bare host for --help / selftest.
    from omnigibson.envs import EnvironmentWrapper as _EnvWrapper
    from omnigibson.eval.utils.eval_utils import set_sensor_modalities as _set_modalities

    class TinyCamWrapper(_EnvWrapper):
        """Keeps the robot cameras the evaluator expects, but renders 16x16 RGB only (rendering is ~40% of step cost)."""

        def __init__(self, env, size: int | None = None):
            # 16x16 by default (rendering is ~40% of step cost); standard mode raises it with RCB_CAM_SIZE,
            # because there the agent has nothing to work from but these images.
            size = int(os.environ.get("RCB_CAM_SIZE", size or 16))
            super().__init__(env=env)
            robot = env.robots[0]
            for name, sensor in robot.sensors.items():
                if not hasattr(sensor, "image_height") or not hasattr(sensor, "image_width"):
                    continue
                _set_modalities(sensor, {"rgb"})
                sensor.image_height = size
                sensor.image_width = size
                space = sensor.load_observation_space()
                if env.observation_space is not None:
                    env.observation_space.spaces[robot.name].spaces[name] = space
except Exception:  # noqa: BLE001
    TinyCamWrapper = None  # type: ignore[assignment]


# --------------------------------------------------------------------------- session
class _QueuePolicy:
    """LocalPolicy adapter: Evaluator.step() asks policy.forward(obs); we hand it the action Session.step() was given."""

    def __init__(self, robot):
        self.robot, self.next = robot, None

    def act(self, obs):
        a = self.next
        self.next = None
        return a if a is not None else self.robot.q_to_action(self.robot.get_joint_positions())

    def reset(self):
        self.next = None


class Session:
    def __init__(self, task: str, instance: str | Path | None = None, *, instance_id: int | None = None,
                 mode: str = "public_test", robot_config: str | Path | None = None, cameras: str = "default",
                 strict: bool = False):
        if task not in TASKS:
            raise KeyError(f"unknown task {task!r}; known: {list(TASKS)}")
        self.task, self.spec = task, TASKS[task]
        _import_warp_early()
        import torch as th
        import omnigibson as og
        from omnigibson.macros import gm
        from omegaconf import OmegaConf
        gm.HEADLESS = True
        from omnigibson.eval.utils.eval_utils import DEFAULT_EVAL_SEED, seed_everything
        from omnigibson.eval.evaluator import Evaluator, resolve_instance_ids
        self.th, self.og = th, og

        inst = None
        if instance is not None:
            inst = json.load(open(instance))
            if inst.get("task") != task:
                raise ValueError(f"instance task {inst.get('task')} != session task {task}")
            instance_id = int(inst["instance_id"]); mode = inst.get("mode", mode)
            if robot_config is None and inst.get("robot_config"):
                # bare file name: next to the instance file (tests/ copy for the verifier), else next to this module
                cand = [Path(instance).parent / inst["robot_config"], Path(__file__).parent / Path(inst["robot_config"]).name]
                robot_config = next((c for c in cand if c.exists()), cand[0])
        if instance_id is None:
            raise ValueError("need instance=path or instance_id=<challenge instance id>")
        if robot_config is None:
            robot_config = Path(__file__).parent / "r1pro_primitives_eval.yaml"
        self.robot_config_path = Path(robot_config)
        self.robot_config_sha = _sha_of_text(self.robot_config_path.read_text())
        self.instance_id, self.mode, self.cameras = int(instance_id), mode, cameras

        seed = seed_everything(DEFAULT_EVAL_SEED)
        wrapper = "omnigibson.eval.wrappers.DefaultWrapper" if cameras == "default" else f"{__name__}.TinyCamWrapper"
        cfg = OmegaConf.create({
            "env_wrapper": {"_target_": wrapper}, "policy_name": "local",
            "model": {"_target_": "omnigibson.eval.policies.LocalPolicy", "action_dim": None},
            "headless": True, "partial_scene_load": True, "max_steps": None, "write_video": False,
            "mode": mode, "seed": seed, "task": {"name": self.spec["challenge_task"]},
            "robot": OmegaConf.to_container(OmegaConf.load(str(self.robot_config_path)), resolve=True),
        })
        t0 = time.time()
        _log(f"building evaluator for {task} (instance {self.instance_id}, cameras={cameras}); ~3 min ...")
        self.ev = Evaluator(cfg)
        ensure_warp_runtime()
        self.env = self.ev.env
        self.robot = self.env.robots[0]
        self.action_dim = int(self.robot.action_dim)
        self._policy = _QueuePolicy(self.robot)
        self.ev.policy.policy = self._policy
        self._recording: list | None = None
        self.episode_done = False  # set when env.step reports terminated/truncated; primitives stop stepping then
        self._mg = None             # cuRobo, for ik() (created on first use)
        self._camfix = None         # cameras: parent link, mount, intrinsics (camera_info(), first use)
        self._kinm = None           # kinematic model of the robot (kinematics(), robot_spec(), first use)
        self._last_action = None    # the last action sent: hold_action() repeats it
        self._stepped = False       # anything stepped since the instance was loaded / reset (replay)
        self._names_by_obj: dict[int, str] = {}
        self._resets = 0
        self._total_steps = 0
        self._end_logged = False
        tc = getattr(self.env.task, "_termination_conditions", {}) or {}
        self.challenge_max_steps = int(getattr(tc.get("timeout"), "_max_steps", 0)) or None
        self._lift_timeout()
        _slog("session_start", task=task, instance_id=self.instance_id)
        import atexit
        atexit.register(self._log_end)
        _log(f"evaluator ready in {time.time() - t0:.0f}s; action_dim={self.action_dim}")

        # load the frozen instance: fresh reset -> instance TRO state + robot pose -> settle -> reset (official recipe)
        self.ev.reset()
        self.ev.load_task_instance(self.instance_id)
        self.ev.reset()
        self._lift_timeout()
        self.S0 = self._flat_state()
        self.instance_sha = self._sha(self.S0)
        expected = inst.get("state_sha") if inst else None
        # exact sha (bit-reproducible on one host), else every task object's pose within tolerance (another host may change
        # the last bits; a wrong dataset / simulator / robot config moves objects by millimetres or more)
        self.instance_exact = expected is None or expected == self.instance_sha
        self.instance_matches = self.instance_exact or (inst is not None and self._poses_match(inst))
        if not self.instance_exact:
            if self.instance_matches:
                _log(f"WARNING: state sha {self.instance_sha} != {expected} but every object pose matches within tolerance (different host?)")
            else:
                msg = f"instance state sha {self.instance_sha} != expected {expected} and poses differ (dataset/simulator/robot-config drift?)"
                if strict:
                    raise RuntimeError(msg)
                _log("WARNING:", msg)
        _log(f"instance {self.instance_id} loaded; state_sha={self.instance_sha}; max_steps={self.max_steps}")

    def _poses_match(self, inst: dict, pos_tol: float = 2e-3, quat_tol: float = 2e-2) -> bool:
        try:
            objs = self.objects()
            ref_objs = inst.get("objects") or {}
            for name, ref in ref_objs.items():
                cur = objs.get(name)
                if cur is None or np.max(np.abs(np.asarray(cur["position"]) - np.asarray(ref["position"]))) > pos_tol:
                    return False
                q0, q1 = np.asarray(cur["orientation_xyzw"]), np.asarray(ref["orientation_xyzw"])
                if min(np.max(np.abs(q0 - q1)), np.max(np.abs(q0 + q1))) > quat_tol:
                    return False
            return bool(ref_objs)
        except Exception as exc:  # noqa: BLE001
            _log("pose comparison failed:", repr(exc)[:120])
            return False

    # ---- state helpers
    def _flat_state(self):
        st = self.og.sim.dump_state(serialized=True)
        if isinstance(st, dict):
            st = self.th.cat([self.th.as_tensor(v).flatten() for v in st.values()])
        return self.th.as_tensor(st).detach().cpu().contiguous()

    @staticmethod
    def _sha(t) -> str:
        return hashlib.sha1(t.numpy().tobytes()).hexdigest()[:16]

    def state_sha(self) -> str:
        return self._sha(self._flat_state())

    def _lift_timeout(self) -> None:
        """No step budget: the challenge's timeout termination goes up to the runaway guard MAX_STEPS (the BDDL goal
        still ends the episode the moment it holds)."""
        tc = getattr(self.env.task, "_termination_conditions", {}) or {}
        if tc.get("timeout") is not None:
            tc["timeout"]._max_steps = MAX_STEPS

    @property
    def max_steps(self) -> int | None:
        tc = getattr(self.env.task, "_termination_conditions", {}) or {}
        return int(getattr(tc.get("timeout"), "_max_steps", 0)) or None

    # ---- episode control
    def reset(self) -> None:
        """Return to the frozen instance state. In-process this is approximate (a few 1e-6 differences after
        load_state); a fresh process reproduces the instance exactly, which is what the verifier does."""
        _slog("reset", task=self.task, n=self._resets + 1, sim_steps_before=int(self.env.episode_steps))
        self._resets += 1
        self._total_steps += int(self.env.episode_steps)
        self._recording = None
        self.episode_done = False
        self._last_action = None
        self._stepped = False
        self._policy.reset()
        self.ev.reset()
        self._lift_timeout()
        self.og.sim.load_state(self.S0.clone(), serialized=True)

    def step(self, action) -> tuple[bool, bool]:
        """Apply one low-level action (robot.action_dim,) for one control step. Returns (terminated, truncated)."""
        a = self.th.as_tensor(np.asarray(action, dtype=np.float32)).flatten()
        if a.numel() != self.action_dim:
            raise ValueError(f"action must have {self.action_dim} entries, got {a.numel()}")
        if self.episode_done:
            raise PrimitiveError("episode is over (success or timeout); call reset() before stepping again")
        if self._recording is not None:
            self._recording.append(a.clone())
        self._stepped = True
        self._last_action = a.clone()
        self._policy.next = a
        terminated, truncated = self.ev.step()
        if terminated or truncated:
            self.episode_done = True
        return terminated, truncated

    def _gripper_cmd(self, arm: str, open_: bool):
        """The action entries of `arm`'s gripper: open = both fingers 2 cm beyond their upper limit (assisted grasping only
        releases on a command at or above the limit), closed = their lower limit (it holds whatever the fingers touch)."""
        r = self.robot
        ji = r.gripper_control_idx[arm]
        q = r.get_joint_positions().clone()
        q[ji] = (r.joint_upper_limits[ji] + 0.02) if open_ else r.joint_lower_limits[ji]
        return self.th.as_tensor(r.q_to_action(q)).flatten()[r.controller_action_idx[f"gripper_{arm}"]].clone()

    def hold_action(self):
        """The action that holds the current targets: the last action sent, with the base entries at 0 (they are per-step
        displacements; 0 = stand still). Before the first step (and after reset()) the measured joint positions with both
        grippers commanded open. (A hold built from MEASURED positions would re-command a gripper to wherever its fingers
        are, and assisted grasping keys on the command: it would drop a wide held object or re-grab one just let go.)"""
        r = self.robot
        idx = r.controller_action_idx
        if self._last_action is not None:
            a = self._last_action.clone()
        else:
            a = self.th.as_tensor(r.q_to_action(r.get_joint_positions())).flatten().clone()
            for arm in ("left", "right"):
                a[idx[f"gripper_{arm}"]] = self._gripper_cmd(arm, True).to(a.dtype)
        a[idx["base"]] = 0.0
        return a

    def status(self) -> dict[str, Any]:
        out = {"success": bool(self.env.task.success), "sim_steps": int(self.env.episode_steps), "resets": self._resets,
               "state_sha": self.state_sha(), "q_score": None}
        try:
            for m in self.ev.metrics:
                agg = m.aggregate(self.env)
                if isinstance(agg, dict) and "q_score" in agg:
                    out["q_score"] = float(agg["q_score"].get("final", 0.0))
        except Exception as exc:  # noqa: BLE001
            out["q_score_error"] = repr(exc)[:120]
        return out

    # ---- recording / trajectories
    def record_start(self) -> None:
        self._recording = []

    def record_stop(self) -> np.ndarray:
        acts = self.th.stack(self._recording).numpy() if self._recording else np.zeros((0, self.action_dim), np.float32)
        self._recording = None
        _slog("record", task=self.task, n_actions=int(len(acts)), success=bool(self.env.task.success))
        return acts.astype(np.float32)

    def save_trajectory(self, actions: np.ndarray, path: str | Path, meta: dict | None = None) -> None:
        np.savez(path, actions=np.asarray(actions, dtype=np.float32), task=self.task, instance_id=self.instance_id,
                 instance_sha=self.instance_sha, action_dim=self.action_dim, action_layout=ACTION_LAYOUT,
                 robot_config_sha=self.robot_config_sha, meta=json.dumps(meta or {}))

    def replay(self, actions: np.ndarray) -> dict[str, Any]:
        """Open-loop replay from the frozen initial state. In a session that has not stepped since the instance was
        loaded (the CLI `replay`, the verifier) the actions run from the loaded state itself, which reproduces a fresh
        process that ran them right after loading bit-exactly (measured: an oracle's live run and a fresh replay end on
        the same state sha). Otherwise reset() first, which is approximate: an in-process reset leaves PhysX's hidden
        solver/contact state different, and a replay after it drifts (putting_shoes_on_rack: q_score 1.0 live, 0.9)."""
        if self._stepped:
            self.reset()
        for a in np.asarray(actions, dtype=np.float32):
            terminated, truncated = self.step(a)
            if terminated or truncated:
                break
        st = self.status()
        _slog("replay", task=self.task, n_actions=int(len(actions)), success=st["success"])
        return st

    # ---- video (needs cameras="default" for a watchable resolution)
    def start_video(self, path: str | Path, fps: int = 30) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.ev.start_recording(str(path), rate=fps)

    def stop_video(self) -> None:
        self.ev.stop_recording()

    # ---- objects
    def _scope(self):
        return self.env.task.object_scope

    def get_object(self, name: str):
        ent = self._scope()[name]
        return getattr(ent, "wrapped_obj", ent)

    def objects(self) -> dict[str, dict]:
        """Task-relevant objects by BDDL name -> {category, position, orientation_xyzw}."""
        out = {}
        for name, ent in self._scope().items():
            obj = getattr(ent, "wrapped_obj", ent)
            if obj is None or not hasattr(obj, "get_position_orientation") or name.startswith("agent") or obj is self.robot:
                continue
            try:
                pos, quat = obj.get_position_orientation()
                out[name] = {"category": getattr(obj, "category", "?"), "position": [round(float(x), 4) for x in pos],
                             "orientation_xyzw": [round(float(x), 4) for x in quat]}
            except Exception:  # noqa: BLE001
                continue
        return out

    def _name_of(self, obj) -> str | None:
        for name, ent in self._scope().items():
            if getattr(ent, "wrapped_obj", ent) is obj:
                return name
        return None

    # ---- inverse kinematics: cuRobo, the motion library OmniGibson ships (created on first use)
    def _curobo(self):
        """cuRobo motion generator, used for IK only (~1 min and ~2 GB of GPU memory the first time)."""
        if self._mg is None:
            from omnigibson.action_primitives.curobo import CuRoboMotionGenerator
            ensure_warp_runtime()
            t0 = time.time()
            # low-memory settings (fit a 16 GB GPU next to Isaac): batch 1, no CUDA graphs, 128 IK seeds
            self._mg = CuRoboMotionGenerator(self.robot, batch_size=1, use_cuda_graph=False, collision_activation_distance=0.02,
                                             motion_cfg_kwargs={"num_ik_seeds": 128, "num_trajopt_seeds": 2, "num_graph_seeds": 2})
            _log(f"cuRobo IK ready in {time.time() - t0:.0f}s")
        return self._mg

    def ik(self, targets: dict, attempts: int = 4) -> dict[str, np.ndarray] | None:
        """Inverse kinematics for one arm or both together: `targets` = {"left"|"right": (pos(3), quat_xyzw(4))}, world-
        frame end-effector poses. Returns {"trunk": q(4), <arm>: q(7), ...} joint positions (rad) that reach all of them
        (the trunk may bend as well), or None if cuRobo finds no solution. Kinematics only: no collision checking against
        the scene."""
        from omnigibson.action_primitives.curobo import CuRoboEmbodimentSelection as Emb
        th, r, mg = self.th, self.robot, self._curobo()
        tp = {r.eef_link_names[a]: th.as_tensor(np.asarray(p, dtype=np.float32)).reshape(1, 3) for a, (p, _) in targets.items()}
        tq = {r.eef_link_names[a]: th.as_tensor(np.asarray(q, dtype=np.float32)).reshape(1, 4) for a, (_, q) in targets.items()}
        for _ in range(int(attempts)):  # cuRobo's IK is seeded randomly
            succ, js = mg.compute_trajectories(target_pos=tp, target_quat=tq, is_local=False, max_attempts=1, timeout=30.0,
                                               ik_fail_return=5, enable_finetune_trajopt=False, finetune_attempts=0,
                                               return_full_result=False, success_ratio=1.0, ik_only=True,
                                               ik_world_collision_check=False, skip_obstacle_update=True, emb_sel=Emb.ARM)
            ok = th.where(succ)[0].cpu()
            if len(ok):
                q = mg.path_to_joint_trajectory(js[ok[0]], get_full_js=False, emb_sel=Emb.ARM).cpu()
                q = q.reshape(-1, q.shape[-1])[-1]
                out = {"trunk": q[r.trunk_control_idx].numpy().astype(np.float64)}
                for a in targets:
                    out[a] = q[r.arm_control_idx[a]].numpy().astype(np.float64)
                return out
        return None

    # ---- primitives for the agent: deliberately thin wrappers of the low-level action (joint targets, gripper commands, a
    # straight-line base drive, IK moves) plus privileged state getters. Navigation, grasping, placing and every other skill
    # are the agent's to build.
    def primitives(self) -> dict[str, Callable]:
        th, s, r = self.th, self, self.robot
        idx = r.controller_action_idx
        parts = {"trunk": "trunk", "left": "arm_left", "right": "arm_right"}

        def _wrap(a: float) -> float:
            return (a + math.pi) % (2 * math.pi) - math.pi

        def _yaw(quat_xyzw) -> float:
            x, y, z, w = [float(v) for v in quat_xyzw]
            return math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))

        def _base_pose():
            pos, quat = r.get_position_orientation()
            return float(pos[0]), float(pos[1]), _yaw(quat)

        def _step(a) -> bool:
            terminated, truncated = s.step(a)
            return bool(terminated or truncated)

        def get_object_pose(name: str):
            """(position(3), quaternion_xyzw(4)) of a task object in the world frame."""
            pos, quat = s.get_object(name).get_position_orientation()
            return pos.cpu().numpy().astype(float), quat.cpu().numpy().astype(float)

        def get_object_bbox(name: str):
            """Axis-aligned bounding box (center(3), extent(3)) of a task object in the world frame."""
            obj = s.get_object(name)
            if hasattr(obj, "aabb_center") and hasattr(obj, "aabb_extent"):
                c, e = obj.aabb_center, obj.aabb_extent
            else:
                lo, hi = obj.aabb
                c, e = (lo + hi) / 2, hi - lo
            return th.as_tensor(c).cpu().numpy().astype(float), th.as_tensor(e).cpu().numpy().astype(float)

        def get_robot_pose():
            """(position(3), quaternion_xyzw(4)) of the robot base in the world frame."""
            pos, quat = r.get_position_orientation()
            return pos.cpu().numpy().astype(float), quat.cpu().numpy().astype(float)

        def get_eef_pose(arm: str | None = None):
            """(position(3), quaternion_xyzw(4)) of an end effector (default arm: left) in the world frame."""
            arm = arm or r.default_arm
            if hasattr(r, "get_eef_position") and hasattr(r, "get_eef_orientation"):
                pos, quat = r.get_eef_position(arm), r.get_eef_orientation(arm)
            else:
                pos, quat = r.eef_links[arm].get_position_orientation()
            return pos.cpu().numpy().astype(float), quat.cpu().numpy().astype(float)

        def object_in_hand(arm: str | None = None):
            """BDDL name of the object assisted grasping attaches to `arm`'s gripper (default arm), or None."""
            obj = (getattr(r, "_ag_obj_in_hand", None) or {}).get(arm or r.default_arm)
            return s._name_of(obj) if obj is not None else None

        def hold(steps: int = 10) -> int:
            """Keep the current targets for `steps` control steps (the base stands still). Returns control steps."""
            for i in range(int(steps)):
                if s.episode_done or _step(s.hold_action()):
                    return i
            return int(steps)

        def set_gripper(arm: str | None, open_: bool, steps: int = 15) -> int:
            """Command `arm`'s gripper (default arm) open (True) or closed (False) and hold `steps` control steps. Closing on
            an object attaches it (assisted grasping); opening releases it. The command stays until changed."""
            arm = arm or r.default_arm
            cmd = s._gripper_cmd(arm, bool(open_))
            for i in range(int(steps)):
                if s.episode_done:
                    return i
                a = s.hold_action(); a[idx[f"gripper_{arm}"]] = cmd.to(a.dtype)
                if _step(a):
                    return i + 1
            return int(steps)

        def open_gripper(arm: str | None = None, steps: int = 15) -> int:
            """set_gripper(arm, True, steps)."""
            return set_gripper(arm, True, steps)

        def close_gripper(arm: str | None = None, steps: int = 30) -> int:
            """set_gripper(arm, False, steps)."""
            return set_gripper(arm, False, steps)

        def move_joints(targets: dict, *, max_dq: float = 0.02, steps: int | None = None, settle: int = 0) -> int:
            """Interpolate joint targets linearly from the current ones: `targets` = {"trunk": q(4), "left": q(7), "right":
            q(7)} (any subset, rad), at most `max_dq` rad per control step (or exactly `steps` steps), then hold `settle`
            steps. The base and the grippers keep their commands. Returns control steps."""
            if s.episode_done or not targets:
                return 0
            a0 = s.hold_action()
            cur = {k: a0[idx[parts[k]]].clone() for k in targets}
            goal = {k: th.as_tensor(np.asarray(v, dtype=np.float32)).flatten().to(a0.dtype) for k, v in targets.items()}
            span = max(float(th.max(th.abs(goal[k] - cur[k]))) for k in targets)
            n = int(steps) if steps else max(2, int(math.ceil(span / max_dq)))
            for i in range(1, n + 1):
                a = s.hold_action()
                for k in targets:
                    a[idx[parts[k]]] = cur[k] + (goal[k] - cur[k]) * (i / n)
                if _step(a):
                    return i
            return n + hold(settle)

        def move_base(x: float, y: float, yaw: float, *, max_lin: float = 0.02, max_ang: float = 0.05, tol: float = 0.03,
                      tol_yaw: float = 0.05, max_steps: int = 2000) -> int:
            """Drive the base straight to the world pose (x, y, yaw[rad]): every control step a displacement of at most
            `max_lin` m and `max_ang` rad towards it (closed loop on the measured base pose), until within `tol` / `tol_yaw`
            or it stops making progress (blocked by something). No obstacle avoidance, no path planning: the base is a
            floating body that contact shoves around. Returns control steps."""
            n, best, stall = 0, float("inf"), 0
            while n < max_steps and not s.episode_done:
                cx, cy, cyaw = _base_pose()
                dx, dy, dyaw = x - cx, y - cy, _wrap(yaw - cyaw)
                d = math.hypot(dx, dy)
                if d < tol and abs(dyaw) < tol_yaw:
                    break
                prog = d + 0.3 * abs(dyaw)
                if prog < best - 1e-3:
                    best, stall = prog, 0
                else:
                    stall += 1
                    if stall > 60:
                        _log(f"move_base: no progress for 60 steps, {d:.2f} m / {dyaw:.2f} rad short (blocked?)")
                        break
                f = min(1.0, max_lin / max(d, 1e-9))
                tx, ty, tyaw = cx + f * dx, cy + f * dy, cyaw + max(-max_ang, min(max_ang, dyaw))
                # the virtual base joints live in the robot's spawn frame (and rz is unwrapped): target = current joints +
                # the world displacement rotated into that frame
                j = r.get_joint_positions()[r.base_control_idx]
                ryaw = _wrap(cyaw - float(j[2])); c, si = math.cos(ryaw), math.sin(ryaw)
                q = r.get_joint_positions().clone()
                q[r.base_control_idx] = th.tensor([float(j[0]) + c * (tx - cx) + si * (ty - cy), float(j[1]) - si * (tx - cx) + c * (ty - cy),
                                                   float(j[2]) + _wrap(tyaw - cyaw)], dtype=q.dtype)
                a = s.hold_action(); a[idx["base"]] = th.as_tensor(r.q_to_action(q)).flatten()[idx["base"]].to(a.dtype)
                n += 1
                if _step(a):
                    break
            return n

        def top_down_quat(yaw: float = 0.0):
            """End-effector orientation (xyzw) pointing straight down, rotated by `yaw` rad about the world z axis."""
            x, y, z, w = TOP_DOWN_XYZW
            cz, sz = math.cos(yaw / 2), math.sin(yaw / 2)
            return np.array([cz * x - sz * y, cz * y + sz * x, cz * z + sz * w, cz * w - sz * z], dtype=float)

        def move_ee(arm: str | None, pos, quat_xyzw=None, *, max_dq: float = 0.02, settle: int = 10) -> float:
            """Move `arm`'s end effector (default arm) to the world pose (pos, quat_xyzw; default: keep the current
            orientation): s.ik() (trunk + arm, no collision checking) then move_joints(). Raises PrimitiveError without an IK
            solution. Returns the final position error (m)."""
            arm = arm or r.default_arm
            if quat_xyzw is None:
                quat_xyzw = get_eef_pose(arm)[1]
            sol = s.ik({arm: (pos, quat_xyzw)})
            if sol is None:
                raise PrimitiveError(f"move_ee: no IK solution for the {arm} arm at {np.round(np.asarray(pos, dtype=float), 3).tolist()}")
            move_joints({"trunk": sol["trunk"], arm: sol[arm]}, max_dq=max_dq, settle=settle)
            return float(np.linalg.norm(get_eef_pose(arm)[0] - np.asarray(pos, dtype=float)))

        return {"get_object_pose": get_object_pose, "get_object_bbox": get_object_bbox, "get_robot_pose": get_robot_pose,
                "get_eef_pose": get_eef_pose, "object_in_hand": object_in_hand, "hold": hold, "set_gripper": set_gripper,
                "open_gripper": open_gripper, "close_gripper": close_gripper, "move_joints": move_joints, "move_base": move_base,
                "move_ee": move_ee, "ik": s.ik, "top_down_quat": top_down_quat}

    # ---- rendering (same API as the RoboTwin tasks' Session: render_frame / render_grid / render_video): the robot's own
    # cameras at the session's resolution, 224x224 with the default cameras="default" (the challenge's resolution) and
    # 16x16 with cameras="tiny" (cheaper rendering: it saved ~40% of the step time on the 16 GB laptop GPU, nothing
    # measurable on an RTX 4090 with the 8-thread cap). Rendering does not change the physics state.
    VIDEO_CAMERAS: tuple[str, ...] = ("robot_r1:zed_link:Camera:0", "robot_r1:left_realsense_link:Camera:0",
                                      "robot_r1:right_realsense_link:Camera:0")

    def _images(self) -> dict[str, np.ndarray]:
        out = {}
        obs = self.env.get_obs()
        obs = obs[0] if isinstance(obs, tuple) else obs

        def walk(node, path):
            if isinstance(node, dict):
                for k, v in node.items():
                    walk(v, f"{path}.{k}" if path else str(k))
                return
            if "rgb" in path.lower():
                a = np.asarray(node.cpu() if hasattr(node, "cpu") else node)
                if a.ndim == 3 and a.shape[-1] in (3, 4):
                    out[path.split(".")[-2] if "." in path else path] = np.ascontiguousarray(a[..., :3].astype(np.uint8))
        walk(obs, "")
        return out

    def render_frame(self, camera: str = "robot_r1:zed_link:Camera:0", size: tuple[int, int] | None = None) -> np.ndarray:
        """RGB (H, W, 3) uint8 of one robot camera for the current state (see VIDEO_CAMERAS); `size=(w, h)` resizes."""
        imgs = self._images()
        if camera not in imgs:
            raise KeyError(f"unknown camera {camera!r}; known: {sorted(imgs)}")
        img = imgs[camera]
        if size is not None and (img.shape[1], img.shape[0]) != tuple(size):
            import cv2
            img = cv2.resize(img, tuple(size), interpolation=cv2.INTER_LINEAR)
        return img

    def render_grid(self, cameras: tuple[str, ...] = VIDEO_CAMERAS, cols: int = 3, size: tuple[int, int] = (224, 224)) -> np.ndarray:
        """One image tiling `cameras` (row-major, `cols` per row; each resized to `size`)."""
        tiles = [self.render_frame(c, size=size) for c in cameras]
        while len(tiles) % cols:
            tiles.append(np.zeros_like(tiles[0]))
        return np.concatenate([np.concatenate(tiles[i:i + cols], axis=1) for i in range(0, len(tiles), cols)], axis=0)

    def render_video(self, actions: np.ndarray, path: str | Path, *, every: int = 3, fps: int = 10,
                     cameras: tuple[str, ...] = VIDEO_CAMERAS, cols: int = 3, size: tuple[int, int] = (224, 224)) -> dict[str, Any]:
        """Replay `actions` like replay() (from the loaded state if nothing stepped yet, else after reset()) and write an
        MP4 of `cameras` tiled, one frame every `every` control steps (+ `<path>.last.png`). Returns the final status plus
        n_frames and the video path. Use a Session with cameras="default" (the CLI `render` does)."""
        import imageio.v2 as imageio
        if self._stepped:
            self.reset()
        grab = lambda: self.render_grid(cameras, cols=cols, size=size)  # noqa: E731
        frames = [grab()]
        for i, a in enumerate(np.asarray(actions, dtype=np.float32)):
            terminated, truncated = self.step(a)
            if (i + 1) % every == 0 or terminated or truncated:
                frames.append(grab())
            if terminated or truncated:
                break
        path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
        with imageio.get_writer(str(path), fps=fps, format="FFMPEG", codec="libx264", macro_block_size=1) as w:
            for f in frames:
                w.append_data(f)
        imageio.imwrite(str(path.with_suffix(".last.png")), frames[-1])
        return {**self.status(), "n_frames": len(frames), "video": str(path)}

    # ---- rcb-limited/2.2 inputs, the same in both modes (the limited service imports this module): camera calibration and
    # mounting, depth, the robot's spec sheet, its measured state, stateless kinematics. Nothing here steps physics or
    # changes the simulator state: cameras and depth read what the renderer produced, kinematics is math on the robot model.
    TCP_FRAMES = {"left": "left_tcp", "right": "right_tcp"}

    def _cam_sensors(self) -> dict:
        return {n: s for n, s in self.robot.sensors.items() if hasattr(s, "image_height") and hasattr(s, "image_width")}

    @staticmethod
    def _cam_gl(sensor) -> np.ndarray:
        """Current world pose of a camera prim, OpenGL axes (x right, y up, z backward)."""
        pos, quat = sensor.get_position_orientation()
        return _T_of(_np(pos), _np(quat))

    @staticmethod
    def _cam_view(sensor) -> np.ndarray:
        """The pose (4x4, OpenGL axes) the camera's latest frame was rendered with: the renderer's own view matrix. Frames
        lag the physics by 2 control steps while the robot moves (measured), so this is the pose that matches the pixels
        and the depth; before the first render, the prim's current pose."""
        try:
            V = np.asarray(_np(sensor.camera_parameters["cameraViewTransform"]), dtype=np.float64).reshape(4, 4).T
            if np.any(V):
                return np.linalg.inv(V)
        except Exception:  # noqa: BLE001
            pass
        return Session._cam_gl(sensor)

    def _cam_fixed(self) -> dict:
        """Per robot camera, constant (cached): parent link, link_T_cam_cv, intrinsics, image size, clipping range."""
        if self._camfix is None:
            out = {}
            for n, s in self._cam_sensors().items():
                link = s.prim.GetParent().GetName()
                W, H = int(s.image_width), int(s.image_height)
                f = W * float(s.focal_length) / float(s.horizontal_aperture)      # square pixels, principal point at the centre
                T_link = _T_of(*[_np(x) for x in self.robot.links[link].get_position_orientation()])
                out[n] = {"parent_link": link, "link_T_cam_cv": np.round(np.linalg.inv(T_link) @ self._cam_gl(s) @ GL2CV, 6) + 0.0,
                          "K": [[f, 0.0, W / 2.0], [0.0, f, H / 2.0], [0.0, 0.0, 1.0]], "size": [W, H],
                          "clip": [float(v) for v in _np(s.clipping_range)]}
            self._camfix = out
        return self._camfix

    def camera_info(self, cameras=None) -> dict[str, dict]:
        """Per robot camera (default: all): intrinsic_cv (3x3), extrinsic_cv (3x4, world -> camera in OpenCV axes: x right,
        y down, z forward) and cam2world_gl (4x4 camera pose, OpenGL axes) of the latest rendered frame (the one
        render_frame / render_depth return: it lags the physics by 2 control steps while the robot moves), image_size [W, H],
        mount ({"type": "link", "parent_link", "link_T_cam_cv"}: world_T_cam = world_T_link @ link_T_cam_cv for any joint
        state) and moves (True: every robot camera rides on the robot). Plain lists. Reads, never steps."""
        fix, sens = self._cam_fixed(), self._cam_sensors()
        out = {}
        for n in (list(cameras) if cameras is not None else sorted(fix)):
            if n not in fix:
                raise KeyError(f"unknown camera {n!r}; known: {sorted(fix)}")
            G, f = self._cam_view(sens[n]), fix[n]
            out[n] = {"intrinsic_cv": [list(r) for r in f["K"]], "extrinsic_cv": np.linalg.inv(G @ GL2CV)[:3].tolist(), "cam2world_gl": G.tolist(),
                      "image_size": list(f["size"]), "mount": {"type": "link", "parent_link": f["parent_link"], "link_T_cam_cv": f["link_T_cam_cv"].tolist()},
                      "moves": True}
        return out

    def enable_depth(self, cameras=None) -> None:
        """From now on the robot cameras (default: all) also render z-depth (OmniGibson's "depth_linear", the 2026
        challenge's depth). Attaching it renders the current state a few times; rendering never steps physics."""
        sens = self._cam_sensors()
        new = [n for n in (list(cameras) if cameras is not None else sorted(sens)) if "depth_linear" not in sens[n].modalities]
        for n in new:
            sens[n].add_modality("depth_linear")
        for _ in range(10 if new else 0):                 # a new annotator has data after ~3 renders
            if all(np.asarray(_np(sens[n].get_obs()[0].get("depth_linear", np.zeros(0)))).size for n in new):
                break
            self.og.sim.render()

    def _frames(self, cameras, depth: bool = False) -> tuple[dict, dict]:
        """({cam: RGB uint8 (H, W, 3)}, {cam: z-depth float32 (H, W), 0 = no reading}) of the frame last rendered."""
        sens = self._cam_sensors()
        if depth:
            self.enable_depth(cameras)
        rgb, dep = {}, {}
        for n in cameras:
            obs = sens[n].get_obs()[0]
            rgb[n] = np.ascontiguousarray(_np(obs["rgb"])[..., :3].astype(np.uint8))
            if depth:
                dep[n] = _clean_depth(obs["depth_linear"])
        return rgb, dep

    def render_depth(self, camera: str = "robot_r1:zed_link:Camera:0") -> np.ndarray:
        """z-depth (H, W) float32 in metres of one robot camera for the current state: the distance from the camera plane
        along the optical axis, 0 = no reading; the same pixel grid as render_frame(camera) (without `size`)."""
        if camera not in self._cam_sensors():
            raise KeyError(f"unknown camera {camera!r}; known: {sorted(self._cam_sensors())}")
        return self._frames([camera], depth=True)[1][camera]

    def _kin(self) -> _Kin:
        """The kinematic model (built once, from the live articulation) and the frames kinematics() knows."""
        if self._kinm is None:
            r = self.robot
            names = list(r.joints)
            qn = [names[i] for i in r.trunk_control_idx.tolist()] + [names[i] for a in ("left", "right") for i in r.arm_control_idx[a].tolist()]
            k = _Kin(r, self.og.sim.stage, qn, r.base_footprint_link_name)
            self._kin_lo = np.array([float(r.joints[n].lower_limit) for n in qn])
            self._kin_hi = np.array([float(r.joints[n].upper_limit) for n in qn])
            self._kin_reset = np.array([float(_np(r.reset_joint_pos)[names.index(n)]) for n in qn])
            tip = {a: float(np.mean(list(r.eef_to_fingertip_lengths[a].values()))) for a in ("left", "right")}
            self._tcp = {self.TCP_FRAMES[a]: (r.eef_link_names[a], _T_of([0.0, 0.0, tip[a]], [0.0, 0.0, 0.0, 1.0])) for a in ("left", "right")}
            keep = [r.base_footprint_link_name, *r.trunk_link_names, *[l for a in ("left", "right") for l in r.arm_link_names[a]],
                    *[l for a in ("left", "right") for l in r.gripper_link_names[a]], *[r.eef_link_names[a] for a in ("left", "right")],
                    *[f["parent_link"] for f in self._cam_fixed().values()]]
            self._kin_frames = {**{l: (l, np.eye(4)) for l in dict.fromkeys(keep) if l in k.links}, **self._tcp}
            self._kinm = k
        return self._kinm

    def robot_spec(self) -> dict:
        """The robot's spec sheet (the standard mode's /spec "robot_spec"): its joints in the order of
        robot.get_joint_positions() (after the 6 virtual base joints) with the limits the simulator enforces and the
        manufacturer's rated velocity / effort, the grippers' stroke and open/close rule, the drive gains, the
        end-effector and fingertip-centre (TCP) frames, the mobile base."""
        from omnigibson.utils.constants import JointType
        r = self.robot; self._kin()
        names = list(r.joints); base = set(r.base_idx.tolist()); rated = self._rated_limits()
        joints, gains = [], {}
        for i, (n, j) in enumerate(r.joints.items()):
            if i in base:
                continue
            vel = float(_np(j._articulation_view.get_max_velocities(joint_indices=j.dof_indices))[0][0])
            eff = float(_np(j._articulation_view.get_max_efforts(joint_indices=j.dof_indices))[0][0])
            pris = j.joint_type == JointType.JOINT_PRISMATIC
            joints.append({"name": n, "type": "prismatic" if pris else "revolute", "unit": "m" if pris else "rad",
                           "position_limits": [float(j.lower_limit), float(j.upper_limit)],
                           "velocity_limit": vel if 0 < vel < 1e5 else None, "effort_limit": eff if 0 < eff < 1e10 else None, **rated.get(n, {}),
                           "group": next(g for g, idx in (("trunk", r.trunk_control_idx), ("left_arm", r.arm_control_idx["left"]),
                                                          ("right_arm", r.arm_control_idx["right"]), ("left_gripper", r.gripper_control_idx["left"]),
                                                          ("right_gripper", r.gripper_control_idx["right"])) if i in idx.tolist())})
            gains[n] = {"stiffness": float(j.stiffness), "damping": float(j.damping)}
        grip, tcp = {}, {}
        for a in ("left", "right"):
            fi = r.gripper_control_idx[a].tolist()
            lo, hi = float(r.joint_lower_limits[fi[0]]), float(r.joint_upper_limits[fi[0]])
            grip[a] = {"joints": [names[i] for i in fi], "opening_m": [round(2 * lo, 6), round(2 * hi, 6)],
                       "command": (f"joint_position gripper_{a}_0 and gripper_{a}_1: one target per finger, its travel in m ({lo:g} = "
                                   f"closed, {hi:g} = fully open; opening = the sum of the two). A finger commanded below {hi:g} closes: "
                                   "assisted grasping then holds an object the finger pads touch for 0.3 s, and lets it go only when both "
                                   f"fingers are commanded at or above {hi:g} again. The service's open command is {hi + 0.02:g} (the "
                                   "controller clips the drive target to the limit), so these action limits reach it. Switched at the row. "
                                   "ee_pose: gripper >= 0.5 = open (that open command), < 0.5 = closed (the lower limit)."),
                       "tcp_frame": self.TCP_FRAMES[a]}
            eef = r.eef_link_names[a]; link, off = self._tcp[self.TCP_FRAMES[a]]
            tcp[eef] = {"parent_link": eef, "link_T_frame": np.eye(4).tolist(),
                        "definition": f"the {a} end-effector frame ({eef}): the frame of the ee_pose action and of the proprio "
                                      f"{a}_eef_* pose; z along the fingers (approach), y along the finger travel; it lies between the "
                                      "finger pads, where assisted grasping holds objects"}
            tcp[self.TCP_FRAMES[a]] = {"parent_link": link, "link_T_frame": off.tolist(),
                                       "definition": f"the {a} fingertip centre (TCP): midway between the two fingertips, {off[2, 3] * 100:.2f} cm "
                                                     f"along +z of {eef}, same orientation; the proprio tcp_pose group"}
        bj = [names[i] for i in r.base_idx.tolist()]
        return {
            "name": "R1Pro",
            "description": "Galaxea R1 Pro as modelled in BEHAVIOR-1K 3.9.2: a holonomic wheeled base, a 4-joint trunk, two 7-joint "
                           "arms with parallel-jaw grippers (2 prismatic fingers each), a head camera on the trunk, a wrist camera per arm",
            "base": {"type": "mobile", "root_link": r.base_footprint_link_name,
                     "pose_proprio": ["base_x", "base_y", "base_z", "base_qx", "base_qy", "base_qz", "base_qw"],
                     "frame": f"{r.base_footprint_link_name}: x forward, y left, z up; the kinematics' base frame",
                     "joints": bj,
                     "command": "joint_position base_x, base_y, base_yaw: a displacement (m, m, rad) in the robot's own frame, applied at "
                                "EVERY control step (30 Hz) the row covers: the base controller moves the targets of the virtual joints "
                                f"{bj[0]}, {bj[1]}, {bj[5]} by it (their stiff drives follow within the step; {bj[2]}, {bj[3]}, {bj[4]} "
                                "are passive). Zeros stand still.",
                     "per_step_limits": {"x_m": 0.15, "y_m": 0.15, "yaw_rad": 0.3},
                     "velocity_limits": {"x_m_s": 4.5, "y_m_s": 4.5, "yaw_rad_s": 9.0,
                                         "note": "enforced: the per-step limits at 30 Hz (the virtual base joints themselves have no velocity "
                                                 "or effort limit; the stiff drives follow almost the whole step); no rated base speed is known"},
                     "note": "the 6 virtual joints are proprio columns (group base_joint_pos) relative to the robot's start frame; they "
                             "have no position limits"},
            "joints": joints,
            "grippers": grip,
            "controller": {"type": "joint position: every driven joint follows its target through a PhysX PD drive, effort = "
                                   "stiffness * (target - q) - damping * qdot, clipped at effort_limit",
                           "control_hz": 30, "physics_hz": 120, "gains": gains,
                           "note": "the virtual base joints x, y, rz use the same drive gains; targets hold for the 4 physics substeps "
                                   "of a control step; joint targets outside position_limits are clipped (reported in meta.clipped)"},
            "tcp": tcp,
        }

    def _rated_limits(self) -> dict:
        """{joint: {"rated_velocity", "rated_effort", "rated_source"}}: the <limit> velocity / effort of each joint in the
        R1 Pro's URDF exported from the manufacturer's CAD (r1pro_source.urdf next to robot.urdf_path in the licensed
        dataset), read at run time; {} when the file is absent."""
        import xml.etree.ElementTree as ET
        p = os.path.join(os.path.dirname(self.robot.urdf_path), "r1pro_source.urdf")
        out = {}
        try:
            for j in ET.parse(p).getroot().findall("joint"):
                lim, e = j.find("limit"), {}
                for k, a in (("rated_velocity", "velocity"), ("rated_effort", "effort")):
                    try:
                        v = float(lim.get(a)) if lim is not None and lim.get(a) is not None else 0.0
                    except ValueError:
                        v = 0.0
                    if v > 0:
                        e[k] = v
                if e:
                    out[j.get("name")] = {**e, "rated_source": "the <limit> of the R1 Pro URDF exported from the manufacturer's CAD "
                                                               "(BEHAVIOR dataset: omnigibson-robot-assets models/r1pro/urdf/r1pro_source.urdf)"}
        except (OSError, ET.ParseError) as exc:
            _log("robot_spec: no rated limits:", repr(exc)[:160])
        return out

    def robot_state(self) -> dict:
        """The robot's measured state: q / qd / effort (numpy, robot.joints order: 6 virtual base joints, trunk, arms
        interleaved left/right, fingers; effort = the drive effort PhysX measured), base_pose, and per arm eef (the ee_pose
        frame), tcp (fingertip centre) poses and gripper_opening (m). Poses: world frame, [x, y, z, qx, qy, qz, qw]."""
        r = self.robot; self._kin()
        q = _np(r.get_joint_positions()).astype(np.float64)
        out = {"q": q, "qd": _np(r.get_joint_velocities()).astype(np.float64), "effort": _np(r.get_joint_efforts()).astype(np.float64),
               "base_pose": np.concatenate([_np(x) for x in r.get_position_orientation()]).astype(np.float64), "eef": {}, "tcp": {}, "gripper_opening": {}}
        for a in ("left", "right"):
            Te = _T_of(*[_np(x) for x in r.eef_links[a].get_position_orientation()])
            out["eef"][a] = np.array(_pose7(Te))
            out["tcp"][a] = np.array(_pose7(Te @ self._tcp[self.TCP_FRAMES[a]][1]))
            out["gripper_opening"][a] = float(sum(q[i] for i in r.gripper_control_idx[a].tolist()))
        return out

    def kinematics_spec(self) -> dict:
        """What kinematics() answers (the standard mode's /spec "kinematics")."""
        r, k = self.robot, self._kin()
        eef = [r.eef_link_names[a] for a in ("left", "right")]; tcp = [self.TCP_FRAMES[a] for a in ("left", "right")]
        return {"endpoint": "/kinematics", "joint_names": list(k.q_names), "frame": "base",
                "base_pose_proprio": ["base_x", "base_y", "base_z", "base_qx", "base_qy", "base_qz", "base_qw"],
                "quaternion_order": "xyzw", "links": list(self._kin_frames), "tcp_frames": tcp, "ee_frames": eef, "ik_targets": eef + tcp,
                "ik": {"solver": "damped least squares from the seed (the targeted arms' joints first, then with the trunk), then "
                                 "cuRobo's multi-seed IK (the ee_pose action's solver) started from the seed, refined the same way",
                       "moves": "the trunk and the arm of each targeted frame; the other arm keeps its seed values",
                       "seed_default": "the robot's reset configuration", "tol_pos_m": KIN_TOL_POS_M, "tol_rot_rad": KIN_TOL_ROT_RAD,
                       "max_iters": KIN_MAX_ITERS, "collision_checking": "none", "joint_limits": "enforced"},
                "stateless": True,
                "note": "q = trunk + both arms (joint_names, all proprio columns of measured positions). Poses are in the base frame "
                        f"({r.base_footprint_link_name}, see robot_spec.base) unless the request gives base_pose (x y z qx qy qz qw: the "
                        "7 base proprio columns); then they are in the world frame. The model is the simulator's own articulation (its "
                        "joint frames), so FK of the measured joints gives the measured link poses."}

    def kinematics(self, req: dict) -> dict:
        """Stateless forward / inverse kinematics (the standard mode's /kinematics answer):
          {"op": "fk", "q": [18], "links"?: [...], "base_pose"?: [7]} -> {"ok": True, "op": "fk", "frame", "poses": {frame: [x,y,z, qx,qy,qz,qw]}}
          {"op": "ik", "targets": {frame: [7]}, "seed"?: [18], "base_pose"?, "tol_pos_m"?, "tol_rot_rad"?, "max_iters"?}
              -> {"ok", "op": "ik", "frame", "q": [18], "error": {frame: {"pos_m", "rot_rad"}}}
        q follows kinematics_spec()["joint_names"]; frames kinematics_spec()["links"]; poses in the base frame, or the world
        frame when base_pose is given. The robot's current state plays no part; nothing is stepped."""
        k = self._kin(); n = len(k.q_names); spec = self.kinematics_spec()

        def vec(x, m, what):
            a = np.asarray(x, dtype=np.float64).reshape(-1) if x is not None else None
            if a is None or a.size != m or not np.all(np.isfinite(a)):
                raise ValueError(f"{what} must be {m} finite numbers")
            return a

        def pose(x, what):
            p = vec(x, 7, what); nq = float(np.linalg.norm(p[3:]))
            if nq < 1e-6:
                raise ValueError(f"{what}: quaternion has zero norm")
            return _T_of(p[:3], p[3:] / nq)
        Tw = pose(req["base_pose"], "base_pose") if req.get("base_pose") is not None else None
        frame = "world" if Tw is not None else "base"
        if req.get("op") == "fk":
            q = vec(req.get("q"), n, "q"); links = req.get("links") or list(self._kin_frames)
            bad = [l for l in links if l not in self._kin_frames]
            if bad:
                raise ValueError(f"unknown links {bad}; known: {list(self._kin_frames)}")
            T = k.fk(q); pre = Tw if Tw is not None else np.eye(4)
            return {"ok": True, "op": "fk", "frame": frame, "poses": {l: _pose7(pre @ T[self._kin_frames[l][0]] @ self._kin_frames[l][1]) for l in links}}
        if req.get("op") != "ik":
            raise ValueError("op must be 'fk' or 'ik'")
        tg = req.get("targets")
        if not isinstance(tg, dict) or not tg or any(f not in spec["ik_targets"] for f in tg):
            raise ValueError(f"targets must map frames from {spec['ik_targets']} to poses")
        tol_p = float(req.get("tol_pos_m") or KIN_TOL_POS_M); tol_r = float(req.get("tol_rot_rad") or KIN_TOL_ROT_RAD)
        iters = int(req.get("max_iters") or KIN_MAX_ITERS)
        seed = self._kin_reset.copy() if req.get("seed") is None else np.clip(vec(req["seed"], n, "seed"), self._kin_lo, self._kin_hi)
        inv = np.linalg.inv(Tw) if Tw is not None else np.eye(4)
        targets = {f: (self._kin_frames[f][0], self._kin_frames[f][1], inv @ pose(p, f"targets[{f}]")) for f, p in tg.items()}
        trunk = list(range(4))
        arms = sorted({k.qi[j] for f in targets for j in k.chain[targets[f][0]]} - set(trunk))
        lo, hi = self._kin_lo, self._kin_hi

        def score(e):
            return sum(p + 0.3 * r_ for p, r_ in e.values())
        best = None
        for cols in (arms, trunk + arms):
            q, err, ok = k.solve(targets, seed, cols, lo, hi, tol_p, tol_r, iters)
            if best is None or ok or score(err) < score(best[1]):
                best = (q, err, ok)
            if ok:
                break
        if not best[2]:
            try:
                q0 = self._curobo_ik(targets, seed)
                if q0 is not None:
                    q, err, ok = k.solve(targets, q0, trunk + arms, lo, hi, tol_p, tol_r, iters)
                    if ok or score(err) < score(best[1]):
                        best = (q, err, ok)
            except Exception as exc:  # noqa: BLE001
                _log("kinematics: cuRobo IK fallback failed:", repr(exc)[:200])
        q, err, ok = best
        q = q.copy(); rest = [i for i in range(n) if i not in trunk + arms]
        q[rest] = seed[rest]
        return {"ok": bool(ok), "op": "ik", "frame": frame, "q": [float(v) for v in q],
                "error": {f: {"pos_m": float(e[0]), "rot_rad": float(e[1])} for f, e in err.items()}}

    def _curobo_ik(self, targets: dict, seed) -> np.ndarray | None:
        """cuRobo's multi-seed IK (the ee_pose action's solver) for the targets (base frame), started from `seed` (the
        virtual base joints at 0, so cuRobo's root frame is the base frame); its seed sampler restarts every call.
        Returns q in kinematics order, or None."""
        from omnigibson.action_primitives.curobo import CuRoboEmbodimentSelection as Emb
        th, r, mg, k = self.th, self.robot, self._curobo(), self._kinm
        names = list(r.joints)
        q_full = th.zeros(len(names), dtype=th.float32)
        for i, nm in enumerate(k.q_names):
            q_full[names.index(nm)] = float(seed[i])
        for a in ("left", "right"):
            for i in r.gripper_control_idx[a].tolist():
                q_full[i] = float(r.joint_upper_limits[i])
        tp, tq = {}, {}
        for link, off, Tt in targets.values():
            Te = Tt @ np.linalg.inv(off)
            tp[link] = th.as_tensor(Te[:3, 3], dtype=th.float32).reshape(1, 3)
            tq[link] = th.as_tensor(_xyzw_of_R(Te[:3, :3]), dtype=th.float32).reshape(1, 4)
        mg.mg[Emb.ARM].ik_solver.reset_seed()
        succ, js = mg.compute_trajectories(target_pos=tp, target_quat=tq, initial_joint_pos=q_full, is_local=True, max_attempts=1, timeout=30.0,
                                           ik_fail_return=5, enable_finetune_trajopt=False, finetune_attempts=0, return_full_result=False,
                                           success_ratio=1.0, ik_only=True, ik_world_collision_check=False, skip_obstacle_update=True, emb_sel=Emb.ARM)
        if not js or js[0] is None:
            return None
        q = mg.path_to_joint_trajectory(js[0], get_full_js=False, emb_sel=Emb.ARM).cpu()
        q = q.reshape(-1, q.shape[-1])[-1].numpy()
        return np.array([float(q[names.index(nm)]) for nm in k.q_names])

    def exec_code(self, code: str, extra: dict | None = None) -> dict[str, Any]:
        """Run agent/oracle code with the primitives and this session in scope (like cap-x's executor)."""
        g: dict[str, Any] = {"__name__": "__main__", "np": np, "math": math, "th": self.th, "session": self, "s": self,
                             "objects": self.objects, "TASK": self.spec, "PrimitiveError": PrimitiveError,
                             "TOP_DOWN_XYZW": TOP_DOWN_XYZW, **self.primitives(), **(extra or {})}
        try:
            exec(code, g, g)  # noqa: S102
            return {"ok": True}
        except BaseException as exc:  # noqa: BLE001
            import traceback
            return {"ok": False, "error": repr(exc)[:400], "traceback": traceback.format_exc()[-2000:]}

    def _log_end(self) -> None:
        if not self._end_logged:           # og.shutdown() ends the process before atexit handlers run
            self._end_logged = True
            _slog("session_end", task=self.task, resets=self._resets, sim_steps=self._total_steps + int(self.env.episode_steps))

    def close(self) -> None:
        """Shuts Isaac Sim down. NOTE: og.shutdown() terminates the process; write all outputs before calling this."""
        self._log_end()
        try:
            self.ev.__exit__(None, None, None)
        except Exception:  # noqa: BLE001
            pass


# --------------------------------------------------------------------------- CLI
def _load_traj(path: str) -> dict[str, Any]:
    d = np.load(path, allow_pickle=False)
    return {k: (d[k].item() if d[k].shape == () else d[k]) for k in d.files}


def cmd_make_instance(a) -> None:
    s = Session(a.task, instance_id=a.instance_id, mode=a.mode, robot_config=a.robot_config)
    out = {"task": a.task, "challenge_task": s.spec["challenge_task"], "instance_id": s.instance_id, "mode": s.mode, "text": s.spec["text"],
           "robot_config": s.robot_config_path.name, "robot_config_sha": s.robot_config_sha,
           "state_sha": s.instance_sha, "action_dim": s.action_dim, "challenge_max_steps": s.challenge_max_steps,
           "objects": s.objects(), "omnigibson_version": __import__("omnigibson").__version__}
    Path(a.out).write_text(json.dumps(out, indent=1))
    # the goal must not hold before the agent has done anything
    print(json.dumps({"instance": a.out, "state_sha": s.instance_sha, "action_dim": s.action_dim, "initial_status": s.status()}), flush=True)
    s.close()


def cmd_run_oracle(a) -> None:
    """Run the reference code on the frozen instance in this fresh process and record every low-level action."""
    s = Session(a.task, instance=a.instance, strict=True)
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
    s = Session(a.task, instance=a.instance, cameras="default" if a.video else "tiny", strict=a.strict)
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
    s = Session(a.task, instance=a.instance, cameras="default")
    cams = tuple(a.cameras.split(",")) if a.cameras else Session.VIDEO_CAMERAS
    out = s.render_video(_load_traj(a.traj)["actions"], a.out, every=a.every, fps=a.fps, cameras=cams, cols=a.cols)
    print(json.dumps(out), flush=True)
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
    r0 = run("make-instance", "--task", a.task, "--instance-id", a.instance_id, "--robot-config", a.robot_config, "--out", inst)
    r1 = run("run-oracle", "--task", a.task, "--instance", inst, "--code", a.code, "--out", traj)
    r2 = run("replay", "--task", a.task, "--instance", inst, "--traj", traj, "--strict")
    r3 = run("replay", "--task", a.task, "--instance", inst, "--traj", traj, "--strict")
    sha = [((r.get("replays") or [{}])[0]).get("state_sha") for r in (r2, r3)]
    ok = bool(r1.get("success")) and bool(r2.get("all_success")) and bool(r3.get("all_success")) and sha[0] == sha[1] \
        and bool(r2.get("instance_matches")) and bool(r3.get("instance_matches"))
    print(json.dumps({"make_instance": r0, "oracle": r1, "replay_1": r2, "replay_2": r3, "live_equals_replay": sha[0] == r1.get("state_sha"), "PASS": ok}, indent=1), flush=True)
    sys.exit(0 if ok else 1)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("make-instance"); q.add_argument("--task", required=True); q.add_argument("--instance-id", type=int, required=True)
    q.add_argument("--mode", default="public_test"); q.add_argument("--robot-config", default=None); q.add_argument("--out", required=True); q.set_defaults(fn=cmd_make_instance)
    q = sub.add_parser("run-oracle"); q.add_argument("--task", required=True); q.add_argument("--instance", required=True)
    q.add_argument("--code", required=True); q.add_argument("--out", required=True); q.set_defaults(fn=cmd_run_oracle)
    q = sub.add_parser("replay"); q.add_argument("--task", required=True); q.add_argument("--instance", required=True); q.add_argument("--traj", required=True)
    q.add_argument("--repeat", type=int, default=1, help="in-process repeats; only the first is fresh-process exact")
    q.add_argument("--video", default=None); q.add_argument("--fps", type=int, default=30)
    q.add_argument("--strict", action="store_true", help="fail if the instance state sha differs from instance.json"); q.set_defaults(fn=cmd_replay)
    q = sub.add_parser("render"); q.add_argument("--task", required=True); q.add_argument("--instance", required=True); q.add_argument("--traj", required=True)
    q.add_argument("--out", required=True); q.add_argument("--every", type=int, default=3); q.add_argument("--fps", type=int, default=10)
    q.add_argument("--cameras", default=None); q.add_argument("--cols", type=int, default=3); q.set_defaults(fn=cmd_render)
    q = sub.add_parser("selftest"); q.add_argument("--task", default="picking_up_trash"); q.add_argument("--instance-id", type=int, default=301); q.add_argument("--code", required=True); q.add_argument("--robot-config", default=str(Path(__file__).parent / "r1pro_primitives_eval.yaml")); q.add_argument("--out-dir", required=True); q.set_defaults(fn=cmd_selftest)
    a = p.parse_args(); a.fn(a)


if __name__ == "__main__":
    main()
