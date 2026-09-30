# RoboCasa validation

Validated on 2026-09-19 with Docker, CPU MuJoCo 3.2.6 and OSMesa rendering. RoboCasa v0.2 source is pinned at `756598a5be52e052339bb2d957426e39015c2afb`; robosuite is 1.5.1. This is the native `NavigateKitchen` environment, layout 0 / style 0 / seed 0, with full kitchen assets. Source fixture: `cab_4_main_group`; target: `dishwasher_main_group`, target position `(2.075, -0.8, 0)`, target yaw `pi/2`.

## Oracle and replay checks

The development coding-agent reference controller uses only `Session.step` robot actions. It scored 1 with 156 control actions (3,900 physics steps); final planar distance was `0.14259914783458216` m and orientation cosine `0.999915703697793`. Native initial success was 0. RoboCasa's `reward()` is always 0 in this native family; success comes from `_check_success()`.

The live solve, two separate verifier workers, and offscreen-rendered replay produced the same raw final-state SHA-256:

```
d94a7c00827c4cff8d0066e2fa7e7830f8f1a54f5615d6205a5ce11852fd9b6b
```

`reference_oracle/` preserves the generated code, trajectory, live-run hash, numeric verifier output and rendered replay diagnostics. `reference-oracle.mp4` is its actual 640x480 H.264 replay at 20 fps (157 frames, 7.85 seconds), visually checked.

Actual Harbor baseline runs:

| Agent | Job / trial | Success | Deterministic | Grader error |
|---|---|---:|---:|---:|
| oracle | `robocasa-oracle / robocasa-kitchen-navigation-i00__GuV3E9P` | 1 | 1 | 0 |
| nop | `robocasa-nop / robocasa-kitchen-navigation-i00__rDJdhpX` | 0 | n/a | 0 |

The no-op trial reported `missing_trajectory=1`. The oracle was subsequently regraded with the final hardened archive loader and retained the same success, diagnostics and state hash. Raw logs are retained in the repository's ignored `jobs/` directory. Harbor's Docker compose artifact-copy path fallback was exercised and successfully collected the output.

## Independent coding-agent run

An independent Harbor Codex trial (`robocasa-codex-reference / robocasa-kitchen-navigation-i00__zkFKbec`) used Codex 0.155.1, `openai/gpt-6-astra`, reasoning effort `high`, and only the task's normal agent environment and instruction. It created its own waypoint-based controller and replayable artifact; it was not given the oracle solution.

Harbor returned `success=1`, `deterministic=1`, `grader_error=0`, with 378 control actions / 9,450 physics steps. Final planar error was `0.10798426049718683` m; orientation cosine was `0.9999996602802462`. Its self-check and both verifier processes agreed on the exact raw state hash:

```
837d495ea0b5d19f230ae43b8a397dfb7e048c459479606d221d9d8688377187
```

The agent ran for 107.78 seconds (228.57 seconds including setup and grading). Harbor reported 278,751 input tokens, including 260,736 cached tokens, 1,687 output tokens, and estimated cost USD 0.525236. These are the harness's usage/cost values, not a separately verified bill.

`reference_run/` preserves its exact generated `generate.py`, submitted `trajectory.npz`, agent self-check, sanitized Harbor provenance/metrics, and video replay diagnostics. `reference.mp4` is rendered from that exact independent trajectory using the final verifier-side tooling, with the same final-state hash. The video is 640x480 H.264, 20 fps, 379 frames / 18.95 seconds. Full agent transcripts and Harbor raw results remain under ignored `jobs/robocasa-codex-reference/`.

Reproduce the independent trial with an existing Codex login:

```bash
CODEX_FORCE_AUTH_JSON=1 harbor run -p tasks/robocasa-kitchen-navigation-i00 -a codex -m openai/gpt-6-astra --ak reasoning_effort=high
```

## Archive and contract checks

`tests/test_archive.py` passes four tests covering valid archives, invalid shapes/dtypes/nonfinite/out-of-range actions, forged trillion-row NPY headers, and unexpected archive members. The loader checks the NPY header and exact payload length before allocating an array. Both verifier tooling and scene copies match the agent-facing copies byte-for-byte. Structure, task fields, pinned Docker base and instruction contract checks pass using Python 3.12.

The simulator assets are downloaded only while building the image; replay and grading do not access the network. The original fixture archive is pinned to mirror revision `866be1d2158a6486af2211156b83eeaeb031f54f`, SHA-256 `bd993f47d0ae5f5f3d89cf5f9fc28d55ceb878359c49136d30052de0bb1ef231`. Textures are pinned to official revision `1b92c3d02ca4354984fec961357db0bff7b32166`, SHA-256 `ba3a4dcef96e199cbd601c7cdb7eb46077fb6672611b7ac74c25a191bf0be392`.
