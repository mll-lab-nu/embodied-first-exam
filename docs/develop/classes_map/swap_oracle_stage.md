# Swap Oracle Stage

This note records the first runnable Swap milestone: build a simple Swap scene
and let Franka execute a scripted standard-answer path.

## Goal

The stage is not RL yet. It checks that the physical scene, robot controller,
and a task-specific oracle can work together:

```text
build Swap scene
reset Franka home
pick green block at slot 4
place it into empty slot 3
return home
check success
```

## Reusable Classes

### `EntityManifest`

File: `topogym/core/manifest.py`

Small registry from names to Genesis handles. Other modules can ask for
`"robot"`, `"block_red"`, `"slot_3"`, etc. without passing many handles around.

Reusable across all tasks.

### `FrankaPositionIKController`

File: `topogym/robot/franka.py`

Powers the Franka arm:

- sets PD gains and force limits
- resets to home qpos
- opens and closes the gripper
- moves the end effector to a target pose with Genesis IK

This is the first concrete version of the C/Embodiment layer.

### `PickPlacePrimitive`

File: `topogym/primitives/pick_place.py`

Runs a scripted pick-place sequence:

```text
open gripper
move above source
descend
close gripper
lift
move above target
descend
open gripper
retract
```

This primitive is reusable for Swap and later tabletop tasks. It runs on pure
physics: the block only moves when the gripper actually grips it via real
contact and friction. No teleport/set_pos shortcuts.

## Swap-Specific Classes

### `SwapLayout`

File: `topogym/tasks/legacy/swap.py`

Reads slot and block coordinates from `configs/task_configs/swap.yaml`.
It answers questions such as:

- where is slot 0?
- where should `block_red` sit in slot 3?
- which block does the oracle move?

### `SwapSceneBuilder`

File: `topogym/tasks/legacy/swap.py`

Builds the table, stage, robot, slot markers, and colored blocks. It returns a
`SwapScene` containing:

```text
scene
manifest
layout
```

### `SwapOraclePlan`

File: `topogym/tasks/legacy/swap.py`

The standard answer for the smoke task. It moves `block_red` from source slot 0
to target slot 3 using `PickPlacePrimitive`, then returns the robot home.

### `SwapSuccessChecker`

File: `topogym/tasks/legacy/swap.py`

First simple success check: the moved block center must be close to the target
slot center in x/y.

## Configs

```text
configs/env_configs/common_room.yaml
configs/robot_control_configs/franka_panda_position_ik.yaml
configs/task_configs/swap.yaml
```

The task config owns Swap-specific details: slot positions, block colors, source
slot, target slot, and primitive heights.

## Runnable Prototype

```bash
python -m prototypes.swap_empty_slot_demo
python -m prototypes.swap_empty_slot_demo --viewer --keep-open
python -m prototypes.swap_physical_grasp_demo --viewer --keep-open --verbose
```

`swap_empty_slot_demo` uses perfect attachments for the full random-state
solver. `swap_physical_grasp_demo` is the contact-only smoke path: it closes the
real Franka fingers, verifies that the block follows a short lift, then carries
and releases it without attaching or teleporting it.

These prototypes are the bridge before the full MDP layer. The next step is to
turn the same pieces into:

```text
ObservationBuilder
ActionDecoder
RewardComputer
```
