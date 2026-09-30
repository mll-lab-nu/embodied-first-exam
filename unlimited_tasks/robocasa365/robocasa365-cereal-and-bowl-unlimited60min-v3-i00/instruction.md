Complete this fixed-instance robot task: **Open the cabinet. Pick the cereal and bowl from the cabinet and place them on the counter next to the milk. Then close the cabinet.**

This is unlimited privileged-state coding-agent evaluation. Use `from casa_runtime import Session; s = Session(render=True)`.
Read `/app/action_spec.json` for all 13 ordered channels, effective finite bounds, units and action frames.
`s.observe()` exposes the native instruction, robot joints, full body positions in world metres and WXYZ quaternions,
and the SAME effective action bounds and complete body-part slices as action_spec.json.
`s.step(action)` applies one native control at 20 Hz. `s.render()` returns RGB; `s.result()` returns native diagnostics.
Only robot actions may change the online scene. Do not change physics, task state, runtime or success predicates.
No oracle or one-click task-solving policy is provided.

Mobile Panda uses the final hybrid_mode channel: >0 enables base mode, <=0 arm mode (default -1); grip >0 closes.
For a 13-D Panda, the first seven channels are absolute joint targets in radians. `solve_ik` / `move` provide robot-only
kinematics/control with agent-selected world targets, without object selection or collision planning.
For a 12-D Panda, the first six channels are normalised Cartesian/axis-angle deltas; their frame and scales are in the spec.
GR1 uses absolute pose targets in robot base coordinates (XYZ metres, axis-angle radians), bounded by [-10,10],
followed by two six-channel unscaled Fourier hands in [-3,3]. The listed finger order is authoritative.
GR1 has no mobile base and no hybrid_mode channel. Upstream advertised hand bounds differ and are diagnostic only.

You may inspect privileged state, code, observe, reset, record, replay and debug freely. `reset()` always restores the
same frozen instance. There is NO reset count cap, NO cumulative exploration control cap, and no additional model
call/token/turn quota. All exploration and resets consume the same 3600-second (60-minute) agent wall-clock budget.
Cold start/setup and final independent verifier replay are separate. There is no wrapper-imposed per-trajectory step
cap either. Native simulator termination and numerical/physical validity remain unchanged. Per-Session costs are saved under
/app/output/sim-usage/ (sum all Session records, including unsuccessful exploration).

Submit before the deadline using `s.save('/app/output/trajectory.npz')`. This saves the current episode's native action
annotations and actual actuator controls, bound to the frozen instance. Only the final submitted trajectory counts.
The trusted verifier replays it twice in fresh processes and requires matching final states and native success.
RoboCasa365 uses ever-success; legacy RoboCasa and GR1 require final native success. Your own success claim does not score.
All agent processes must stop at completion/deadline before independent verification. Optional code/images go under /app/output/.
