# MuJoCo Playground quadruped tasks: how they are made

docs/benchmarks/mujoco-playground.md describes the tasks; this is the pipeline that makes them. Only `generate.py` runs
in CI (standard library only); the rest needs MuJoCo 3.3.7 and the asset tree of `eai-mujoco`
(`RCB_MJ_ROOT`, built by `images/mujoco/prepare_assets.sh`; `RCB_MJ_OUT=<dir>` writes it elsewhere).

1. **Candidates** (Playground's own code, JAX on the CPU; a checkout of MuJoCo Playground at 4057c14 installed with
   `pip install -e <playground> "jax[cpu]"`):
   `python make_instances.py Go1JoystickFlatTerrain --seeds 0-39 --out cand/`
2. **Reference policies** for the environments without a pretrained one (`train/`, PPO with rsl_rl on the CPU, plain
   MuJoCo in worker processes; `pip install torch rsl-rl-lib tensordict mujoco==3.3.7`):
   `train/run_capped.sh Go1Getup --iters 1000 --envs 2048 --workers 14 --out runs/go1_getup` (a 48 GB memory cap via a
   systemd user scope; ~3 GB used). `train/qenv.py` mirrors each Playground environment's reset, action mapping,
   observations and rewards. Go1 joystick needs none: Playground ships its policy (`RCB_PLAYGROUND=<checkout>`).
3. **Selection and freezing**: `python select_instances.py Go1Getup --cand cand/ --policy runs/go1_getup/policy.pt`
   writes `instances/<Env>.json` (with its t = 0 state hash and the numbers the texts quote), `oracles/<Env>.npy` (the
   reference rows, float32-exact) and `selection/<Env>.json` (every candidate tried and why it was skipped).
4. **Tasks**: `python3 generate.py` (and `--check`).

`shared/rcb_quadruped.py` is the one simulator module: the privileged tooling, the verifier's replay CLI and the
standard service's simulator (`shared/standard/server.py`, the 2.2 adapter).
