# VLABench privileged-state API

This is **privileged-state coding-agent evaluation**. It measures target selection,
planning, skill composition, programming and debugging. Ground-truth poses, labelled
grasp/place points and geometric planning are available; results do not measure
pure visual perception or learning a general policy.

```python
from vlb_traj import Session
with Session() as s:
    s.record_start()
    state = s.state()
    observation = s.observe(camera=2, point_cloud=True)
    # Select targets from the instruction and observed entity names.
    # Execute your own sequence of s.skill(...), s.ik(...), and s.step(...).
    feedback = s.status()
    actions = s.record_stop()
    s.save_trajectory(actions, '/app/output/trajectory.npz')
```

## State and observations

| Method | Inputs and return |
|---|---|
| `Session(instance='/app/instance.json')` | Constructs the fixed native episode; validates compiled model and full initial integration/task state hashes. |
| `reset()` | Reconstructs the model, Composer, robot, entities, task conditions and seeded RNGs. Clears current episode/recording; lifetime counters persist. Returns status. |
| `state()` | JSON-compatible physical state: named entities with category, world position and WXYZ quaternion, joint positions, available annotated grasp/place/button points; robot joints/velocities, TCP pose and both finger joints; compiled action bounds and control period. No target-answer fields or expert sequence. |
| `observe(camera=2,width=320,height=320,point_cloud=False)` | NumPy RGB uint8 `(H,W,3)`, depth in metres `(H,W)`, intrinsic matrix, camera-to-world matrix; optional world point cloud `(H*W,3)`. Camera IDs follow native model order. Optical frame: +X right, +Y down, +Z forward. |
| `ik(position,quaternion_wxyz)` | Native IK, no movement. Returns `success` and seven joint targets. Failed IK is explicitly reported; do not assume returned joints solve the request. |
| `step(action)` | One bounded finite nine-component actuator command; returns native success, step counts and state hash. |
| `skill(name, **kwargs)` | Runs a general official skill and records every actual simulator command. Returns `stage_success`, `failure`, `executed_actions`, native task `success`, counts/hash. A stage result is not task success. |
| `status()` | Native task success and diagnostic counters/hashes; no fabricated dense progress metric. |
| `record_start()` / `record_stop()` | Start immediately after reset; stop returns float64 `(T,9)` controls. Record all formal actions from the fixed start. |
| `save_trajectory(actions,path)` | Validated NPZ submission with controls, timestamps and version/instance metadata. |
| `load_trajectory(path)` / `replay(actions,video=None)` | Validate archive; reconstruct the instance then execute recorded controls, without skills, IK or planning. Optional CPU-rendered MP4. |

Coordinates are world metres. Quaternions are **WXYZ**, not SciPy's XYZW.
Robot joint angles are radians; velocities are radians/second. Finger positions are metres.
The compiled Franka actuator order is seven arm positions then left/right finger translations.
Each control is held **0.1 s (10 Hz), 100 MuJoCo substeps of 0.001 s**. This differs from
LeRobot's higher-level wrapper action interface. Query bounds rather than assuming normalized
actions: native arm actuator ctrlranges are ±1e10; finger ranges are `[0,0.04]`.
These enormous arm ctrlranges are native actuator limits, not a recommended safe motion envelope.

## General official skills

All positions/quaternions use the conventions above. `gripper_state` is two finger
targets (`[0,0]` closed, `[0.04,0.04]` open). Lists/NumPy vectors may be supplied;
use NumPy arrays for arithmetic-sensitive optional arguments such as `press.target_pos`.

