FROM ghcr.io/mll-lab-nu/efe:mujoco-0.1.2
COPY instance.json /app/instance.json
COPY --from=ghcr.io/mll-lab-nu/efe:dextoolbench-files-0.9.0@sha256:ab32718ec9c78f5d4d63c18b54eaaaee8726bf784f00b00fb654a50435ffc1f2 /privileged/environment/rcb_dtb.py /opt/tools/rcb_dtb.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
