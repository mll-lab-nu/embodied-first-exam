# Base image = KinDER (images/kinder/). Everything task-specific is copied here.
# Generated from scripts/kinder/templates/Dockerfile -- edit the template, not this copy.
FROM ghcr.io/mll-lab-nu/efe:kinder-0.1.6
COPY instance.json /app/instance.json
COPY --from=ghcr.io/mll-lab-nu/efe:kinder-files-0.1.1@sha256:bda6642064225d59d7be3c1640dfdd86ebbab1ec54357c7dcbe723850d3a8128 /privileged/environment/rcb_kinder.py /opt/tools/rcb_kinder.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
