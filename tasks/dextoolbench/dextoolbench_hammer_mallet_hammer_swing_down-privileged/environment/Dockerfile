FROM ghcr.io/mll-lab-nu/efe:mujoco-0.1.2
COPY instance.json /app/instance.json
COPY --from=ghcr.io/mll-lab-nu/efe:dextoolbench-files-0.6.0@sha256:3a06c3f2689f1b13c088bfd0d4588c0799ed908d983604865e5265376c9415bf /privileged/environment/rcb_dtb.py /opt/tools/rcb_dtb.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
