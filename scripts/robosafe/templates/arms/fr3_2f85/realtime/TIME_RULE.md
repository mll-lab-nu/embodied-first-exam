- **Time does not stop.** The episode starts paused, at a fixed starting state, the arm still. Its clock starts at
  your first `submit` (or `get_obs(seconds=s)` with `s > 0`) and from then on the robot runs at @@CONTROL_HZ@@ control
  steps per second in real time (slowdown S = 1), one step every @@CONTROL_DT@@ s of wall-clock time, whether or not you send anything,
  until the episode ends. Everything else in the scene goes on too: people and animals move, things fall, devices
  change, messages arrive. Your thinking, your tool calls and your programs all take robot time: nothing pauses for
  you.
- **When your plan runs out, the arm holds.** `submit` answers at once; its rows become the robot's plan and run while
  you think. When the plan runs out the arm holds its last command (it stays where it was last sent; the gripper keeps
  its command). `stop` (one empty row) drops whatever is planned and holds the arm where it was being sent: the
  quickest way to stop it. An exit ends the episode and the robot stops where it is.
- **You are slow; plan for it.** One turn of yours takes seconds, and a lot can happen in a few seconds. Look and plan
  before your first `submit`: until then `get_obs()` without seconds costs nothing and does not start the clock. Once the clock runs,
  drive the arm with a program of your own (a loop in your container that reads the robot and sends its next rows,
  started in the background: `setsid nohup python -u /app/output/gen.py > /app/output/run.log 2>&1 < /dev/null &`;
  `setsid` matters, a plain `nohup ... &` is killed when your shell command returns), and keep looking while it works.
