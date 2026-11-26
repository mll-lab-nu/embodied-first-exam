# Standard mode: the agent container has NO simulator and no RoboWits code — only Python and the client, on the shared
# pinned client base with the shared pins (embodied_first_exam/standard/client.env, client-requirements.txt).
FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
COPY client-requirements.txt /tmp/client-requirements.txt
RUN pip install --no-cache-dir -r /tmp/client-requirements.txt
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.5.0@sha256:a6c2ac2ede9fe2c1744f9c6e67c6a49de9c5a8b8c2c9ae4f0d774b7dd72662ff /rcb_client.py /rcb1.py /opt/tools/
ENV PYTHONPATH=/opt/tools
# the robot's MCP tools (docs/protocol/standard_mode.md "MCP tools"): the server Harbor starts, efe-robot
COPY efe_mcp /opt/tools/efe_mcp
RUN mkdir -p /app/output
WORKDIR /app
