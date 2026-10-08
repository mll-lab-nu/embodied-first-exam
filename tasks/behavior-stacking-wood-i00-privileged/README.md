# behavior-stacking-wood-i00-privileged

| | |
|---|---|
| Benchmark | BEHAVIOR-1K |
| Mode | privileged |
| Twin | `behavior-stacking-wood-i00-standard` |
| Simulator / robot | `behavior` / `r1pro` |
| Family / instance | `stacking_wood` / seed 301 |
| Oracle | `none` — No reference solution: BEHAVIOR-1K ships no expert or planner that replays on this frozen instance. Solvable: model trial behavior-stacking-wood-i00__48hThC9 (behavior-lunaxh-t8-0927, privileged) graded success=1, deterministic=1 by the separate verifier on a pre-v1.0 version of this task (dev/qineng 912567fa; grader verdict and frozen instance unchanged since); agent log https://embodied-agent-interface-v2-internal.github.io/runs/behavior-1k/codex-gpt6_luna-xhigh/stacking_wood/unlimited/, verifier replay https://huggingface.co/datasets/eai-v2-internal/agent-runs/resolve/main/behavior-1k/codex-gpt6_luna-xhigh/stacking_wood/unlimited/replay.mp4; not re-run on this version (static validation only). Human review per family (protocol §2.7). |
| Agent time budget | 14400 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-behavior:0.1.1` |

## Task
Six logs lie spread out on the driveway in the garden; stack them so that every log touches at least one other log.

**Success**, all at the same time (the episode ends by itself the moment they hold):
- every log (`log.n.01_1` to `_6`) is touching at least one other log

## Difficulty
First-pass rating on the task-list site: medium. The 2026 challenge's 200 teleoperated demonstrations took 531 s on average (15,939 control steps at 30 Hz) and drove 85.96 m; the scene loads 4 rooms, and the goal uses `touching`.

## Reference solution
None (`oracle = "none"`): no reference solution was written (the challenge ships teleop demos, not scripts). Evidence that the task is solvable: model trial `behavior-stacking-wood-i00__48hThC9` (behavior-lunaxh-t8-0927), graded 1 by the separate verifier; its agent log is on the results site (https://embodied-agent-interface-v2-internal.github.io/runs/behavior-1k/codex-gpt6_luna-xhigh/stacking_wood/unlimited/) and the verifier's replay on Hugging Face (https://huggingface.co/datasets/eai-v2-internal/agent-runs/resolve/main/behavior-1k/codex-gpt6_luna-xhigh/stacking_wood/unlimited/replay.mp4); `task.toml` `oracle_evidence` has the version it ran on.

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in two fresh processes; pass iff the BDDL goal
holds after every replay, the final-state hashes agree and the rebuilt frozen instance matches the recorded one
(`tests/grade.py`), plus `/logs/verifier/replay.mp4`. A fresh process reproduces the live run bit for bit (the replay
starts from the loaded state, no reset); an in-process reset is only approximate, hence two fresh processes.

No oracle: the family is reviewed by a maintainer (PROTOCOL §2.7) in the pull request that adds it, on a positive example and a `nop` run per mode.

## Details
| | |
|---|---|
| Instance | 2026 BEHAVIOR Challenge public_test instance 301 (scene `house_single_floor`), state hash in `environment/instance.json` |
| Image | `ghcr.io/mll-lab-nu/eai-behavior:0.1.1` = `stanfordvl/behavior:3.9.2` + ffmpeg; BUILD_ONLY, built on every host (`images/behavior/`) |
| Dataset | the licensed BEHAVIOR dataset, mounted read-only from `$RCB_BEHAVIOR_DATA` (a precondition), never baked in |
| GPU | an RTX-class NVIDIA GPU (`environment/docker-compose.yaml`, `count: 1`) |
| Budget | 14400 s: every Python process pays ~3 min of Isaac Sim + scene load; ~7-11 control steps/s (docs/benchmarks/behavior.md) |
| Verifier time | each replay min(4 h, max(3600 s, 1200 s + steps / 2)); `[verifier] timeout_sec` 30600 s (two capped replays + 30 min) |

### Change Log
- 2026-10-08: verifier time limits only. `tests/grade.py` gives each of the two fresh-process replays min(4 h, max(3600 s, 1200 s + steps / 2)) instead of a flat 3600 s, and `[verifier] timeout_sec` is 30600 s (was 5400 s), measured on an 8-vCPU L40S host (job #3137): the Isaac start took 626 s and a 10,475-step replay ran slower than 3.5 control steps/s, so long trajectories hit the old limit as a grader error. The scene, frozen instance and pass rule are unchanged, so the task keeps its name; a trial graded before this date with `grader_error` = 1 can be regraded.
