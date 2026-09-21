# Compact single-arm Buzz Wire seed

The coding-agent episode uses the separate [static bundle](agent_episode/README.md),
which contains no reference poses or arm guide. Its runtime does not read
`robot_seed.json`; see the [adapter documentation](../../../../docs/develop/modules/buzz_wire_agent_adapter_zh.md).

`robot_seed.json` provides the complete geometric layout, ring-orientation profile,
fixed grasp transform, and a continuous arm guide for the compact
`spatial_maze_robot_v3` instance. The guide is a planning seed, not a physical
execution or an acceptance report.

The scene uses the original fixed Panda mount and original joint limits.
`robot_plan` resolves every sample against those limits, checks full robot/fixture
and robot/tool collision geometry, and exports the exact rigid assets. It accepts
release before the witness end only after all bends, on the final downward post.
The runtime must independently pass live contact dynamics and terminal settling.

The 743 × 527 × 25 mm base carries horizontal switchbacks, a broad inclined height
fold and a one-turn spiral. The ring has a 22 mm centerline radius, 1.8 mm tube
radius and a flat rectangular grip. The orientation profile permits the ring to
tilt relative to the wire while maintaining certified tool clearance and linking.
This allows the physical wrist to negotiate the spatial route without extending
joint limits.

Reproduce with a new output directory:

```bash
OPENBLAS_NUM_THREADS=1 PYTHONPATH=. .venv-gs121-nyx/bin/python \
  -m topogym.tasks.buzz_wire_3d.robot_plan \
  --seed-plan assets/tasks/buzz_wire_3d/compact_single_arm_v1/robot_seed.json \
  --output runs/environment_bootstrap/buzz_wire_3d/compact_recheck/plan
```

See [task documentation](../../../../docs/develop/tasks/buzz_wire_3d_zh.md) for
execution, stability comparison, synchronized rendering and archiving.
