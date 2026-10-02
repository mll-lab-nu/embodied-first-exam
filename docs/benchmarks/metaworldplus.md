# MetaWorld+

All fifty of [Meta-World](https://github.com/Farama-Foundation/Metaworld)'s v3 environments (Sawyer arm, reward v2),
each on one frozen instance, in both modes: 100 tasks.

| | |
|---|---|
| upstream | Meta-World @ `59fc34d7768af9785e4688c3e1db671424f4a6c3` (MIT), MuJoCo 3.3.0, gymnasium 1.1.1 |
| tasks | `tasks/metaworldplus-<env>-i00-privileged` and `tasks/metaworldplus-<env>-i00-standard` (twins share the instance) |
| metadata | `simulator = "mujoco"`, `robot = "sawyer"`, `family = "metaworld/<env>"`, `oracle = "full"` |
| image | `ghcr.io/mll-lab-nu/eai-metaworld:0.1.0` (`images/metaworld/`), CPU only |
| standard client | the one client base and pins of `scripts/eai_standard/` (`client.env`, `client-requirements.txt`); `rcb_client.py` / `rcb1.py` byte copies of the MuJoCo standard tasks' (accepting both protocol spellings) |
| generator | `scripts/metaworldplus/` (`freeze.sh` → `frozen/`, `generate.py` → `tasks/`) |

## Task definition
- **Instance.** Meta-World's reset randomization (object and goal positions) drawn with the instance seed: 0, except
  soccer and stick-pull (1), where Meta-World's scripted policy fails on seed 0. Frozen in `instance.npz` (~13 KB): the
  MuJoCo integration state, the model arrays reset rewrites, the env's JSON-encodable caches and both RNG states,
  with a SHA-256 checked on every load. Copied into `environment/`, `tests/` and `environment/sim/`.
- **Actions.** Meta-World's native action in both modes, `[dx, dy, dz, grip]` clipped to [-1, 1], one per control step
  (0.0125 s = timestep 0.0025 s × frame_skip 5): the hand's mocap target moves by `[dx, dy, dz]` × 1 cm and the arm
  follows through a weld; `grip` drives the fingers. There is no `joint_position` action (PROTOCOL §4.4 SHOULD): the
  Sawyer in Meta-World has no arm actuators (`model.nu = 2`, the two fingers), so joint targets would mean changing
  the upstream robot model. In standard mode the type is called `ee_delta`.
- **Success.** Meta-World's own check (`evaluate_state`) on the state after the last action (PROTOCOL §3): no
  "success at any step". In three environments (handle-press, handle-pull-side, stick-pull) the success state does
  not persist by itself (holding still for 10 control steps after the oracle's last action loses it); their READMEs
  say so, and the instructions tell the agent that only the final state counts.
- **Length.** Privileged deliverables have 1 ≤ T ≤ 500 actions (Meta-World's `max_path_length`; the MuJoCo
  Playground tasks bound theirs the same way). Standard episodes have no step limit (D1): only the wall clock.
- **World frame.** Metres; x to the robot's right, y forward (away from the robot's base), z up; table top at z = 0.
  Both instructions state it; the workspace box of the hand's target is given per task.
- **Standard-mode observations.** Four fixed cameras (`front`, `left`, `right` and Meta-World's `topview`; RGB, depth,
  intrinsics and camera-to-world pose), proprioception (`tcp`, gripper opening, mocap target, arm and finger joints,
  last command) and `meta["task"]["target_pos"]`, the point Meta-World's check measures against (as the MuJoCo
  Playground standard tasks give their target). No object poses, no reward, no success signal. Meta-World's
  per-camera views `corner*` are left out: they render upside down.

## Standard-mode service (`images/metaworld/standard/server_mw.py`)
Derived from `images/mujoco/limited/server_mj.py` and identical in protocol and lifecycle (four endpoints, RCB1, no
reset, journal + per-call checkpoints with at most two resumes, startup watchdog, SIGUSR1 collect hook, `/data`
evidence, verdict before video). Differences:
1. The action type comes from the tool module (`mw_tool.ACTION_TYPE`: `ee_delta`) instead of a fixed `joint_position`.
2. Watching (`/observe` with `seconds > 0`) holds the hand still (`S.hold_targets()`), since actions are deltas.
3. Cameras and proprioception come from the tool module (`CAMERA_VIEWS`, `PROPRIO_LAYOUT`); `meta.task` is the target.
4. DexToolBench's goal logic is gone.
5. As in the MuJoCo service after the migration (PROTOCOL §7): a simulator error (500) ends the episode with
   `reason = "error"`, a body over 64 MB gets 413, non-numeric `dt` / `seconds` are a 400; `final.json` carries
   `replay_success` / `live_success` and the grader writes numeric fields only; `/status` and `meta` also carry
   `sim_steps`, submit responses `clipped`.

Protocol: `eai-standard/2.1` (`/spec`, `task.toml`, instructions). `generate.py` finishes every task with
`scripts/task_conventions.py` `normalize` (README layout, no `results/`), and `--check` is clean on all 100.

Agent results are not in the repository (PROTOCOL D3): they are published on the results site.

## Egress
Meta-World's scripted policies solve these tasks and are public (PyPI, GitHub), so `task.toml` closes agent egress to
the model APIs (`network_mode = "allowlist"`, the hosts of `scripts/set_agent_egress.py`), as DexToolBench does. The
policies are deleted from the image in the layer that installs them; `freeze.sh` mounts them from the pinned commit.

## Rebuilding
```bash
docker build -t ghcr.io/mll-lab-nu/eai-metaworld:$(cat images/metaworld/VERSION) \
    -f images/metaworld/Dockerfile images/metaworld          # ~780 MB
bash scripts/metaworldplus/freeze.sh            # instances + oracles -> scripts/metaworldplus/frozen/ (~1 min)
python3 scripts/metaworldplus/generate.py       # -> tasks/metaworldplus-* ; re-running reproduces them exactly
cd tasks && harbor add --scan . && cd ..
bash ci_checks/run_all.sh tasks/metaworldplus-*
```
`scripts/build_images.sh` still names images `rcb-<name>`; until the migration, build this one with the command above.
`freeze.sh` re-creates every instance and oracle, so the task digests change only if the image or Meta-World changes.

## Evidence
`scripts/metaworldplus/frozen/report.json` (written by `freeze.sh`), for all fifty environments: the instance is not
solved at the start; `reset()` is bit-exact; the oracle (Meta-World's scripted policy, up to its first success, 41–136
actions) succeeds; two replays in fresh processes end in the live state's hash and succeed. Instances reproduce
the earlier MetaWorld+ snapshots bit for bit (same seeds, same integration state).

Harbor runs on the generated tasks (AMD Ryzen 9 7950X, Docker, no GPU): `-a oracle` 50/50 privileged and 6/6 standard
(assembly, handle-press, handle-pull-side, soccer, stick-pull, sweep) score 1, deterministic; `-a nop` scores 0 on four
tasks per mode. Two scripted cheat attempts score 0: in privileged mode, tooling patched to report success, forged
reward files and a do-nothing trajectory; in standard mode, hidden endpoints (`/reset`, `/state`, `/success`: 404), a
wrong action type and `dt` (400), and a forged `final.json` in the agent's container (never collected).
