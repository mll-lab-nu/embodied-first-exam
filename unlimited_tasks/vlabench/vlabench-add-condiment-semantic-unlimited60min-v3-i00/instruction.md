Complete this fixed robot task: **Add ketchup to the dish**.
Use `from vlb_traj import Session; s=Session()`; read /app/API.md.
Unlimited means privileged state via s.state(), native general skills, same-instance reset,
record and replay. No reset count, cumulative exploration, model-call or token quota.
No episode or submitted-trajectory step cap. All exploration, thought and resets share 3600 seconds.
Only robot controls may change the scene; do not change runtime, physics, predicates or scores.
Start recording immediately after reset with s.record_start(); use s.save_trajectory(s.record_stop(),'/app/output/trajectory.npz').
Only the final submitted trajectory is independently replayed twice; exploration successes do not score.
Costs are per-Session under /app/output/sim-usage; sum all records. No expert policy is provided.
