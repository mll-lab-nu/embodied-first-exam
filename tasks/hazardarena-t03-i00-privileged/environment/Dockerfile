# HazardArena privileged task: the HazardArena image, the task's tooling and its frozen instance.
FROM ghcr.io/mll-lab-nu/eai-hazardarena:0.1.0
COPY instance.json /app/instance.json
COPY ha_tool.py /opt/tools/ha_tool.py
ENV PYTHONPATH=/opt/tools:/opt/HazardArena:/opt/rrt-algorithms
RUN mkdir -p /app/output
WORKDIR /app
