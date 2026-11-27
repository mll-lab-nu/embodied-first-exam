# The agent's container: the joint-level seat image of the GPU tier, prebuilt from Embodied Olympics pilots/soccer_joint/make_v5_tasks.py
# (python 3.12 + the `game` client, MuJoCo 3.3.7 and the /opt/robot toolkit + /opt/train: mjlab 1.6.0, MuJoCo Warp, PyTorch CUDA, rsl_rl 5.4.2; the GPU match world /opt/robot/train2v2).
FROM ghcr.io/mll-lab-nu/efe:embodied-olympics-match-soccer-joint-gpu-0.1.3@sha256:7dee4b99af4bd5ec5c0d974176d09c6452c581645fc07295889c8fb4c8b22c69
# the eai-standard/2.x client (docs/protocol/standard_mode.md): `from rcb_client import Robot`
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.6.0@sha256:5e5e605d9f3cc2a4a0efc4ffb1f277278f8f77f225cc6ff60d00d15b4cb3b515 /rcb1.py /realtime/rcb_client.py /opt/tools/
ENV PYTHONPATH=/opt/tools
# the robot's MCP tools (docs/protocol/standard_mode.md "MCP tools"): the server Harbor starts, efe-robot
COPY efe_mcp /opt/tools/efe_mcp
ENV SIM_URL=http://localhost:8000 PRACTICE_URL=http://localhost:8100 SEAT=A
WORKDIR /app
