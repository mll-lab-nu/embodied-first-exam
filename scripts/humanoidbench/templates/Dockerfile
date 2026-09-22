# Base image = HumanoidBench environment (see images/humanoidbench/). Everything task-specific is copied here.
# Generated from scripts/humanoidbench/templates/Dockerfile -- edit the template, not this copy.
FROM ghcr.io/jameskrw/rcb-humanoidbench:{{image_tag}}
COPY instance.npz /app/instance.npz
COPY rcb_hb.py /opt/tools/rcb_hb.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
