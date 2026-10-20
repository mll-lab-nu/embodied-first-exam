# kinder-constrained-cupboard-i00-standard

| | |
|---|---|
| Benchmark | KinDER |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `kinder-constrained-cupboard-i00-privileged` |
| Simulator / robot | `kinder` / `tidybot-plus-plus` |
| Family / instance | `constrained-cupboard` / seed 0 |
| Oracle | `none` — GPT-6 Luna's privileged-mode trajectory, run `codex-gpt6_luna-medium` on the results site, which today's privileged verifier scores 1; it moves the base diagonally by up to 0.14 m a step, beyond standard mode's 0.1 m disc, so it is no standard-mode example, and none is known yet; human review in PR #8 |
| Agent time budget | 1800 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:kinder-0.1.6` |

## Task
Standard mode (robot as a service, `eai-standard/2.1`) of `kinder-constrained-cupboard-i00-privileged`: the same KinDER instance (`kinder/ConstrainedCupboard3D-o6-v0`, seed
0) runs in the `sim` sidecar; the agent gets a client and the robot's own sensors -- two
cameras, joint encoders, the base's odometry -- and
never the scene's state or the goal check. No reset: one episode, which is graded.

Task: put the six brown rods lying on the floor (30 cm long) into the row of eleven narrow cupboards standing side by side ahead of the robot, one rod each, each into a cupboard's 40 cm-tall compartment: taking the rods in order of their distance from where the centre of the robot's base starts, nearest first, they go into the 11th, 5th, 2nd, 8th, 4th and 1st cupboard of the row, counted from the robot's left as it faces the row at the start. The task succeeds the moment every rod's centre is inside its compartment: above that compartment's shelf, below the shelf over it, and within the cupboard's 10 cm width and 30 cm depth.

## Difficulty
Geometric: six identical rods, each into the one narrow compartment it is owed (standard mode names them by distance and by place in the row).

## Reference solution
None. Solvability rests on the positive example in `oracle_evidence` (task.toml), checked by a human reviewer (docs/protocol/README.md §2.7).

## Verification
The sidecar judges the episode as it runs (KinDER's goal check at every control step; the episode ends there) and,
when the collect hook ends the trial, writes that verdict to `/data/final.json` (`graded_by = "live"`): nothing is
replayed to grade it (owner, 2026-10-17). The scene's start is checked against the frozen instance's
recorded state (`scene_sha`) when the episode begins (a mismatch is `instance_mismatch`, infrastructure).
`tests/grade.py` grades `final.json` in a container of its own with no network: success = live success. The video
(`replay.mp4`) is rendered from `trajectory.npz` in one pass after the verdict and never changes it.
No oracle; human review in PR #8. `nop` scores 0.

Benchmark notes: `tasks/kinder/README.md`.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 4 GB | 3 GB |
| GPU memory | 2 GB | 2 GB |

- GPU: required, any NVIDIA GPU; recommended: any 8 GB+ NVIDIA GPU (RTX 4090 / L4).
- Measured: GPU 1.2-1.3 GB (oracle 1.2 GB on RTX 4090), evaluation-pool GPU profile (per-trial GPU peaks, 10-03..10); memory: privileged container p90 2.8 GB, sim 1.1 GB, mem_guard (docker memory per container, an RTX 4090 workstation, 10-02..10); CPU author estimate
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 6 GiB GPU memory, 14 GiB memory. Limits measured: GPU: 1.3 GiB (the evaluation pool's GPU profile (per-trial GPU peaks by card, 10-03..10)) -> max(1.5 x peak, peak + 4); memory: agent container docker peak 2.8 GiB over 11 samples (mem_guard (docker memory incl. page cache, top-4 containers every 10 min, an RTX 4090 workstation, 10-02..10)) -> max(1.5 x peak, peak + 4, 8), at most the 16 GiB cap; whole trial: + the sim service's 6 GiB (docker peak 1.1 GiB, 1 samples); processes 512 and disk 20 GiB: design defaults, not yet measured.

## Details

### Change Log
- 2026-10-11: `RCB_RESET_BUDGET`'s default 0 -> 10 (owner decision; PROTOCOL §4.5, tasks/kinder/README.md); the service already had `POST /reset`. The scene, instance, pass rule and verifier are unchanged, so the task keeps its name; runs recorded before this date had no reset and are reported separately.
- 2026-10-16: agent time limit 3600 s -> 1800 s (`[agent] timeout_sec`, both twins; author decision, tasks/kinder/README.md), and `RCB_RESET_BUDGET`'s default 10 -> 0 (author decision): one episode, which the practice and the graded attempt share. The scene, instance, pass rule and verifier logic are unchanged (`tests/rcb_limits.json` carries the new cutoff), so the task keeps its name; runs recorded before this date are reported separately.
- 2026-10-17 (owner): graded by the live episode: `success` = KinDER's goal check reached during the episode the sim service ran (the same rule, judged as it ran), and no grading replay runs (no `replay_success` / `deterministic` any more; `final.json` has `graded_by = "live"`, `replays = 0`, `reward.json` `graded_by_live = 1`). The video is one render pass over the trajectory after the verdict, as before. The scene's start is checked when the episode begins: a scene that does not build to the frozen instance's recorded state (`scene_sha`) gives up as infrastructure (`instance_mismatch`). The scene, instance, pass rule and the agent's interface are unchanged, so the task keeps its name; every archived verdict is the same under the live rule.
