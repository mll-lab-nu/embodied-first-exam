#!/bin/bash
# Grader: replay the agent's trajectory from the frozen instance (tests/ copy) in a fresh process.
cd /opt/cap-x
python -m rcb.grade --family cube_stack --instance /tests/instance.npz --traj /app/output/trajectory.npz --repeat 2 \
  2> /logs/verifier/grade.log
