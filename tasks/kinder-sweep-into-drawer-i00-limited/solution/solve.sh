#!/bin/bash
# No reference solution, on purpose: robot_coding_bench does not require one for new tasks.
# The gate that stays is the nop agent: an episode with no actions cannot reach the goal, so it scores 0.
echo "no reference solution for sweep-into-drawer (limited mode): see this file's header" >&2
exit 1
