#!/bin/bash
# No reference solution exists for this task, on purpose.
#
# Requiring one would cap the benchmark at what we can already solve, which systematically removes every
# interesting task. This task's difficulty is evidenced externally instead: published RL results reach
# negative of success_bar.
#
# What is verified in place of an oracle:
#   * nop floor   -- an all-zero trajectory scores -2191.95 against a bar of 1500, so
#                    the task cannot be passed by submitting nothing.
#   * determinism -- replaying the same actions twice in one process gives a bit-identical final state.
# Both are checked by `scripts/humanoidbench/gen_tasks.py verify`.
echo "no reference solution for package: see this file's header" >&2
exit 1
