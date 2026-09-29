"""Version 1 transition data: measured states and submitted commands are separate.

One file contains one episode, including any explicitly restored branches.
``transitions/<index>`` stores the complete Transition fields. In particular,
``action`` is the accepted command, ``observation`` is its input state, and
``next_observation`` is its resulting state. No action is inferred from motion.
Episode and branch IDs, both state IDs, control/physics counters, and durations
are required. Attributes record schema, completion status, and episode metadata.

The former next-observed-pose training format is intentionally not compatible.
"""

SCHEMA_VERSION = "2.0.0"

TRANSITION_FIELDS = (
    "episode_id", "branch_id", "state_id", "previous_state_id", "control_step",
    "physics_step", "sim_time_s", "physics_steps", "action_duration_s",
    "observation", "action", "next_observation", "reward", "terminated",
    "truncated", "info",
)
