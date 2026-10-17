# The agent's container: the joint-level seat image of the GPU tier, prebuilt from RoboOlympics pilots/soccer_joint/make_v5_tasks.py
# (python 3.12 + the `game` client, MuJoCo 3.3.7 and the /opt/robot toolkit + /opt/train: mjlab 1.6.0, MuJoCo Warp, PyTorch CUDA, rsl_rl 5.4.2; the GPU match world /opt/robot/train2v2).
FROM ghcr.io/mll-lab-nu/eai-soccer-joint-gpu:0.1.2@sha256:8c9c783d8c881e73ca023ebfe3da4eb6c06627ad2c468ceacbab48e34ee002ec
ENV SIM_URL=http://localhost:8000 PRACTICE_URL=http://localhost:8100 SEAT=A
WORKDIR /app
