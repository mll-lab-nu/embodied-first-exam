# VLABench privileged task: the VLABench image, the task's tooling and its frozen instance.
FROM ghcr.io/embodied-agent-interface-v2-internal/eai-vlabench:0.1.0
COPY instance.json /app/instance.json
COPY vlb_tool.py /opt/tools/vlb_tool.py
ENV PYTHONPATH=/opt/tools:/opt/VLABench:/opt/rrt-algorithms
RUN mkdir -p /app/output
WORKDIR /app
