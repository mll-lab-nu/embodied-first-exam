# Standard mode: the agent container has no simulator and no LIBERO code -- only Python and the client.
FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
RUN pip install --no-cache-dir certifi==2026.7.22 charset-normalizer==3.5.2 idna==3.20 numpy==2.5.3 pillow==12.3.0 requests==2.34.2 scipy==1.18.1 urllib3==2.8.0
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.7.0@sha256:1ab8c16d4372a0b44f5c0ea7f819f6febafcfdc132013b1736a04f360375b28f /rcb1.py /v2_1/rcb_client.py /opt/tools/
ENV PYTHONPATH=/opt/tools
# the robot's MCP tools (docs/protocol/standard_mode.md "MCP tools"): the server Harbor starts, efe-robot
COPY efe_mcp /opt/tools/efe_mcp
RUN mkdir -p /app/output
WORKDIR /app
