# The agent's container: the joint-level seat image of the CPU tier, prebuilt from Embodied Olympics pilots/soccer_joint/make_v5_tasks.py
# (python 3.12 + the `game` client, MuJoCo 3.3.7 and the /opt/robot toolkit).
FROM ghcr.io/mll-lab-nu/efe:embodied-olympics-match-soccer-joint-cpu-0.1.2@sha256:4b0eb7b85f713b09ddcf8675f5dd7542e54986df50a4ace0c96d9ee13ec0626f
# the eai-standard/2.x client (docs/protocol/standard_mode.md): `from rcb_client import Robot`
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.5.0@sha256:ff602baf1ef852d21ecf0152d94cf210c8b691a5bdaa88d00dc381f6150b98cb /rcb1.py /rcb_client.py /opt/tools/
ENV PYTHONPATH=/opt/tools
# the robot's MCP tools (docs/protocol/standard_mode.md "MCP tools"): the server Harbor starts, efe-robot
COPY efe_mcp /opt/tools/efe_mcp
ENV SIM_URL=http://localhost:8000 PRACTICE_URL=http://localhost:8100 SEAT=A
WORKDIR /app
