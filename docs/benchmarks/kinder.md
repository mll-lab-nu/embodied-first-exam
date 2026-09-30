# KinDER

Physical reasoning for robot planning and control, kept apart from perception and language: tool use, non-prehensile
multi-object manipulation, geometric and dynamic constraints.

| | |
|---|---|
| upstream | [KinDER](https://github.com/Princeton-Robot-Planning-and-Learning/kindergarden) (RSS 2026, [arXiv 2604.25788](https://arxiv.org/abs/2604.25788)), MIT, pinned at `5b2dbac` |
| simulator | MuJoCo 3.3 (Dynamic3D) in KinDER's MimicLabs lab (textured floor, walls, furniture), CPU; two tasks in PyBullet (Kinematic3D: no dynamics, a colliding move is refused); upstream also has Pymunk 2D families |
| robot | TidyBot++: holonomic base, Kinova Gen3 7-DoF arm, Robotiq 2F-85 gripper; delta actions (MuJoCo: 10 Hz) |
| score | pass = KinDER's own goal check (an object's centre inside a goal region, and the like) within the episode (1000 steps; PyBullet 3000) |
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
| BalanceBeam3D (1) | tool, dynamic | ✅ o3 | put three cubes on a seesaw's marked region and leave it within 5° of level | ✅ · ❌ |
| Dynamo3D (3) | nonprehensile | ✅ o3 | drive into a floor square that three chairs block (fixture, the pipeline check) | ✅ · ✅ |
| SweepIntoDrawer3D (1) | nonprehensile, tool, dynamic | ✅ o5 | open a drawer, then get five small cubes from the counter into it (a wiper is there) | ❌ · ❌ |
| ScoopPour3D (6) | nonprehensile, tool, dynamic | ✅ o30 | move 30 small cubes from one bin to another (a scoop is there) | ❌ · ❌ |
| Shelf3D (6) | spatial, geometric | ✅ o2 | put two cubes from the floor in a cramped cupboard's top compartment | ✅ · ❌ |
| ConstrainedCupboard3D (6) | geometric | ✅ o6 | put six identical rods into six narrow cupboards, each rod into the one it is owed (limited names them by distance and place in the row) | ✅ · ❌ |
| SweepSimple3D (6) | nonprehensile, tool | ✅ o10 | get ten small cubes on the floor into a box marked at the kitchen island's end (a wiper is there) | ❌ · ✅ |
| SortClutteredBlocks3D (4) | spatial | ✅ o4 bins | sort four clustered cubes into the four bins of their colours | ✅ · ✅ |
| Obstruction3D (5), PyBullet | geometric | ✅ o4 | clear three blocks off a pad, then place a block on it | ✅ · ❌ |
| Packing3D (3), PyBullet | geometric | ✅ p3 | pack three flat parts into a tray, flat and without overlap | ✅ · ✅ |
| Rearrange3D (10) | spatial | ⬜ | o2: passes both modes | ✅ · ✅ |
| PickPlace3D (1), FrankaPickPlace3D (1) | — | ⬜ | plain pick-and-place: passes both modes | ✅, ✅ · ✅, ✅ |
| LimbRepositioning3D (16) | — | ⬜ | an arm welded to a human limb, torque control: another robot interface; its IKFast cannot build in our image | not run |
| Kinematic3D, PyBullet (6): BaseMotion3D, Table3D, Transport3D, KinematicShelf3D, KinematicCylinderShelf3D, PrplLab3D | spatial, tool, geometric | ⬜ | kinematic: pass in minutes, some by releasing objects in mid-air | 6/6 ✅ · 6/6 ✅ |
| Dynamic2D, Pymunk (4): DynObstruction2D, DynPushPullHook2D, DynPushT2D, DynScoopPour2D | all five | ⬜ | 2D: a camera image is nearly the state, so no limited mode | 4/4 ✅ · — |
| Kinematic2D (6): Motion2D, StickButton2D, Obstruction2D, ClutteredRetrieval2D, ClutteredStorage2D, PushPullHook2D | spatial, tool, geometric | ⬜ | 2D and kinematic | 6/6 ✅ · — |

