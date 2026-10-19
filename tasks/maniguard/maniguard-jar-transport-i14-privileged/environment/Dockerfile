# Base image = ManiGuard on its pinned stack (images/maniguard/: BEHAVIOR-1K v3.7.2 + Isaac Sim 4.5; BUILD_ONLY, every host
# builds it). Everything task-specific is copied here. The licensed BEHAVIOR dataset is NOT in any image:
# environment/docker-compose.yaml mounts the host's copy ($RCB_MANIGUARD_DATA, docs/benchmarks/maniguard.md).
FROM ghcr.io/mll-lab-nu/efe-private:maniguard-0.1.0
COPY instance /app/instance
COPY --from=ghcr.io/mll-lab-nu/efe-private:maniguard-files-0.1.0@sha256:c3f228906c44d58cdbb2dfef6a0adaf989f1be969d227e1c9db9e060f5b3f6cf /privileged/environment/rcb_maniguard.py /opt/tools/rcb_maniguard.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
