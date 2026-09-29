# KinDER

Physical reasoning for robot planning and control, kept apart from perception and language: tool use, non-prehensile
multi-object manipulation, geometric and dynamic constraints.

| | |
|---|---|
| upstream | [KinDER](https://github.com/Princeton-Robot-Planning-and-Learning/kindergarden) (RSS 2026, [arXiv 2604.25788](https://arxiv.org/abs/2604.25788)), MIT, pinned at `5b2dbac` |
| simulator | our tasks: MuJoCo 3.3 (Dynamic3D) in KinDER's MimicLabs lab (textured floor, walls, furniture), CPU; upstream also has Pymunk 2D and PyBullet 3D families |
| robot | TidyBot++: holonomic base, Kinova Gen3 7-DoF arm, Robotiq 2F-85 gripper; 10 Hz delta actions |
| score | pass = KinDER's own goal check (an object's centre inside a goal region, and the like) within 1000 steps |
| image | `ghcr.io/jameskrw/rcb-kinder:0.1.6` (`images/kinder/`) |

Kinematic families are near-solved upstream; on the dynamic ones the paper's best methods stay low
(DynPushPullHook2D-o5 ≤ 0.43, SweepIntoDrawer3D-o5 ≤ 0.14; sampling MPC on the true simulator 0.00 on both).

## Why add it, next to what we have

| our benchmarks | what they test | what KinDER adds |
|---|---|---|
| LIBERO-PRO, Meta-World+, VLABench, RoboLab, RoboTwin 2.0, RoboCasa / RoboCasa365 / RoboCasa-GR1 | tabletop and kitchen skills: language, robustness, bimanual coordination | little to read or recognise: the physics is the difficulty |
| BEHAVIOR-1K | long household activities | one physical problem per task, each a few minutes of robot time |
| HumanoidBench, MuJoCo Playground | body control: gaits, balance, whole-body motion | a mobile manipulator; the objects' dynamics, not the robot's |
| DexToolBench | tool use inside a dexterous hand | arm-level tools (scoop, wiper) and pushing, throwing, balancing |
| RoboWits, TopoGym (ours) | hand-made creative puzzles; geometric constraints | overlaps on balance and packing; adds dynamics (throw, scoop, sweep) and a difficulty knob per family |

## Tasks: upstream's 31 families (123 variants), ours ✅ (one variant each, seed 0)

| family (variants) | challenge | ours | the robot must / why not | Luna full · limited |
|---|---|---|---|---|
| Tossing3D (2) | dynamic | ✅ o1 | get a cube from the floor into a bin beyond a low wall that spans the room | ✅ · ❌ |
| BalanceBeam3D (1) | tool, dynamic | ✅ o3 | put three cubes on a seesaw's marked region and leave it within 5° of level | ✅ · ✅ |
| Dynamo3D (3) | nonprehensile | ✅ o3 | drive into a floor square that three chairs block (fixture, the pipeline check) | ✅ · ✅ |
| SweepIntoDrawer3D (1) | nonprehensile, tool, dynamic | ✅ o5 | open a drawer, then get five small cubes from the counter into it (a wiper is there) | ❌ · ✅ |
| ScoopPour3D (6) | nonprehensile, tool, dynamic | ✅ o30 | move 30 small cubes from one bin to another (a scoop is there) | ❌ · ❌ |
| Shelf3D (6) | spatial, geometric | ✅ o2 | put two cubes from the floor in a cramped cupboard's top compartment | ✅ · ❌ |
| ConstrainedCupboard3D (6) | geometric | ⬜ | identical rods, each owed to one of six cupboards (limited names them by distance and place in the row) | o6: ✅ · ❌ |
| Rearrange3D (10) | spatial | ⬜ | left or right of the bowl, in the bowl's own frame (it starts along the island, so a sentence can name it) | o2: ✅ · ✅ |
| SweepSimple3D (6) | nonprehensile, tool | ⬜ | sweeping blocks to one side: SweepIntoDrawer3D asks for more | o10: ❌ · ❌ |
| SortClutteredBlocks3D (4) | spatial | ⬜ | sorting blocks by colour: repeated pick-and-place | o4 bins: ✅ · ❌ |
| PickPlace3D (1), FrankaPickPlace3D (1) | — | ⬜ | plain pick-and-place | ✅, ✅ · ✅, ✅ |
| LimbRepositioning3D (16) | — | ⬜ | an arm welded to a human limb, torque control: another robot interface | not run: its IKFast cannot build in our image |
| Kinematic3D, PyBullet (8): BaseMotion3D, Obstruction3D, Table3D, Transport3D, Packing3D, KinematicShelf3D, KinematicCylinderShelf3D, PrplLab3D | spatial, tool, geometric | ⬜ | kinematic: near-solved | 8/8 ✅ · 6/8 ✅ |
| Dynamic2D, Pymunk (4): DynObstruction2D, DynPushPullHook2D, DynPushT2D, DynScoopPour2D | all five | ⬜ | 2D: a camera image is nearly the state | 4/4 ✅ · — |
| Kinematic2D (6): Motion2D, StickButton2D, Obstruction2D, ClutteredRetrieval2D, ClutteredStorage2D, PushPullHook2D | spatial, tool, geometric | ⬜ | 2D and kinematic | 6/6 ✅ · — |

