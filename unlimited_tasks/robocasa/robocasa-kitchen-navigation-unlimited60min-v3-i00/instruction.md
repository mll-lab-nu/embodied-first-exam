Move the PandaOmron mobile manipulator to the designated fixture in this frozen RoboCasa `NavigateKitchen` scene. Success uses RoboCasa's native predicate: the mobile base must be within 0.20 m of the target position in the floor plane and face the target yaw with cosine error at least 0.98. You may inspect the full simulator state.

Write `/app/output/trajectory.npz`, a NumPy archive containing only `actions`: a finite numeric array of shape `(T, 3)`, with `1 <= T` and every value in `[-1, 1]`. Also save your generating code under `/app/output/` for reference. The trajectory is replayed open-loop from the provided frozen instance; only robot actions may complete the goal.

Use `/app/casa_traj.py`:

```python
from casa_traj import Session
s = Session()
print(s.observe())
s.step([0.2, 0.0, 0.0])
s.save('/app/output/trajectory.npz')
s.close()
```

`observe()` returns base and target positions in world coordinates (meters), base and target yaw in radians, the target fixture name, native success, and simulation/reset counts. Positions use the MuJoCo world frame with Z up. There are no quaternion action fields.

Each action is the native mobile-base control triple `[local_x, local_y, yaw]`, with planar translation relative to the current base frame and yaw about +Z. `Session.step` inserts them into the PandaOmron base controller, keeps the arm/torso controls zero, enables native base mode, and advances one 20 Hz control step (25 MuJoCo physics steps). Translation is bounded by 1 m/s and yaw by 1.5 rad/s before physical friction and actuator dynamics.

`Session.reset()` restores the same frozen scene and re-anchors the controllers. `NativeSession().env` exposes native fixture geometry, robot state and controllers; import NativeSession from casa_traj for this advanced local API. This additional initialization counts toward agent time. `Session(render=True).frame()` gives a 640x480 RGB frame. To self-check a saved trajectory in a new process:

```bash
python /app/casa_traj.py replay --traj /app/output/trajectory.npz
python /app/casa_traj.py replay --traj /app/output/trajectory.npz --video /app/output/rollout.mp4
```

Only robot actions may change the online scene. Do not modify physics or task predicates; submit robot controls for independent replay.

Unlimited exploration: no reset count, cumulative exploration or per-trajectory wrapper step cap. Agent time is 3600 seconds (60 minutes); all observation, coding and resets count. Native physics and success conditions are unchanged.
