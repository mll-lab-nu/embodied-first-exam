# Base image = BEHAVIOR-1K v3.9.2 (images/behavior/: BUILD_ONLY, every host builds it). Everything task-specific is
# copied here. The BEHAVIOR dataset is NOT in any image (its license forbids redistribution):
# environment/docker-compose.yaml mounts the host's licensed copy.
FROM ghcr.io/embodied-agent-interface-v2-internal/eai-behavior:0.1.1
COPY instance.json /app/instance.json
COPY rcb_behavior.py r1pro_primitives_eval.yaml /opt/tools/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
