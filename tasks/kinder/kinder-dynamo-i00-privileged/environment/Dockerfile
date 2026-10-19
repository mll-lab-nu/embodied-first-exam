# Base image = KinDER (images/kinder/). Everything task-specific is copied here.
# Generated from scripts/kinder/templates/Dockerfile -- edit the template, not this copy.
FROM ghcr.io/mll-lab-nu/efe:kinder-0.1.6
COPY instance.json /app/instance.json
COPY --from=ghcr.io/mll-lab-nu/efe:kinder-files-0.1.0@sha256:bec476e6c2748cc2eac4e4b054b60d899ab6a44afcf3d89a9b070a1f78d68b7d /privileged/environment/rcb_kinder.py /opt/tools/rcb_kinder.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
