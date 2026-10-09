# bigym2-reach-target-dual-i00-privileged

| | |
|---|---|
| Benchmark | BiGym 2.0 |
| Mode | privileged |
| Twin | `bigym2-reach-target-dual-i00-standard` |
| Simulator / robot | `bigym2` / `unitree-g1-dex1` |
| Family / instance | `reach-target-dual` / seed 0 |
| Oracle | `none` — no reference solution (BiGym 2.0 ships no expert or planner; its demonstrations and its agents' programs stay off the agent's network); positive example graded 1 by the separate verifier: bigym2-reach-target-dual-i00-pri__fxPRBTg (run codex-gpt6_luna-medium, 2026-10-08, on an earlier text of the privileged task; regraded by its current verifier); human review in PR #123 |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-bigym2:0.1.1` |

## Task
Touch the red sphere with your left hand and the green sphere with your right hand at the same time. (BiGym 2.0 `reach_target_dual`, a Unitree G1 humanoid whose legs and waist NVIDIA's GR00T whole-body controller drives.)

## Difficulty
Both arms at once, each to its own 5 cm ball, while the controller balances the body; the shortest task (14 s).

## Reference solution
None. BiGym 2.0 has no scripted expert or planner; its human demonstrations and its coding agents' programs are public
on the Hugging Face Hub and never reach the agent (no network but the model APIs; seed 0 is none of their seeds).

## Verification
`tests/grade.py` replays `/app/output/trajectory.npz` from the frozen instance in two fresh processes (`rcb_bigym2.py
replay`: upstream's official env, one step per row until upstream ends the episode). Pass iff upstream's `is_success`
holds in both (the task's success held for 1 s, no fall) and both end in the same state. Success condition: the point between the left gripper's two finger pads is inside the red sphere and the right gripper's inside the green sphere at the same time: each within 0.05 m of its sphere's centre (the spheres' radius).
No oracle; human review in PR #123 (PROTOCOL §2.7).

## Details
| | |
|---|---|
| Upstream | BiGym 2.0 (swirl-uk/BiGym2 at 93ad4b3, bigym 1.0.0, Apache-2.0), task `reach_target_dual` ("reaching"), official configuration |
| Instance | `environment/instance.json` = `tests/instance.json`: the task reset with seed 0, t = 0 state hash `c043250ab851bae093876865b52384500b12b477` |
| Horizon | 700 control steps (14 s at 50 Hz), upstream's budget for this task |
| Action | 20 floats per control step (`instance.json` `t0.layout`) |
| Tooling | `environment/rcb_bigym2.py` = `tests/rcb_bigym2.py` (scripts/bigym2/shared/) |
