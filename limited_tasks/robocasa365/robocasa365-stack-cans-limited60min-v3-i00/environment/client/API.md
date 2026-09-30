# Limited RoboCasa client
Only `spec()`, `observe(camera=None)`, `step(action)`, `status()` are public.
Read spec() for all channels, effective bounds, units, frames and native camera names.
observe() returns RGB uint8, intrinsic K, camera_to_world (OpenCV optical frame, metres),
and robot-only joints and end effectors. Joint types follow MuJoCo: 0 free, 1 ball, 2 slide, 3 hinge;
slide positions are metres, hinge positions radians; quaternion components are dimensionless.
It also saves /app/output/limited-view-<camera>.jpg: open it with your native image viewer.
No hidden object poses, seed, instance config, reward, predicates, reset, snapshots, oracle or submit endpoint.
step(action) executes ONE validated control, permanently recorded, including failed attempts.
status() only reports liveness, counts and remaining seconds, never hidden success.
One continuous episode and 3600 seconds from activation. End when status().ended is true.
No success statement or agent-written trajectory is used for scoring.
