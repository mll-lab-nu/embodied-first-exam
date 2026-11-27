# The player's container: no simulator, only Python with the standard client pins and the generic `game`
# command of the core (core/game.py, the sport's shortcuts filled in by tools/generate.py).
FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
COPY client-requirements.txt /opt/client-requirements.txt
RUN pip install --no-cache-dir -r /opt/client-requirements.txt
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-files-0.4.0@sha256:0d8eb42153dfb410f293e1ab6da62c5f3b7f08901fbb8c91f1d98e6729ebf88f /standard-realtime/environment/variants/bbdd57d050/game /usr/local/bin/game
RUN chmod +x /usr/local/bin/game && mkdir -p /app/output
# the eai-standard/3.0 client (docs/protocol/standard_mode.md): `from rcb_client import Robot`
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:497a2b864b3a1aaf1f60206dc14f08a0f99960037f0e54be3d4bc2e39f5adba4 /rcb1.py /rcb_client.py /opt/tools/
ENV PYTHONPATH=/opt/tools
# the robot's MCP tools (docs/protocol/standard_mode.md "MCP tools"): the server Harbor starts, efe-robot
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:497a2b864b3a1aaf1f60206dc14f08a0f99960037f0e54be3d4bc2e39f5adba4 /mcp/server.py /mcp/rcb_tools.py /mcp/schema.py /mcp/workspace.py /mcp/suites.py /opt/tools/efe_mcp/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:497a2b864b3a1aaf1f60206dc14f08a0f99960037f0e54be3d4bc2e39f5adba4 /mcp/schema/tools.json /opt/tools/efe_mcp/schema/
COPY efe_mcp /opt/tools/efe_mcp
ENV SEAT=A
ENV SIM_URL=http://localhost:8000
WORKDIR /app
