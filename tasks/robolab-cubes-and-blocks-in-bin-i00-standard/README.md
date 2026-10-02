# robolab-cubes-and-blocks-in-bin-i00-standard

| | |
|---|---|
| Benchmark | RoboLab |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `robolab-cubes-and-blocks-in-bin-i00-privileged` |
| Simulator / robot | `robolab` / `franka-robotiq-2f85` |
| Family / instance | `cubes_and_blocks_in_bin` / seed 0 |
| Oracle | `none` — No reference solution: RoboLab ships no expert or planner. Positive examples graded 1 by the separate verifier: robolab-cubes-and-blocks-in-bin__MJxbnQb (robolab-cubes-and-blocks-in-bin-i00-privileged, run codex-gpt6_luna-xhigh, robolab-lunacx-0925-2038, ws; https://embodied-agent-interface-v2-internal.github.io/runs/robolab/codex-gpt6_luna-xhigh/cubes_and_blocks_in_bin/unlimited/); robolab-cubes-and-blocks-in-bin__YG25byB (robolab-cubes-and-blocks-in-bin-i00-standard, run codex-gpt6_luna-xhigh, robolab-lunaxh-limited-0928, lab; https://embodied-agent-interface-v2-internal.github.io/runs/robolab/codex-gpt6_luna-xhigh/cubes_and_blocks_in_bin/limited/). Human review per family (PROTOCOL §2.7). |
| Agent time budget | 5400 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robolab:0.1.1` |

## Task
Standard-mode twin of `robolab-cubes-and-blocks-in-bin-i00-privileged` (same frozen instance, the state after RoboLab's canonical seed-0 reset):
the agent gets only the `eai-standard/2.2` client (docs/STANDARD_MODE_2_2.md); the simulator runs in the `sim` sidecar
(`environment/docker-compose.yaml`, GPU on the sidecar), which owns the scene and records the episode as a (T, 8)
trajectory. The collect hook (`environment/sim/finalize.sh`) ends the episode, lets the service exit, replays the
trajectory in two fresh processes (Isaac: only the first replay in a process is bit-exact, and two simulators do not fit
in one container) and writes `final.json`; the verifier runs in a separate sandbox (`tests/Dockerfile`) over those
artifacts. Compare against the privileged task to measure the cost of losing resets, privileged state and primitives.

## Difficulty
That of `robolab-cubes-and-blocks-in-bin-i00-privileged` (its README), without resets, object poses or the success predicate: every step is planned from camera images, depth and the robot's own proprioception, and a failed grasp or a knocked-over object stays that way.

## Reference solution
None: RoboLab ships no expert or planner, and no reference solution has been written for this family (`oracle = "none"`). Positive examples, model trials the separate verifier scored 1:
- `robolab-cubes-and-blocks-in-bin__MJxbnQb` (privileged mode, run `codex-gpt6_luna-xhigh`, batch `robolab-lunacx-0925-2038`, host ws): [trial log](https://embodied-agent-interface-v2-internal.github.io/runs/robolab/codex-gpt6_luna-xhigh/cubes_and_blocks_in_bin/unlimited/), [replay video](https://huggingface.co/datasets/eai-v2-internal/agent-runs/resolve/main/robolab/codex-gpt6_luna-xhigh/cubes_and_blocks_in_bin/unlimited/replay.mp4)
- `robolab-cubes-and-blocks-in-bin__YG25byB` (standard mode, run `codex-gpt6_luna-xhigh`, batch `robolab-lunaxh-limited-0928`, host lab): [trial log](https://embodied-agent-interface-v2-internal.github.io/runs/robolab/codex-gpt6_luna-xhigh/cubes_and_blocks_in_bin/limited/), [replay video](https://huggingface.co/datasets/eai-v2-internal/agent-runs/resolve/main/robolab/codex-gpt6_luna-xhigh/cubes_and_blocks_in_bin/limited/replay.mp4)

## Verification
`success` = live success ∧ replay success ∧ deterministic (two fresh-process replays agree), computed in the sidecar's
collect hook; `tests/grade.py` reads `final.json` with no network and writes the reward fields (with `infra_error` and the
crash-recovery fields), plus `/logs/verifier/replay.mp4`. RoboLab's success term is instantaneous: it is checked after
every control step and the first step where it holds ends the episode (RoboLab's own termination), live and in the
replays.

No oracle; human review in PR #3 (PROTOCOL §2.7: per family, this task and its twin, a positive example and the `nop` result).

## Details
| | |
|---|---|
| Episode | one episode, no reset, no step limit: it ends at the first control step where RoboLab's success term holds, when the agent's time is up, or on a simulator error; the wall clock is the only budget |
| Action space | `submit` chunks of `joint_position` (8, streamed at the 15 Hz control rate with the agent's `dt`, a multiple of 1/15 s) or `ee_pose` (8, differential IK per row); `observe` frames or a watch window; `/kinematics` (FK / IK, stateless); binary RCB1 responses |
| Images | the `sim` sidecar runs eai-robolab (BUILD_ONLY, `images/robolab/BUILD_ONLY`); the agent container and the verifier run the shared client image with its pip pins (`scripts/eai_standard/client.env`) |
| Crash recovery | resume class `exact`: every control step journaled, a checkpoint with the state hash after every call; `restart: on-failure:6`, the service resumes the same episode (docs/STANDARD_MODE_2_2.md §13) |
| Generator | `scripts/robolab/mk_tasks.py` (`scripts/robolab/families.json`, `template/standard/`, `shared/`, `scripts/eai_standard/`); docs/benchmarks/robolab.md |
