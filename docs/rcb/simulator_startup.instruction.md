# Simulator startup and command lifecycle

Compatibility note: current TopoGym tasks already include startup guidance in their fixed `instruction.md`.
This file is retained for older commands that explicitly append it; current tasks do not require this extra file.

Keep the original task objective, interaction mode, simulator/sensor configuration, and agent wall-clock budget.
These instructions concern startup and waiting for commands; they do not grant extra time or additional simulator access.

- Initialization can take minutes. Recent Cast Coil starts on this host took about 120 seconds; this is an observation,
  not a deadline or a guarantee for other tasks, machines, or loads. Initialization may produce little output while
  building the scene or compiling kernels. Use `python -u` for scripts so their progress is not buffered.
- A command tool's wait/yield interval (for example, `yield_time_ms=30000`) is not the command's lifetime.
  If a command is still running, retain its process/session identifier and continue waiting for that same command.
  With Codex's `exec_command`, expose the complete result, including `session_id` and `exit_code`, rather than only
  `output` (for example, `text(r)` instead of only `text(r.output)`). Continue a running command with `write_stdin`
  using its returned `session_id` and no input. An outer JavaScript wrapper saying `Script completed` does not prove
  that the Python process has exited. Use the corresponding wait/status operation if another command tool is provided.
- Do not rerun an initialization command merely because its first wait returned without an `instance ready` message.
  Inspect or wait for the original command. Start a replacement only after confirming the original process has exited;
  if cancellation is necessary, stop only your own identified process and confirm its exit before retrying.

For unlimited tasks:
- Keep at most one live simulator process in this trial at a time. A new Python process calling `Session(...)`
  creates another scene and consumes additional GPU memory. Separate replay/render CLI commands also create scenes.
- Reuse the initialized Session for observations, actions, reset, and replay. Avoid separate initialization-only probes;
  put the first useful actions and trajectory save in the same script that initializes the simulator.
- Initialization consumes the agent budget. Save an initial real trajectory as soon as practical and keep saving progress.

For limited tasks:
- Connect with `Robot()` and let its existing retry loop wait for the simulator service (default connection budget:
  600 seconds, still subject to the actual agent deadline). Do not try to start or rebuild a simulator yourself.
- Reconnecting a client accesses the same episode; it does not reset the world. While an action request is still
  running, wait for its original command rather than resubmitting the same actions, which could execute them twice.
