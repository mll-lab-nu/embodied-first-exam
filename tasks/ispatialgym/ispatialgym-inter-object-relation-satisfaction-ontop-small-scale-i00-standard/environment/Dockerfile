# Standard mode: the agent container has NO simulator and no iSpatialGym code — only Python, the client and the goal
# image. The base image and the pip pins are the shared eai-standard client (embodied_first_exam/standard/client.env,
# client-requirements.txt).
FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
COPY client-requirements.txt /tmp/client-requirements.txt
RUN pip install --no-cache-dir -r /tmp/client-requirements.txt
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:497a2b864b3a1aaf1f60206dc14f08a0f99960037f0e54be3d4bc2e39f5adba4 /rcb_client.py /rcb1.py /opt/tools/
ENV PYTHONPATH=/opt/tools
# the robot's MCP tools (docs/protocol/standard_mode.md "MCP tools"): the server Harbor starts, efe-robot
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:497a2b864b3a1aaf1f60206dc14f08a0f99960037f0e54be3d4bc2e39f5adba4 /mcp/server.py /mcp/rcb_tools.py /mcp/schema.py /mcp/workspace.py /opt/tools/efe_mcp/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:497a2b864b3a1aaf1f60206dc14f08a0f99960037f0e54be3d4bc2e39f5adba4 /mcp/schema/tools.json /opt/tools/efe_mcp/schema/
COPY efe_mcp /opt/tools/efe_mcp
COPY --from=ghcr.io/mll-lab-nu/efe:ispatialgym-goals-files-0.1.0@sha256:a5b14edb2270793a3d97edeb2ff151646532f30221fe40b55867d33732c97e7f /inter-object-relation-satisfaction-ontop-small-scale-i00/goal.png /app/goal.png
RUN mkdir -p /app/output
WORKDIR /app
