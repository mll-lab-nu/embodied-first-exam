# Base image = ManiGuard on its pinned stack (images/maniguard/: BEHAVIOR-1K v3.7.2 + Isaac Sim 4.5; BUILD_ONLY, every host
# builds it). Everything task-specific is copied here. The licensed BEHAVIOR dataset is NOT in any image:
# environment/docker-compose.yaml mounts the host's copy ($RCB_MANIGUARD_DATA, tasks/maniguard/README.md).
FROM ghcr.io/mll-lab-nu/efe-private:maniguard-0.1.0
COPY instance /app/instance
COPY --from=ghcr.io/mll-lab-nu/efe:maniguard-files-0.2.0@sha256:d7cd9c97ab71568db2022bd72b6987c1266f087ce0d5c4c475863c0075c74125 /privileged/environment/rcb_maniguard.py /opt/tools/rcb_maniguard.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
