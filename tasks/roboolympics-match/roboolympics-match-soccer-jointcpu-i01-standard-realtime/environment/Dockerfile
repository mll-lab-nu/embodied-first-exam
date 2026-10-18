# The agent's container: the joint-level seat image of the CPU tier, prebuilt from RoboOlympics pilots/soccer_joint/make_v5_tasks.py
# (python 3.12 + the `game` client, MuJoCo 3.3.7 and the /opt/robot toolkit).
FROM ghcr.io/mll-lab-nu/eai-soccer-joint-cpu:0.1.2@sha256:4b0eb7b85f713b09ddcf8675f5dd7542e54986df50a4ace0c96d9ee13ec0626f
ENV SIM_URL=http://localhost:8000 PRACTICE_URL=http://localhost:8100 SEAT=A
WORKDIR /app
