# Embodied First Exam tasks

Harbor tasks in which a coding agent controls a simulated robot on a frozen scene instance, one directory per task
under `tasks/<benchmark>/`, in privileged, standard or realtime mode. In privileged mode the agent delivers a
trajectory (or code) that a separate verifier replays; in standard and realtime mode it drives the robot through a
simulator service it cannot open, and the live episode is graded (realtime: on a clock that does not stop). See the
repository README for running them and `docs/protocol/` for the contract and scoring.