`oN` = the variant's number of objects (Dynamo3D: obstacle chairs); variants differ only in that count. Challenge: the
paper's five, as its Fig. 3 marks each environment (spatial relations, nonprehensile multi-object manipulation, tool
use, combinatorial geometric constraints, dynamic constraints; a grouped row lists its families' union; —: added after
the paper). Our six cover all five.

Luna: GPT-6 Luna, one standard run per mode (09-29). The rows without ✅ were screened once to find hard tasks, at the
variant named there (the hardest upstream's baselines configure, else the hardest with at most 10 objects; the grouped
rows: `scripts/kinder/subset.toml`, Screening). Kinematic families pass in minutes in full mode, some by releasing
objects in mid-air; the hard ones are SweepSimple3D (0/10 cubes, both modes), SortClutteredBlocks3D and
ConstrainedCupboard3D (limited fails, full passes at the step or time limit), and in limited mode Obstruction3D and
Packing3D. Analyses: `results/kinder/analysis/`.

Why: physics decides the outcome (Dynamic3D, MuJoCo, TidyBot++), and a camera can see the goal or a sentence can name
it, so limited mode is fair. Source: `scripts/kinder/subset.toml`.

## Modes (standard config: Codex via OpenRouter, effort medium, 60 min)

| mode | the agent gets | resets | delivers |
|---|---|---|---|---|
| limited | the robot's own sensors, below; no goal check | 50 | the graded episodes themselves |
| full | the simulator with state access (`get_state`/`set_state`) and the goal check, offline | unlimited | one replayable trajectory |

Limited mode, what the agent can and cannot access:

| given (a real robot has it) | not given |
|---|---|
| the task sentence: goal and success condition | any object's or goal region's position |
| `robot_base` RGB, `robot_wrist` RGB-D (the Gen3's RealSense D410), 480×640: to see further, turn the base or raise the wrist | world coordinates: odometry starts at the robot's start pose; a room camera (a knob for control runs, never overhead) |
| base odometry (pose, velocity), arm joint angles and velocities, finger position | the goal check before the episode ends (only `success`/`failed`) |
| `spec()`: action layout and bounds, arm joint axes, positions, limits and torques, camera fields of view and poses, 10 Hz, 1000 steps, reset budget | masses, friction, the simulator itself |

The table is the TidyBot++'s. The screening's other robots get the same kind of sensors: the desk-mounted Franka its
wrist camera (RGB-D; the model has none, so it is TidyBot++'s, mounted the same way on the same gripper) and joint
encoders, with an unmarked goal given in its base frame; the PyBullet robot TidyBot++'s two cameras on the same links,
odometry, joint angles and finger position (kinematic: no velocities). The 2D tasks have no limited twin: a map of the
scene would be their only sensor.

## Run

```bash
sg docker -c 'RCB_MODEL=openrouter/openai/gpt-6-luna scripts/run_deepseek_openrouter.sh tasks/kinder-tossing-i00-limited \
  -c scripts/kinder/configs/limited.yaml --ak reasoning_effort=medium'
sg docker -c 'RCB_MODEL=openrouter/openai/gpt-6-luna scripts/run_deepseek_openrouter.sh tasks/kinder-tossing-i00 \
  --ak reasoning_effort=medium'
python3 scripts/results/build.py --add jobs/<job>     # log the run, rebuild the results pages
```

## Latest results (GPT-6 Luna, 09-29; pass / scored tasks)

| limited | full |
|---|---|
| 2/5 (sweep-into-drawer, balance-beam) | 3/5 (tossing, balance-beam, shelf) |

- limited, with only the robot's own cameras, has to look for things (turn the base, raise the wrist camera); wrist depth
  gets the heights right. What still costs most is grasping: `spec()` has no gripper pinch point, so each run finds it
  by trial. The fixture dynamo passes both modes.
- full passes read the state and the goal check and do IK on the model's pinch site; the two multi-step contact tasks
  fail in full mode, and one of them (sweep-into-drawer) passed in limited with a better grasp strategy.
- The earlier limited setup (white floor, room camera, no depth) scored 0/5; full ran on the white floor, which changes
  only its images.

Per task: `results/kinder/README.md`; analysis: `results/kinder/analysis/overview.md`; limited protocol:
`docs/LIMITED_MODE_1_1.md`.
