`g1_running.npz` holds the weights of the G1 running policy of **C1801SYQ/g1_running**
(https://github.com/C1801SYQ/g1_running, commit de56c7adeadfa1b639fda5332f57f32588133228, Apache License 2.0:
`LICENSE.g1_running`), converted to numpy without change:

- `rl_sar/policy/g1/running/policy.pt` (TorchScript, rsl_rl actor, checkpoint `model85800_straight`; sha256
  c4890005e430895feeb1aa8a80fa71f5e7fe96f7c7b45652bb709807d24930b2): the actor's four linear layers (`actor_*`; ELU
  between them; its normaliser is the identity), 96 observations -> 29 actions;
- `rl_sar/policy/g1/running/deploy.yaml` (sha256 d98673ce5bd73244bce23230d2df0a65f848bb8bc307dc9d8b70d4f024035932):
  `joint_ids_map` (`map`: policy index i -> Unitree SDK joint `map[i]`), `stiffness` and `damping` (SDK order),
  `default_joint_pos` (`default`, policy order);
- `test_x`, `test_y`: one input and the TorchScript output for it (run_policy.py checks the numpy port against it).

The policy is the platform's implementation of the high level's `run` (simulator side only; never in the low level's
seat: seat/toolkit.toml [forbidden]).
