## RoboTwin 2.0 tasks, two evaluation modes, verifier isolation

18 commits on top of `main` (698 files; most are 22 RoboTwin task directories × 2 modes plus their instance files). `ci_checks/run_all.sh` passes; every task has oracle 1 / nop 0 in a separate verifier sandbox.

### What is in it
- **Base image** `images/robotwin` (SAPIEN 3 + CuRobo + RoboTwin assets, pinned; expert code scrubbed) and the `third_party/RoboTwin` submodule at `6dde571`.
- **22 unlimited tasks** `tasks/robotwin_2_0_<task>`: frozen instance = RoboTwin seed + initial-state hash (uncommon seeds, chosen by an expert sweep); trajectory = per-physics-step drive targets (T, 34) captured by hooking `scene.step()`; verifier replays twice, six-camera video.
- **22 limited twins** `tasks/robotwin_2_0_<task>-limited` (robot as a service, `rcb-limited/2.0`): simulator in a `sim` sidecar the agent cannot open; the agent gets `submit` (a chunk of low-level actions: `joint_position` streamed at 250 Hz with its own `dt`, or `ee_pose` planned by CuRobo) and `get_obs` (current frames or a watch window), RGB/depth + proprioception only, no reset; videos/frames come back as binary RCB1 frames that the agent's code stores where it likes (nothing enters the model context automatically); the sidecar records the episode as the same (T, 34) trajectory, replays it for success + determinism, renders the video; separate verifier over the sidecar's record.
- **Verifier isolation for all tasks** (`[verifier] environment_mode = "separate"` + `tests/Dockerfile`; CI check). Measured: a cheating oracle that patches `check_success` scores 1 under Harbor's default shared verifier, 0 under the sandbox.
- **Agent egress switch** `scripts/set_agent_egress.py {public|allowlist}` (default public; verified allowlist keeps Codex/ChatGPT login, Claude Code, OpenRouter working while GitHub/PyPI are blocked).
- Tooling: `rcb_traj.py` accepts any RoboTwin task; oracle retries (CuRobo planning is not deterministic run to run); interaction log → self-reported cost fields; generators (`robotwin_mk_task.py`, `robotwin_mk_limited.py`, `robotwin_expert_sweep.py`); batch scripts (`regrade_trials.sh`, `collect_batch_results.py`, `make_two_mode_report_zh.py`).
- Docs: PROTOCOL §4 (isolation, egress), LIMITED_MODE(.zh), LIMITED_MODE_PROTOCOL, LIMITED_MODE_V2_DESIGN.zh (implemented), README sections on the two modes, anti-cheat design and the batch workflow, `docs/results/` (first batch: Codex + GPT-6 Luna, 21 tasks, unlimited 11/21, limited 1/21).

### Review
An independent code review of this branch was run on 2026-09-24; all high/medium findings are fixed in `45795d8`/`85de23c` (sidecar signal deadlock, TOPP status, grader hardening against agent-written logs and oversized trajectories, client timeouts, protocol/doc mismatches, egress). Remaining low items are listed in that commit message.

### Notes for the reviewer
- The base image (21.6 GB) is not on GHCR yet; `scripts/build_images.sh` builds it (needs a GPU host for the tasks, not for the build).
- Branch `verifier-isolation` (PR-sized, contract + robosuite only) is subsumed by this branch; merge either, not both.
- Job outputs are gitignored; the results summary and batch plan are in `docs/results/`; per-task results with videos and failure analysis are under each task's `results/codex-gpt6-luna/README.md`.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
