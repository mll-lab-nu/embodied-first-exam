# scripts/kinder — where the KinDER tasks come from

Every `tasks/kinder-*` directory is generated from this one; nothing in them is edited by hand. What they are and why:
`docs/benchmarks/kinder.md`.

| file | what it is |
|---|---|
| `subset.toml` | **the source of truth**: which KinDER environments, each goal's sentence, `room_camera` where upstream's is overhead |
| `facts.json` | what the simulator is the authority on: each scene's digest, the action space, costs, the checks below. Written by `measure` only |
| `shared/rcb_kinder.py` | the tooling: frozen instance (in KinDER's MimicLabs lab), recording, deterministic replay, camera images. Copied into every task |
| `shared/grade.py` | the full-mode verifier: two replays in a fresh process, both must reach the goal and end in the same state |
| `shared/limited/server.py` | the limited-mode adapter behind `scripts/limited/rcb_service.py`: the robot's sensors, the odometry frame |
| `shared/limited/rcb_client.py` | the agent's client: the shared client code with KinDER's docstring (its API reference) |
| `templates/`, `templates/limited/` | everything the tasks have in common, with `{{placeholders}}` |
| `configs/limited.yaml` | the standard limited run: 50 resets, the robot's own cameras with wrist depth |

```bash
./gen_tasks.py render                # rewrite every task dir from the sources   (no simulator needed)
./gen_tasks.py measure [family]      # pin, check and time each instance       (image + GPU, see gen_tasks.py)
./gen_tasks.py verify                # re-measure; fail on drift, a passing nop, a non-deterministic replay
```

`measure` checks, per task: holding still for a whole episode does not reach the goal; a replay is bit-identical in
process and in a fresh one; for a task with a limited twin (the 3D ones), the real sidecar refuses an out-of-range action, serves wrist depth, returns to the t=0
images after a reset, and finalizes with a deterministic replay and a video. Adding a task: a `[[task]]` block in `subset.toml`, then
`measure <family>`, `render`, `ci_checks/run_all.sh`, and `cd tasks && harbor add --scan .`.
