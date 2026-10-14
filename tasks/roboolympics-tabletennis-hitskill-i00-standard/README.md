# roboolympics-tabletennis-hitskill-i00-standard

| | |
|---|---|
| Benchmark | RoboOlympics |
| Mode | standard (`skilleval-api-test/1`) |
| Twin | — (none: a task RoboOlympics exports with its own service, PROTOCOL §4c) |
| Simulator / robot | `mujoco` / `franka-panda` |
| Family / instance | `tabletennis_hit_skill` |
| Oracle | `full` — solution/: our reference skill (lowlevel/reference, the toolkit only); see the export report for its rate on the development set |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f` |

## Task
Implement `/app/output/skill/hit.py`: hit(t, pos, normal, vel, *, state, spec) -> one low-level command ({'type': 'traj', 'k0', 'q': rows of 9 targets} | {'type': 'slew', 'q', 'speed'} | {'type': 'hold'}) or None; the contact at control step state['step'] + round(t / 0.01) (in the API test the command takes effect at state['step']; in the match when your call returns, spec timing).

## Difficulty
Our reference skill reaches the line on this set; the platform's own implementation fulfils every request (each
request was kept only if it does). Development requests from development seeds [1041, 1042, 1049, 1050, 1057, 1058, 2043, 2044, 2051, 2052, 2059, 2060, 3045, 3046, 3053, 3054, 3061, 3062, 4047, 4048, 4055, 4056, 4063, 4064] (not the official
hidden requests).

## Reference solution
`solution/skill/`: solution/: our reference skill (lowlevel/reference, the toolkit only); see the export report for its rate on the development set.

## Verification
Separate sandbox, no network: `skilleval.evaluate` (the sport's API test, no competition test) on the development
requests; `tests/engineer_grade.py` writes reward.json (success = rate >= 0.7, deterministic answers).

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 4 GB | 4 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: RoboOlympics' exported skill tasks (scripts/roboolympics/exported.toml; ws-1/2, 2026-10): no sim service, the agent 2 CPUs; the verifier runs the simulator and the skill; CPU only
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 4 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 4 GiB memory. Limits measured: design defaults of RoboOlympics' exported tasks (no sim service).

## Details

### Notes
Source: RoboOlympics task `tabletennis-match-wallclock-program-lowlevel-standard` (the low level's in-loop match), revision `wallclock-15+duel-wallclock-12+low-inloop-1+core-0.2`;
contract, toolkit, evaluator and request pipeline unchanged; only the request set is the development one.
