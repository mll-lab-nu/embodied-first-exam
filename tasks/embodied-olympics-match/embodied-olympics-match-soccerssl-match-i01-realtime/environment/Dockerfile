# The player's container: no simulator, only Python with the standard client pins and the generic `game`
# command of the core (core/game.py, the sport's shortcuts filled in by tools/generate.py).
FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
COPY client-requirements.txt /opt/client-requirements.txt
RUN pip install --no-cache-dir -r /opt/client-requirements.txt
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-files-0.4.0@sha256:0d8eb42153dfb410f293e1ab6da62c5f3b7f08901fbb8c91f1d98e6729ebf88f /standard-realtime/environment/variants/b0a191cbcc/game /usr/local/bin/game
RUN chmod +x /usr/local/bin/game && mkdir -p /app/output
# the eai-standard/3.0 client (docs/protocol/eai-standard.md): `from rcb_client import Robot`
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:ba111a75bfe7b63b7119f1699fe0d61e565ad6cd4d504591e32fdea7c826c795 /rcb1.py /realtime/rcb_client.py /opt/tools/
ENV PYTHONPATH=/opt/tools
# the robot's MCP tools (docs/protocol/eai-standard.md "MCP tools"): the server Harbor starts, efe-robot
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:ba111a75bfe7b63b7119f1699fe0d61e565ad6cd4d504591e32fdea7c826c795 /mcp/server.py /mcp/rcb_tools.py /mcp/schema.py /mcp/workspace.py /mcp/suites.py /opt/tools/efe_mcp/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:ba111a75bfe7b63b7119f1699fe0d61e565ad6cd4d504591e32fdea7c826c795 /mcp/schema/tools.json /opt/tools/efe_mcp/schema/
COPY efe_mcp /opt/tools/efe_mcp
ENV SEAT=A
ENV SIM_URL=http://localhost:8000
WORKDIR /app
