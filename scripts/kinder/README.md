# scripts/kinder — where the KinDER tasks come from

Every `tasks/kinder-*` directory is generated from this one; nothing in them is edited by hand (their `results/` aside).
What they are and why: `docs/benchmarks/kinder.md`.

| file | what it is |
|---|---|
| `subset.toml` | **the source of truth**: which KinDER environments, each goal's sentence, `room_camera` where upstream's is overhead, each task's difficulty and the evidence for a task without an oracle |
| `facts.json` | what the simulator is the authority on: each scene's digest, the action space, costs, the checks below. Written by `measure` only |
| `shared/rcb_kinder.py` | the tooling: frozen instance (in KinDER's MimicLabs lab), recording, deterministic replay, camera images. Copied into every task |
| `shared/grade.py` | the privileged-mode verifier: two replays in a fresh process, both must reach the goal and end in the same state |
| `shared/standard/` | standard mode (`eai-standard/2.1`): `rcb_service.py` (the simulator-agnostic service: endpoints, RCB1, episode, crash recovery, finalize), `server.py` (the adapters, one per robot: sensors, odometry frame, clipping), `rcb_client.py` and `rcb1.py` (the agent's client; its docstring is the API reference), `grade.py` (the verifier) |
| `oracles/<family>/<mode>/` | a task's reference solution, where it has one (the `dynamo` fixture); `render` copies it to `solution/` |
| `templates/`, `templates/standard/` | everything the tasks have in common, with `{{placeholders}}` |
| `configs/codex-openrouter.yaml` | the Harbor job config the recorded runs use: Harbor's own Codex agent on OpenRouter |
| `tests/test_standard_service.py` | the standard-mode service, client and verifier against a toy simulator (`python -m unittest discover -s scripts/kinder/tests`; numpy, requests) |

```bash
./gen_tasks.py render                # rewrite every task dir from the sources   (no simulator needed)
./gen_tasks.py check                 # tasks/ must be what render writes; no task names another
./gen_tasks.py measure [family]      # pin, check and time each instance       (image + GPU, see gen_tasks.py)
./gen_tasks.py verify                # re-measure; fail on drift, a passing nop, a non-deterministic replay
```

`measure` checks, per task: holding still for a whole episode does not reach the goal; a replay is bit-identical in
process and in a fresh one; the real standard-mode service clips an out-of-range move, serves wrist depth, returns to
the t=0 images after a reset (the optional capability), comes back from a crash in the same episode, and finalizes
with a deterministic replay and a video. Adding a task: a `[[task]]` block in `subset.toml`, then `measure <family>`,
`render`, `check`, `ci_checks/run_all.sh`, and `cd tasks && harbor add --scan .`.
