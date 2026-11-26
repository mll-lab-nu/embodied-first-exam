# Base image = HumanoidBench environment (see images/humanoidbench/). Everything task-specific is copied here.
# One template for every HumanoidBench privileged task (the tooling that renders it is kept outside this repository): keep the copies identical.
FROM ghcr.io/mll-lab-nu/efe:humanoidbench-0.2.0
COPY instance.npz /app/instance.npz
COPY --from=ghcr.io/mll-lab-nu/efe:humanoidbench-files-0.5.0@sha256:044a54c3bd443fbc9e0e01c31d78cb3959108bc7fe3cc4d685a4e1b8817660a7 /privileged/environment/rcb_hb.py /opt/tools/rcb_hb.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
