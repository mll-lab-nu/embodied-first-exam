# The agent's container: the joint-level seat image of the CPU tier, prebuilt from RoboOlympics pilots/soccer_joint/make_v5_tasks.py
# (python 3.12 + the `game` client, MuJoCo 3.3.7 and the /opt/robot toolkit).
FROM ghcr.io/mll-lab-nu/eai-soccer-joint-cpu:0.1.0@sha256:93e589d9bb21f2ace711ae8e2652f4179dd5ce0ccd128b3bd833d00dcd4faa8c
ENV SIM_URL=http://localhost:8000 PRACTICE_URL=http://localhost:8100 SEAT=A
WORKDIR /app
