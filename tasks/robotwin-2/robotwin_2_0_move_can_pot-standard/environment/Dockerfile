# Standard mode: the agent container has NO simulator and no RoboTwin code — only Python and the client.
FROM docker.io/library/python:3.12-slim
RUN pip install --no-cache-dir requests numpy pillow scipy
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.9.0@sha256:2cf5b6f826d698eaa0dcddf1561e6c673ca0ddabac2c3868d823598eb3cb75b6 /rcb1.py /sidecar/clients/compact/rcb_client.py /opt/tools/
ENV PYTHONPATH=/opt/tools
# the robot's MCP tools (docs/protocol/eai-standard.md "MCP tools"): the server Harbor starts, efe-robot
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.9.0@sha256:2cf5b6f826d698eaa0dcddf1561e6c673ca0ddabac2c3868d823598eb3cb75b6 /mcp/server.py /mcp/rcb_tools.py /mcp/schema.py /mcp/workspace.py /opt/tools/efe_mcp/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.9.0@sha256:2cf5b6f826d698eaa0dcddf1561e6c673ca0ddabac2c3868d823598eb3cb75b6 /mcp/schema/tools.json /opt/tools/efe_mcp/schema/
COPY efe_mcp /opt/tools/efe_mcp
# the client sends float32 action rows (RoboTwin's)
ENV RCB_ACTION_DTYPE=float32
RUN mkdir -p /app/output
WORKDIR /app
