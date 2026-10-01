# Running evaluations

Operational notes for running batches and reading results. The contract is [PROTOCOL.md](PROTOCOL.md); the
standard-mode wire protocol is [LIMITED_MODE_PROTOCOL.md](LIMITED_MODE_PROTOCOL.md). Task directories end in `-privileged` or
`-standard`.

## Agent logs and timelines
Harbor keeps, per trial, `agent/codex.txt` (every message, command and output), `agent/trajectory.json` and the raw
Codex session (`agent/sessions/`). Run Codex with `--ak reasoning_summary=detailed` to also keep reasoning summaries
(otherwise reasoning is stored encrypted). `scripts/agent_timeline.py <trial_dir>` merges the agent's messages,
reasoning summaries, tool calls, images and token use with the robot service's log into one `analysis/timeline.md`.

## Recordings

- **Standard mode (RoboTwin):** the sim service records `live.mp4` (six views, frames only while physics runs and something moves,
  each stamped with the agent's call and wall/sim time; rendered from the deterministic trajectory at episode end, so it
  costs the agent nothing; `RCB_LIVE=realtime` captures during the episode instead), the exact actions of every call,
  and a crash-safe trajectory. Details: `docs/LIMITED_MODE_PROTOCOL.md` (Live recording). Protocol 2.1 also gives the
  agent measured proprioception (encoders, gripper opening, TCP pose, drive effort) and optional depth noise.
- **Privileged mode:** the agent owns the simulator, so nothing it produces is evidence. `rcb_traj.Session` still dumps every
  rollout's per-step drive targets to `/app/output/rcb_trace/` (`RCB_AGENT_TRACE_DIR`, capped at 300 files / 400 MB),
  and the verifier, after writing the verdict, reconstructs videos of the agent's last six rollouts into
  `agent_sessions/` with an `index.json` of all of them (`agent_traces`, `agent_trace_steps`, `agent_trace_videos`
  in reward.json). Self-reported: an agent that teleports objects through `exec_code` will not replay faithfully.

## Running a two-mode batch (privileged + standard)
```bash
harbor run -p tasks -i robotwin_2_0_<t1>-privileged -i robotwin_2_0_<t2>-privileged -a codex -m openai/gpt-6-luna -n 3 -o $PWD/exps/jobs --job-name <job-priv>
harbor run -p tasks -i robotwin_2_0_<t1>-standard ... -a codex -m openai/gpt-6-luna -n 3 -o $PWD/exps/jobs --job-name <job-std>
scripts/regrade_trials.sh exps/jobs/<job-priv>          # re-run the same grader for trials with a grader error / missing video
scripts/collect_batch_results.py exps/jobs <job-priv> <job-std> <out_dir>   # videos, rewards, cost, summary.md
scripts/make_two_mode_report_zh.py exps/jobs <job-priv> <job-std> <report_dir> [batch_plan.json]   # internal report (Chinese), GIF previews + mp4
```
`CODEX_FORCE_AUTH_JSON=1` uses a ChatGPT-subscription login (`codex login --device-auth`) instead of an API key.
Use an absolute `-o` (compose cp is noisy otherwise); 3 concurrent trials fit one RTX 4090 with headroom for the
separate verifiers. Results (per-task and batch reports) go to the results site and the Hugging Face dataset (PROTOCOL §5), not into the repository.

