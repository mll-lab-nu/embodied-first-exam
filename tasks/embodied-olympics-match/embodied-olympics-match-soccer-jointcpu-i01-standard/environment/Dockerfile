# The agent's container: the joint-level seat image of the CPU tier, prebuilt from Embodied Olympics pilots/soccer_joint/make_v5_tasks.py
# (python 3.12 + the `game` client, MuJoCo 3.3.7 and the /opt/robot toolkit).
FROM ghcr.io/mll-lab-nu/efe:embodied-olympics-match-soccer-joint-cpu-0.1.2@sha256:4b0eb7b85f713b09ddcf8675f5dd7542e54986df50a4ace0c96d9ee13ec0626f
# the eai-standard/3.0 client (docs/protocol/eai-standard.md): `from rcb_client import Robot`
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:a99b04e29e96564b62a2c335b191405d8a94785d6efea2bb5765acbefde92383 /rcb1.py /rcb_client.py /opt/tools/
ENV PYTHONPATH=/opt/tools
# the robot's MCP tools (docs/protocol/eai-standard.md "MCP tools"): the server Harbor starts, efe-robot
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:a99b04e29e96564b62a2c335b191405d8a94785d6efea2bb5765acbefde92383 /mcp/server.py /mcp/rcb_tools.py /mcp/schema.py /mcp/workspace.py /mcp/suites.py /opt/tools/efe_mcp/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:a99b04e29e96564b62a2c335b191405d8a94785d6efea2bb5765acbefde92383 /mcp/schema/tools.json /opt/tools/efe_mcp/schema/
COPY efe_mcp /opt/tools/efe_mcp
ENV SIM_URL=http://localhost:8000 PRACTICE_URL=http://localhost:8100 SEAT=A
WORKDIR /app
