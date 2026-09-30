Complete this robot task: **Push the object around the wall to the target.**
Native environment: `push-wall-v3` (Meta-World v3 Sawyer arm).

This is limited, visual/proprioceptive, single-episode evaluation. Read /app/API.md.
Use `import limited_client as robot`: only spec(), observe(camera), step(action), status().
Observe the images and robot state, write code and control the robot incrementally.
There is no reset or second episode. Every accepted control stays in the server record.
The deadline is 3600 seconds (60 minutes) from activation, including observation, thinking,
coding and execution. The native episode cap is 500 controls at 80 Hz. The service ends the
episode when a native termination condition is reached, after 500 controls, or at the deadline;
stop sending controls once status() reports ended.
Do not attempt to change simulator state or access hidden scoring information.
When finished, simply end your response. The trusted service seals your complete episode for
independent replay; no submit call or agent-authored result is used.
You may save useful scripts and images under /app/output/.
