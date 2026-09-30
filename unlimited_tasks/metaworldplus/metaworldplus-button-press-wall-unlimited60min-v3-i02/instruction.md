Complete this fixed-instance robot task: **Press the button behind the wall.**
Native environment: `button-press-wall-v3` (Meta-World v3, reward v2, Sawyer arm).

This is privileged-state coding-agent evaluation. Use `from mw_runtime import Session; s = Session()`.
`s.observe()` returns the native observation, robot TCP, goal, body poses (world metres, WXYZ
quaternions), joint positions/velocities and the gripper state.
`s.step([dx, dy, dz, grip])` applies the native four-dimensional action in [-1, 1] at 80 Hz:
XYZ is scaled Cartesian displacement (native scale 0.01 m), fixed wrist; grip +1 closes, -1 opens.
`s.move(world_xyz, gripper=-1, steps=30)` is simple proportional XYZ control, without collision
planning or automatic object selection. `s.render()` returns RGB. `s.result()` reports native status.
Native v3/reward-v2 success counts if it is attained at any control of the submitted trajectory;
dense reward is diagnostic only.

You may write programs, execute, inspect, record and replay, and call `s.reset()` to restore the
identical initial instance as often as you like, with any number of Sessions. No episode or submitted-trajectory control cap applies; the native success predicate is unchanged. There is no reset,
cumulative-control, token or turn budget; everything counts toward the 3600-second (60-minute)
wall-clock deadline. Simulator usage is logged per Session under /app/output/sim-usage/.
Only robot actions may change the scene: do not modify simulator state, runtime code, task
predicates or reward files.

Submit before the deadline with `s.save('/app/output/trajectory.npz')`, which stores the controls
of that Session's current episode (since its last reset). Run simulator work synchronously: when
you finish, or at the deadline, all processes in the container are terminated before verification.
A trusted instance and the native checker independently replay the submitted controls twice in
fresh processes and require identical final states; your own success claims are not used.
Optional programs and images also belong in /app/output/.
