# Private static initialization for the agent episode

This bundle holds the fixed `compact_single_arm_v1` collision/visual assets,
physical wire centerline, robot configuration, and one tick-zero initialization.
It is private environment input and must never be exported to the solver.

`wire.urdf` and `wand.urdf` are exact independent copies from the archived
`2026-09-18_compact_single_arm_v1/source_evidence/assets/` instance. They contain
only primitive collision/visual geometry and inertia. `initial_state.json`
keeps the physical rail coordinates and initial state, excluding the orientation
profile, arm guide, reference motion, future poses, and solution phases.
It records asset hashes and a provenance hash of the original tick-zero record.
The loader additionally pins the complete initialization file's SHA-256.

The files were extracted once during adapter development. Creating an episode
reads only this bundle and shared robot/world assets; it does not depend on the
archive, `robot_seed.json`, `reference_path.npz`, or any solution planner.
The static loader cannot supply a reference pose at an arbitrary progress value.

The initial finger half gap is 7.1 mm, with a zero-gap closing target under the
bounded Robotiq torque limit. There is no initial settling step, weld, or other
assisted grasp. Initial ring threading and pregrasp are declared task conditions;
actual holding develops through contact friction after execution starts.

Physical qualification of the historical controller is not transferred to the
new adapter. See [adapter documentation](../../../../../docs/develop/modules/buzz_wire_agent_adapter_zh.md).
