# Base image = HumanoidBench environment (see images/humanoidbench/). Everything task-specific is copied here.
# One template for every HumanoidBench privileged task (the tooling that renders it is kept outside this repository): keep the copies identical.
FROM ghcr.io/mll-lab-nu/efe:humanoidbench-0.2.0
COPY instance.npz /app/instance.npz
COPY --from=ghcr.io/mll-lab-nu/efe:humanoidbench-files-0.7.0@sha256:e59319022949b9fdbeb2354c2c3721ab65391b1668289b5a03d77c2060bde761 /privileged/environment/rcb_hb.py /opt/tools/rcb_hb.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
