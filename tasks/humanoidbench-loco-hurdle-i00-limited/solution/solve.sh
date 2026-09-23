#!/bin/bash
# No reference solution, on purpose: robot_coding_bench no longer requires one for new tasks.
# The gate that stays is the nop agent: an episode with no actions cannot reach the bar, so it scores 0.
echo "no reference solution for hurdle (limited mode): see this file's header" >&2
exit 1