| Skill | Main arguments |
|---|---|
| `pick` | `target_entity_name`; optional `target_pos`, `target_quat`, `prior_eulers` (XYZ radians), `specific_keypoint`, `prepare_distance=-0.1`, `target_velocity=0.05`, `max_n_substep=1`. |
| `place` | `target_container_name`; optional `target_pos`, `target_quat`, `motion_planning_kwargs`. Opens the gripper as part of placement. |
| `moveto` | `target_pos`, optional `target_quat`, `gripper_state`, `target_velocity=0.05`, `max_n_substep=1`. |
| `lift` | `lift_height=0.3` (negative lowers), optional `target_pos`, `target_quat`, `gripper_state`. |
| `pull` / `push` | `pull_distance=0.3` / `push_distance=0.3`; optional target pose and gripper state. Native world-Y motion, not an object-relative direction. |
| `move_offset` | `offset` world XYZ; optional target quaternion/gripper state. |
| `open_door` / `close_door` | `target_container_name`; native handle/hinge annotations supply the motion path. |
| `open_drawer` | `target_container_name`, `drawer_id=0`, `pick_prior_eulers=[[-pi/2,0,0]]`; index order follows the container's native bodies/sites. |
| `press` | `target_pos`, optional `target_quat`, `move_vector=[0,0,0.1]`, `max_n_substep=100`. |
| `open_gripper` / `close_gripper` | `repeat=1`. |
| `wait` | `wait_time=100` control steps, optional `gripper_state`. |
| `reset` | General skill returning the arm to default joints; **does not reset the episode**, and all movement is recorded. |
| `pour`, `flip`, `open_laptop` | Native general skill helpers; `open_laptop` takes `target_entity_name`. These are not used by the six core acceptance trajectories. |

Backend assistance is substantial: annotated grasp candidates, true object geometry,
RGB-D-derived obstacle clouds, RRT paths, interpolation and native IK. The native planner may
fall back to a direct path when RRT fails; native skills sometimes ignore IK failure.
`open_drawer` unconditionally returns stage-success upstream, and door entities have a
placeholder grasp predicate. Always inspect physical feedback and native task success.
The native `target_velocity` parameter controls waypoint interpolation spacing, not a
guaranteed Cartesian speed; tracking depends on physics and substep choices.

The adapter lazily renders the official internal observation only when the planner requests
the point cloud, rather than rendering unused images after every control. Planning still
uses the official observation/obstacle geometry. Native `open_door` has a stale loop index
that emits finger commands beyond ctrlrange; the adapter applies MuJoCo's normal range
clamping **before recording and sending** those commands. User `step()` rejects out-of-range
inputs. No task success conditions or physics contacts are changed.

## Replay, budget and trust

NPZ: `actions` float64 `(T,9)`, `times=arange(T)*0.1`, JSON `metadata` containing schema,
source commit, descriptor digest, task, action semantics, period and substep count. Pickles,
nonfinite values, mismatched instances, unsafe archive sizes and more than 4,000 actions
are rejected. Controls after a terminal episode are rejected rather than silently autoresetting.

Reset reconstructs more than qpos/qvel: actuator/controller state, integration time,
warmstart, native event flags and task logic. The fingerprint uses MuJoCo
`mjSTATE_INTEGRATION` plus audited native boolean/event fields. Compiled numerical model
arrays are fingerprinted too. It checks actual equality rather than trusting the seed.
The verifier requires two fresh processes to succeed with identical final hashes;
numeric integration-state differences are also logged. This is tested on the pinned CPU
image; no cross-platform bit-exact claim is made.

`budget.json` accumulates active session wall time, resets, control steps, physics substeps,
API entries and replay steps across resets/session restarts in the same attempt. API entries
include nested public status calls. Harbor supplies whole-attempt wall time and available
agent turns/tokens/cost. Separate Harbor attempts use separate artifacts. Local counters are
diagnostic, not tamper-proof against a root process; don't erase them. The 3,600-second Harbor
timeout is the total retry budget; the 4,000-control cap applies per submitted episode.

Do not call private simulator members, change object poses, state, native predicates or
reward files. Complete expert methods and evaluation episode collections are removed from
the agent image. The verifier receives fresh trusted Python task code and descriptor after
the agent exits, ignores agent PYTHONPATH/cwd, and replays only controls. Existing Harbor
root access still permits attacks on interpreter/dependency binaries; this integration
does not claim a hardened anti-cheating boundary. Ground-truth hiding is intentionally
out of scope.
