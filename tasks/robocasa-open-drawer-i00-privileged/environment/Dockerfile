# RoboCasa privileged task: the benchmark image, the task's tooling and its frozen instance.
FROM ghcr.io/embodied-agent-interface-v2-internal/eai-robocasa:0.1.0
COPY instance.npz /app/instance.npz
COPY casa_tool.py /opt/tools/casa_tool.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
