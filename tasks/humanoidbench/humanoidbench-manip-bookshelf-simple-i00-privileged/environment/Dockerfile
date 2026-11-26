# Base image = HumanoidBench environment (see images/humanoidbench/). Everything task-specific is copied here.
# One template for every HumanoidBench privileged task (the tooling that renders it is kept outside this repository): keep the copies identical.
FROM ghcr.io/mll-lab-nu/efe:humanoidbench-0.2.0
COPY instance.npz /app/instance.npz
COPY --from=ghcr.io/mll-lab-nu/efe:humanoidbench-files-0.5.0@sha256:1bb5889e1d723c4d0c27d43267f256b5b81cadb378a51aef7b8b739faf4394d3 /privileged/environment/rcb_hb.py /opt/tools/rcb_hb.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
