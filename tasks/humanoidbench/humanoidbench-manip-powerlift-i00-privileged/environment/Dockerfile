# Base image = HumanoidBench environment (see images/humanoidbench/). Everything task-specific is copied here.
# One template for every HumanoidBench privileged task (the tooling that renders it is kept outside this repository): keep the copies identical.
FROM ghcr.io/mll-lab-nu/efe:humanoidbench-0.2.0
COPY instance.npz /app/instance.npz
COPY --from=ghcr.io/mll-lab-nu/efe:humanoidbench-files-0.4.0@sha256:ce4fd00e84bb202de450b54de645a1bdb35b19767d0e07de298c329072632528 /privileged/environment/rcb_hb.py /opt/tools/rcb_hb.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
