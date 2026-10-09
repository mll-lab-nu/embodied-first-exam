# bigym2-pick-box-i00-privileged

| | |
|---|---|
| Benchmark | BiGym 2.0 |
| Mode | privileged |
| Twin | `bigym2-pick-box-i00-standard` |
| Simulator / robot | `bigym2` / `unitree-g1-dex1` |
| Family / instance | `pick-box` / seed 0 |
| Oracle | `none` — no reference solution (BiGym 2.0 ships no expert or planner; its demonstrations and its agents' programs stay off the agent's network); no positive example yet; human review in PR #123 |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-bigym2:0.1.1` |

## Task
Pick the cardboard box up from the side table and gently set it down on the kitchen counter. (BiGym 2.0 `pick_box`, a Unitree G1 humanoid whose legs and waist NVIDIA's GR00T whole-body controller drives.)

## Difficulty
Whole-body carry: squat to a low side table, lift a 3 kg box with two palmless grippers, turn and walk, set it on the counter.

## Reference solution
None. BiGym 2.0 has no scripted expert or planner; its human demonstrations and its coding agents' programs are public
on the Hugging Face Hub and never reach the agent (no network but the model APIs; seed 0 is none of their seeds).

## Verification
`tests/grade.py` replays `/app/output/trajectory.npz` from the frozen instance in two fresh processes (`rcb_bigym2.py
replay`: upstream's official env, one step per row until upstream ends the episode). Pass iff upstream's `is_success`
holds in both (the task's success held for 1 s, no fall) and both end in the same state. Success condition: the box rests on the kitchen counter's top: touching it, its centre above the counter top, its lowest point within 0.03 m of the top's height; held by neither gripper.
No oracle; human review in PR #123 (PROTOCOL §2.7).

## Details
| | |
|---|---|
| Upstream | BiGym 2.0 (swirl-uk/BiGym2 at 93ad4b3, bigym 1.0.0, Apache-2.0), task `pick_box` ("kitchen counter"), official configuration |
| Instance | `environment/instance.json` = `tests/instance.json`: the task reset with seed 0, t = 0 state hash `035675418f181c61150ace3b9912d9828d55d87a` |
| Horizon | 4400 control steps (88 s at 50 Hz), upstream's budget for this task |
| Action | 21 floats per control step (`instance.json` `t0.layout`) |
| Tooling | `environment/rcb_bigym2.py` = `tests/rcb_bigym2.py` (scripts/bigym2/shared/) |
