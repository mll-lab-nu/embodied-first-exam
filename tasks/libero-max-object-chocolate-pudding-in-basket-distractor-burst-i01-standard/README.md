# libero-max-object-chocolate-pudding-in-basket-distractor-burst-i01-standard

| | |
|---|---|
| Benchmark | LIBERO-MAX |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `libero-max-object-chocolate-pudding-in-basket-distractor-burst-i01-privileged` |
| Simulator / robot | `robosuite` / `franka-panda` |
| Family / instance | `libero-max/libero_object/distractor_burst` / seed 195 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-libero-max:0.1.0` |

## Task
LIBERO-MAX case `pro-semantic-object-t08-i09-distractor_burst-d1-p195` as a robot service: a Franka Panda arm at a table, instructed **"Lift chocolate pudding and put it in basket."**, on
the same frozen instance as `libero-max-object-chocolate-pudding-in-basket-distractor-burst-i01-privileged`, with the same online event (distractor burst: 5 other objects appear on the table (`orange_juice_1`, `salad_dressing_1`, `bbq_sauce_1`, `ketchup_1`, `alphabet_soup_1`), the
first time the gripper comes within 0.18 m of `chocolate_pudding_1`). The simulator runs in the `sim` sidecar
(`environment/sim/server.py` on main's `rcb_service.py`); the agent only has the client: two cameras (RGB
256×256, depth on request, calibrated), the robot's own state, and OSC control steps in chunks. One
episode, no reset, no object poses; nothing to hand in. The agent is told that the scene may change once, not how or
when.

## Difficulty
The agent has to find the objects in the images, close the loop through the cameras with OSC deltas, notice the change
when it happens and adapt, and finish in one episode without a reset.

## Reference solution
`solution/`: the privileged oracle's 184 control steps (recorded offline; see the twin's README) submitted
through the client; the episode ends with `reason = "success"` at the last of them.

## Verification
The sim service ends the episode at LIBERO's success (or at the 9000-step technical cap, when the agent's time
is up, or on a simulator error), replays the recorded episode in a fresh process and writes `/data/final.json`;
`tests/grade.py` (separate sandbox, no network) grades it: `success = live_success ∧ replay_success ∧ deterministic`.

## Details
| | |
|---|---|
| Actions | `ee_delta` (7, float64): OSC hand-target delta (1.0 = 0.05 m, 0.5 rad per control step) and gripper |
| Episode cap | 9000 control steps (450 s of robot time; `spec.max_control_steps`, PROTOCOL §4.5 MAY) |
| Resources | 4 CPUs, no GPU (CPU physics, OSMesa rendering) |
