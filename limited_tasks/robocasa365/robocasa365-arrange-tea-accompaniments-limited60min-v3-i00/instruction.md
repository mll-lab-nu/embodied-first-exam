Complete this robot task: **Take out the milk from the fridge and place it on the tray on the counter. Then take the sugar cube near the tray and place it in the tray.**

This is limited single-episode visual/proprioceptive evaluation. Read /app/API.md and use
`import limited_client as robot`: spec(), observe(), step(action), status().
You can observe RGB and robot state, code, and control incrementally. There is no reset,
restore or second episode. Every attempt and its physical steps remain in the server record.
There are at most 3000 controls in this episode and 3600 seconds (60 minutes) from activation,
including observation, thinking and execution. Native success/termination also ends the episode.
When status().ended is true, stop and finish your response. Otherwise finish when you choose;
the trusted sidecar seals all controls for independent replay. Save optional code/images under
/app/output/. Do not write your own score or try to access hidden simulator data.
