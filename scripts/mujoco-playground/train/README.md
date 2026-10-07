# Reference-policy training (not part of any task)

`qenv.py`: Playground's quadruped environments in plain MuJoCo/numpy (one class per environment, citing its source);
`vecenv.py`: worker processes with shared-memory buffers, the rsl_rl `VecEnv` interface; `train.py`: rsl_rl PPO with
Playground's rsl_rl hyperparameters; `run_capped.sh`: one run under a memory cap (`RCB_MEM_MAX`, default 48G).
Each worker compiles its model once and its envs share it (an MjData is ~1 MB with the arena these scenes need).
