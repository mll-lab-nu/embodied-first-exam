# Base image = AM-Bench (scrubbed: no scripted experts) + Isaac Lab / Isaac Sim 5.1 + the baked web assets (see
# images/ambench/; BUILD_ONLY). Everything task-specific is copied here; no reference solution is in the image.
FROM ghcr.io/mll-lab-nu/efe-private:ambench-0.2.0
COPY instance.json /app/instance.json
COPY --from=ghcr.io/mll-lab-nu/efe-private:ambench-files-0.1.0@sha256:31ae5caa3060994aa63457d302ccd0fda4083a68fafb6e0c2324e7fd4f8b80da /privileged/environment/rcb_ambench.py /opt/tools/rcb_ambench.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
