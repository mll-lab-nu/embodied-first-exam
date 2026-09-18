# Evaluation protocol

## Unit of evaluation: (family, instance)

A **family** is a simulator scene + goal predicate + primitive API (e.g. robosuite `cube_stack`).
An **instance** is one frozen initial state of that scene, stored as `tests/instance.npz`
(MuJoCo `qpos`/`qvel`/`time` + `qacc_warmstart`). One Harbor task = one instance. Different seeds are
different tasks; repeated attempts on the same instance (`harbor run -k N`) measure agent variance.

## Task types

| `task_type` | Agent deliverable | Grader |
|---|---|---|
| `trajectory` (v0.1) | `/app/output/trajectory.npz`: `(T, 9)` controller-level actions (7 joint targets + 2 gripper), one row per sim step, for **this** instance | open-loop replay from the frozen state in a fresh process, `--repeat 2`; pass iff the goal predicate holds after every replay **and** all final-state hashes agree |
| `policy` (planned) | `/app/output/policy.py` exposing `solve(session)` | run on N held-out instances of the family; reward = success rate |

Rationale for `trajectory` first: coding agents writing general policies is a separate research
problem; a fixed-instance trajectory matches the real-to-sim → closed-loop-execution story and gives a
crisp, cheat-resistant verifier.

## Tiers

`privileged`: primitives may query ground-truth object poses (digital-twin assumption).
`perception`: primitives see only RGB-D through learned models (SAM3, ContactGraspNet). Same instance
files, different base image / API set.

## What the agent gets

Simulator + primitive API (docstrings are the only API docs), unlimited `Session.reset()`, a recorder,
a self-check `Session.replay()` identical to the grader, optional software rendering. It does **not**
get the grader's copy of the instance (`/tests/`), which is why `instruction.md` may not mention it.

## Budget accounting

Report success **and** cost: agent turns, wall-clock, tokens/$ (Harbor records these), and
sim steps / resets (from `Session.status()` and the trajectory length). Different agent CLIs have
different default effort and tools; align them with `--ak reasoning_effort=…`, `--ak max_turns=…`,
budget caps, and `[agent].timeout_sec` before comparing.

## Determinism requirements for a simulator adapter

An adapter may only ship families whose replay is bit-exact across processes. Robosuite/MuJoCo needs
(1) the warm-start restored, (2) controller goals re-anchored, (3) cached observables refreshed after
`set_state`. `python -m rcb.traj selftest --task <family>` checks live-vs-replay hash equality and is
required evidence for a new family. GPU-PhysX simulators (Isaac/OmniGibson) are not deterministic; use
majority-of-N replays or primitive-level trajectories there (see `archive/` notes when they land).
