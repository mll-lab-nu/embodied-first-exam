# topogym-cast-coil-hard-i00

| | |
|---|---|
| Simulator / robot | TopoGym (Genesis 1.2.1 on CUDA, Nyx RGB) / aloha (two 6-DoF ALOHA (ViperX) arms with parallel-jaw grippers on a fixed base) |
| Family / instance | `cast_coil` / variation `cast_coil_hard`, seed 0 (eval index None), frozen in `environment/instance.json` |
| Task type / tier | trajectory / privileged |
| Base image | `ghcr.io/luigivamper/rcb-topogym:0.2.3-cu128` (built locally with `scripts/build_images.sh topogym`; needs an NVIDIA GPU: `environment/docker-compose.yaml`) |
| Grasping | assisted grasping (contact_weld_v1) |
| Success rule | his default success (goal_complete True; terminal revision release_settling_v2_grasp_contact_2mm) |
| Agent budget | 21600 s |

## Goal
Assemble the gold and silver Cast Coil pieces into their matching interlocking configuration, then release both.

## Success requirements

- Align the pieces' matching assembly frames with relative position error below 1 mm and relative angular error below 0.02 rad.
- The bottom of at least one piece must be within 3 mm of the tabletop. Neither piece may extend more than 1 mm below it, and each piece must overlap the tabletop horizontally.
- Keep both pieces' linear speeds below 1 mm/s and angular speeds below 0.02 rad/s. Merely touching or gripping them is not completion.
- Release all target parts and disengage any assisted grasp. Withdraw the robot until there is at least 5 mm of verified clearance from every target part; opening the fingers while still touching or surrounding the target is insufficient.
- During confirmation, every target point or rigid body's linear speed must be at most 1 mm/s and its displacement from the start of confirmation at most 1 mm. Each target rigid body's angular speed must be at most 0.02 rad/s and angular drift at most 0.02 rad.
- Keep all final conditions satisfied together for at least 0.5 s of simulation time. If any final condition stops holding, the confirmation interval starts again. A brief qualifying pose is not enough; let the simulation advance through the full interval.

## Task failure conditions

- A task piece falling more than 100 mm below the tabletop ends the episode in failure. Finger contact with a held movable piece may penetrate at most 2 mm; holding requires both fingers of the same hand to contact the same piece, or an active assisted grasp by that hand. All other task contacts, including piece-piece, table, arm and gripper-housing contacts, may penetrate at most 1 mm. Exceeding either limit ends the episode in failure.

## Grader details (in addition to the requirements above)

- Contact penetration is read from the contacts at the end of every physics tick (2.5 ms; 10 ticks per control step). "Held" is decided anew at every tick: a zero-force touch counts, and if one finger loses contact (with no active assisted grasp), the other finger is back at the 1 mm limit in the same tick.
- The release clearance is measured between axis-aligned bounding boxes: one around each collision geometry of the whole robot (every link of both arms) and one around each collision geometry of the pieces, so the true gap usually has to be larger than 5 mm.
- Grasp regions (assisted grasping, see Grippers above; one sphere per graspable part): coil_gold: radius 25 mm; coil_silver: radius 25 mm. Both finger contacts must lie inside the part's sphere; a part touched elsewhere is grasped physically. Each region's centre (in its link's frame) is in `/app/instance.json` under `simulator.grasp_assist.targets`.
- A failure is reported in `s.status()["episode_end"]` as "Held finger contact penetration exceeded 2 mm", "Task contact penetration exceeded 1 mm" or "A task body fell below the table".

## Difficulty
Two 6-dof aloha (viperx) arms with parallel-jaw grippers on a fixed base with a 14-D joint-target action space at 40 Hz; success needs the task's predicate (above) held for 0.5 s. Grasping: assisted grasping (contact_weld_v1).

## Reference solution
None yet: `solution/solve.sh` says so and exits 1 (the oracle agent scores 0). A reference solution must be
written for this instance (assisted grasping, if the family enables it, is the same for the oracle and the agent).

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in a fresh process, twice; pass iff the
task's predicate holds after every replay (`tests/grade.py`), plus `/logs/verifier/replay.mp4`. The physics runs on the
GPU, which is not bit-deterministic: the final-state hashes (`deterministic`) and the rebuilt frozen scene
(`instance_ok`) are reported, not required (robot_coding_bench's GPU-backend rule).
