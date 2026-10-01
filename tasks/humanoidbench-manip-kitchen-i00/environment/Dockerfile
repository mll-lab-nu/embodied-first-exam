# Base image = HumanoidBench environment (see images/humanoidbench/). Everything task-specific is copied here.
# Generated from scripts/humanoidbench/templates/Dockerfile -- edit the template, not this copy.
FROM ghcr.io/embodied-agent-interface-v2-internal/eai-humanoidbench:0.1.6
COPY instance.npz /app/instance.npz
COPY rcb_hb.py /opt/tools/rcb_hb.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
