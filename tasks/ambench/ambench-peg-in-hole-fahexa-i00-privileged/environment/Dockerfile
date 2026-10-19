# Base image = AM-Bench (scrubbed: no scripted experts) + Isaac Lab / Isaac Sim 5.1 + the baked web assets (see
# images/ambench/; BUILD_ONLY). Everything task-specific is copied here; no reference solution is in the image.
FROM ghcr.io/mll-lab-nu/efe-private:ambench-0.2.0
COPY instance.json /app/instance.json
COPY --from=ghcr.io/mll-lab-nu/efe:ambench-files-0.2.0@sha256:416a555923062b9c999765a50688889dfb5a1e5525c5fdf8471ec3bd4c1e4061 /privileged/environment/rcb_ambench.py /opt/tools/rcb_ambench.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
