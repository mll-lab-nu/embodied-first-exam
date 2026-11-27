FROM ghcr.io/mll-lab-nu/efe:mujoco-0.1.2
COPY instance.json /app/instance.json
COPY --from=ghcr.io/mll-lab-nu/efe:mujoco-playground-files-0.9.0@sha256:2f8a36bfdf767590e6e7210a586c4c4e1ad220dcb8981ab18303a8da7e5b8047 /privileged/environment/rcb_panda.py /opt/tools/rcb_panda.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
