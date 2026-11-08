# Base image = HumanoidBench environment (see images/humanoidbench/). Everything task-specific is copied here.
# One template for every HumanoidBench privileged task (the tooling that renders it is kept outside this repository): keep the copies identical.
FROM ghcr.io/mll-lab-nu/efe:humanoidbench-0.2.0
COPY instance.npz /app/instance.npz
COPY --from=ghcr.io/mll-lab-nu/efe:humanoidbench-files-0.4.1@sha256:1a7fcffe473eaf01597596e7c4f6442d2ab4dfa80bd2b1797893a555514efe38 /privileged/environment/rcb_hb.py /opt/tools/rcb_hb.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