`oN` = the variant's number of objects (Dynamo3D: obstacle chairs; Packing3D `pN`: parts); variants differ only in that
count. Challenge: the paper's five, as its Fig. 3 marks each environment (spatial relations, nonprehensile multi-object
manipulation, tool use, combinatorial geometric constraints, dynamic constraints; a grouped row lists its families'
union; —: added after the paper). Ours cover all five.

Why these: the first six are the Dynamic3D tasks where physics decides the outcome and a camera can see the goal or a
sentence can name it, so limited mode is fair. The other five come from a screening of every other family (09-29, GPT-6
Luna once per mode, at the variant named: the hardest upstream's baselines configure, else the hardest with at most 10
objects): the ones it failed in limited mode. The ⬜ rows are that screening's results; they left the benchmark.
Source: `scripts/kinder/subset.toml`; analyses: `results/kinder/analysis/`.

## Modes (standard config: Codex via OpenRouter, effort medium, 60 min)

| mode | the agent gets | resets | delivers |
|---|---|---|---|
| limited | the robot's own sensors, below; no goal check | 50: explore in earlier episodes, the graded one executes | the graded episode itself |
| full | the simulator with state access (`get_state`/`set_state`) and the goal check, offline | unlimited | one replayable trajectory |

Limited mode, what the agent can and cannot access:

| given (a real robot has it) | not given |
|---|---|
| the task sentence: goal and success condition | any object's or goal region's position |
| `robot_base` RGB, `robot_wrist` RGB-D (the Gen3's RealSense D410), 480×640: to see further, turn the base or raise the wrist | world coordinates: odometry starts at the robot's start pose; a room camera (a knob for control runs, never overhead) |
| base odometry (pose, velocity), arm joint angles and velocities, finger position | the goal check before the episode ends (only `success`/`failed`) |
| `spec()`: action layout and bounds, arm joint axes, positions, limits and torques, the gripper's grasp point (`end_effector`), camera fields of view and poses, control rate, episode length, reset budget | masses, friction, the simulator itself |

The table is the MuJoCo TidyBot++'s. In Obstruction3D and Packing3D (PyBullet) the robot is the same one, kinematic:
TidyBot++'s two cameras on the same links, odometry, joint angles and finger position (no velocities); `spec()` states
its grasp, release and collision rules, and a move it refuses comes back `blocked` and stops a batch there, as a real
controller stops its queue.

## Run

```bash
sg docker -c 'RCB_MODEL=openrouter/openai/gpt-6-luna scripts/run_deepseek_openrouter.sh tasks/kinder-tossing-i00-limited \
  -c scripts/kinder/configs/limited.yaml --ak reasoning_effort=medium'   # 50 resets, wrist depth
sg docker -c 'RCB_MODEL=openrouter/openai/gpt-6-luna scripts/run_deepseek_openrouter.sh tasks/kinder-tossing-i00 \
  --ak reasoning_effort=medium'
python3 scripts/results/build.py --add jobs/<job>     # log the run, rebuild the results pages
```

## Latest results (GPT-6 Luna, 09-30; pass / scored tasks)

| limited (50 resets) | full | limited without resets (control) |
|---|---|---|
| 3/10 (sweep-simple, sort-blocks, packing-3d) | 7/10 | 0/10 |

- Why 50 resets: KinDER's episode (1000 steps, 100 s of robot time; PyBullet 3000) is the time to carry the task out
  with the whole state known. Limited mode has to find things and calibrate first, which gets earlier episodes; the
  graded one is the execution. Without resets both share one episode, and the nine MuJoCo runs ran out of its 1000 steps
  after 6–46 min (the full-mode passes alone take 574–1000).
- The limited passes calibrated over earlier episodes and then replayed a script (sweep-simple, sort-blocks) or packed
  the tray live in its first episode (packing-3d). A reset restores the scene bit for bit, which a lab cannot; that
  makes replaying a calibrated script possible, as in HumanoidBench.
- Full mode passes by reading the state and the goal check and planning offline; it fails on the two multi-step contact
  tasks (sweep-into-drawer, scoop-pour) and on sweep-simple.

Per task: `results/kinder/README.md`; analysis: `results/kinder/analysis/overview.md`; limited protocol:
`docs/LIMITED_MODE_1_1.md`.
