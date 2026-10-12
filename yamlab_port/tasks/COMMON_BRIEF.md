# Common brief for YAMLab task agents

You port one old RoboTangle family into YAMLab. You report to the YAMLab port lead (the agent that spawned you), not to the user. Write in English.

## Read first

- `yamlab_port/YAMLAB_NOTES.md`: YAMLab, the YAM robot, how a task is built, deformables, hosts.
- `yamlab_port/PLAN.md`: ground rules and your family's section.
- YAMLab source: `yamlab_port/yamlab/` (pristine clone, ec0455d). Templates: `yamlab/envs/tasks/put_pot_on_cooktop_manager*.py`, `yamlab/configs/tasks/put_pot_on_cooktop.yaml`, `yamlab/utils/task_logic.py`, `yamlab/utils/jparse_ik.py`, `scripts/benchmark_eval_throughput.py`.
- Old task: STL package `robotangle_v1_stl/<family>/<tier>/` (in this repo; originally the lab workspace's `tmp/2026-10-11_robotangle_v1_stl/`) (STL in mm, `layout.json`, `start_state.md`, centreline CSVs, `preview.png`, README at the package root). Old code (read-only worktree): `yamlab_port/ref/topogym_2dafa5f/topogym/` (`tasks/<family>/common.py` = success predicate, `assets/geometry/<family>.py` = generator, `planning/<family>/` = old oracle, `utils/geometry/` = helpers). You may copy pure-numpy helpers with a source note.

## Hard rules

1. **Robot unchanged.** Never edit `configs/robot/yam.yaml`, `yamlab/robot/**`, the YAM USD, gains, the gripper, base poses, the action layout or the control rate. Only task files plus registration lines. Per-task knobs YAMLab already exposes (object friction, sim device per mode, episode length, grasp_detect) are fine. No grasp welds or attachment constraints between gripper and object.
2. **Laptop: no simulations or heavy compute.** The user's own experiment runs on it. Editing files and light scripts there are fine.
3. **Compute host = vast** (our borrowed box; connection details removed from this copy):
   - Your dir is `/workspace/yamlab_port/runs/<family>/` only. Never touch other dirs: `/workspace/jianwen-*`, `/workspace/rt`, `/workspace/mj`, other families' run dirs, or `/root/.ssh`.
   - The venv `/workspace/yamlab_port/venv` and the clone `/workspace/yamlab_port/yamlab` are shared and read-only for you. Do not pip install into the venv. If you need a package, install it with `pip install --target /workspace/yamlab_port/runs/<family>/pylib` and add that to PYTHONPATH.
   - Environment: `. /workspace/yamlab_port/env.sh` (venv, EULA, user-space libs, Vulkan ICD). yamlab is NOT installed in the venv. Make your own copy, `cp -r /workspace/yamlab_port/yamlab /workspace/yamlab_port/runs/<family>/yamlab`, add your task files there, and set `PYTHONPATH=/workspace/yamlab_port/runs/<family>/yamlab`. Check `yamlab.__file__` at start.
   - Run everything under `nice -n 19` and `timeout`. At most **2 concurrent Isaac processes** for you. The GPU is shared with another user's job (gpusearch): keep VRAM small, and prefer CPU physics (`device="cpu"`), which is also the deterministic path.
   - Never `pkill`/`pkill -f` by name. List your PIDs and kill them by number. Detach long jobs with `ssh -f ... 'setsid nohup ... > log 2>&1 < /dev/null &'`.
   - Keep large outputs on vast. Copy back only code, JSON metrics, small frames/videos (<= ~20 MB each). No bulk transfers through the laptop.
4. **Rendering:** Isaac's RTX renderer crashes on vast (rtx.scenedb segfault at startup). `--enable_cameras` does not work there. Run physics-only and strip the camera sensors from the scene cfg in your task (see `yamlab_port/setup/vast_physics_smoke.py`: it wraps `YamBimanualSceneCfg.__post_init__` and sets the `*_camera` entries to None; a cleaner task-level flag is fine too).
   - For evidence, (a) save per-step states (object/link poses, EE poses, joint targets) as `.npz`, and (b) write a replay script that re-runs your saved action sequence from the same reset and takes an `--enable_cameras` flag that writes top-camera (and one wrist-camera) frames.
   - The lead will run that replay on a host where RTX works (ws/ws3 in an Isaac 5.1 container) to make the video. You may also make a quick matplotlib/trimesh plot of the logged states on vast as a stand-in.
   - Do not use ws/ws2/ws3 yourself unless the lead tells you to.
5. **Git:** no pushes, no new repos, no branch switching in existing worktrees. Your source of truth is the local folder `yamlab_port/tasks/<family>/`. Keep it mirrored to vast with scp/rsync, and do not edit only on vast.
6. **Workspace:** everything you create locally lives under `yamlab_port/tasks/<family>/`. Keep a short `STATUS.md` there (state, numbers, blockers; update it at milestones) and a `README.md` (how to build and run).

## Deliverables for each tier

- **Re-layout**: re-lay the fixtures for the YAM workspace (two arms side by side facing +X, table x 0.30..1.00, y -0.55..0.55, top z 0.7517). Keep the task's topology and difficulty: the same parts, clearances, wire/rope/cable geometry, crossing order. Record the exact transform (old table frame mm -> YAMLab world m) and the reason in STATUS.md; the lead copies it into PLAN.md's re-layout log.
- A YAMLab task: config YAML, `*_manager_cfg.py`, `*_manager.py`, gym id `<Family>-<Tier>-v0`, registered. Build assets from the STLs, keeping the geometry 1:1 in mm. The layout is re-placed in the YAM workspace and the transform is documented.
- A goal check equivalent to the old success predicate (same thresholds unless physics-dependent; document every deviation). Return it per step, together with the diagnostic values.
- A scripted oracle: privileged state, Cartesian waypoints, IK, 14-D joint targets. It must reach success. Save the action sequence.
- Replay: the open-loop replay of the saved actions from the same reset reaches success. Report whether two runs are bit-identical (state hashes).
- Negative checks: nop (hold the start pose) fails, and a naive variant fails for the intended reason.
- Metrics JSON per run (success, steps, sim time, wall time, key predicate values) and the replay script with `--enable_cameras`.

## How to work and report

- Measure before you design. Start with a scene-only build (no oracle) and check that it loads, settles and is stable (no explosions, no penetration). Then measure YAM reach and IK for your key poses. Then build the oracle.
- Be honest about feasibility. If something does not work in YAMLab/PhysX (e.g. the rope chain cannot hold a knot, or a grasp cannot hold), stop after a bounded, evidence-based attempt. Report what you tried, the measurements, and the smallest change that would make it work. Do not fake success, loosen the goal silently, or move the robot.
- Tiers: solve very_easy first (end to end, including replay and the negative checks). Then go on to the next tier (easier) if very_easy is solid. Stop after easier, or at a blocker.
- Your final message (it returns to the lead) has: state per tier, the evidence paths (local and vast), the key numbers, the deviations from the old task, blockers, and what the lead must do (e.g. render the video).
