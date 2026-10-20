FROM ghcr.io/mll-lab-nu/efe:mujoco-0.1.2
COPY instance.json /app/instance.json
COPY --from=ghcr.io/mll-lab-nu/efe:dextoolbench-files-0.1.1@sha256:f30380562a7e5e284d1e2efa6b95e5c17b539184a22fb0367256fe43b9641955 /privileged/environment/rcb_dtb.py /opt/tools/rcb_dtb.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
