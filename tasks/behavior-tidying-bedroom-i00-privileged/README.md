# behavior-tidying-bedroom-i00-privileged

| | |
|---|---|
| Benchmark | BEHAVIOR-1K |
| Mode | privileged |
| Twin | `behavior-tidying-bedroom-i00-standard` |
| Simulator / robot | `behavior` / `r1pro` |
| Family / instance | `tidying_bedroom` / seed 301 |
| Oracle | `none` — No reference solution: BEHAVIOR-1K ships no expert or planner that replays on this frozen instance. Solvable: model trial behavior-tidying-bedroom-i00__VcXRVyJ (behavior-lunaxh-t8-0927, privileged) graded success=1, deterministic=1 by the separate verifier on a pre-v1.0 version of this task (dev/qineng 2d486a91; grader verdict and frozen instance unchanged since); agent log https://embodied-agent-interface-v2-internal.github.io/runs/behavior-1k/codex-gpt6_luna-xhigh/tidying_bedroom/unlimited/, verifier replay https://huggingface.co/datasets/eai-v2-internal/agent-runs/resolve/main/behavior-1k/codex-gpt6_luna-xhigh/tidying_bedroom/unlimited/replay.mp4; not re-run on this version (static validation only). Human review per family (protocol §2.7). |
| Agent time budget | 14400 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-behavior:0.1.1` |

## Task
Tidy the bedroom. The two sandals lie on the bedroom floor and the book lies on the bed. Put one sandal next to the bed and the other sandal next to the first one, and put the book on top of a table in the bedroom.

**Success**, all at the same time (the episode ends by itself the moment they hold):
- the first sandal (`sandal.n.01_1`) is next to the bed (`bed.n.01_1`)
- the second sandal (`sandal.n.01_2`) is next to the first sandal
- the book (`book.n.02_1`) is on top of a table (`table.n.02_1` or any other of the bedroom's `table.n.02_*`)

## Difficulty
First-pass rating on the task-list site: medium. The 2026 challenge's 200 teleoperated demonstrations took 368 s on average (11,037 control steps at 30 Hz) and drove 33.4 m; the scene loads 6 rooms, and the goal uses `nextto`, `ontop`.

## Reference solution
None (`oracle = "none"`): no reference solution was written (the challenge ships teleop demos, not scripts). Evidence that the task is solvable: model trial `behavior-tidying-bedroom-i00__VcXRVyJ` (behavior-lunaxh-t8-0927), graded 1 by the separate verifier; its agent log is on the results site (https://embodied-agent-interface-v2-internal.github.io/runs/behavior-1k/codex-gpt6_luna-xhigh/tidying_bedroom/unlimited/) and the verifier's replay on Hugging Face (https://huggingface.co/datasets/eai-v2-internal/agent-runs/resolve/main/behavior-1k/codex-gpt6_luna-xhigh/tidying_bedroom/unlimited/replay.mp4); `task.toml` `oracle_evidence` has the version it ran on.

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
