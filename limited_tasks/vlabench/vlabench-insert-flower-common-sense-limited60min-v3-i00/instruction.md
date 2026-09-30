Complete this robot task: **Insert the flower with ... into vase.**

This is limited, visual/proprioceptive, single-episode evaluation. Read /app/API.md.
Use `import limited_client as robot`: only spec(), observe(), step(action), status().
Observe the images and robot state, write code and control the robot incrementally.
There is no reset or second episode. All failed actions remain in the server record.
The deadline is 3600 seconds (60 minutes), including observation, coding and execution.
The repository episode/trajectory cap is 4000 controls. Stop sending controls once ended.
Do not attempt to change simulator state or access hidden scoring information.
When finished, simply end your response. The trusted service automatically seals your
complete episode for independent replay; no submit call or agent-authored reward is used.
You may save useful scripts and images under /app/output/.
