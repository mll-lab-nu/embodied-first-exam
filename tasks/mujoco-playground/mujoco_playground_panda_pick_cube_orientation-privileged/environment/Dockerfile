FROM ghcr.io/mll-lab-nu/efe:mujoco-0.1.2
COPY instance.json /app/instance.json
COPY --from=ghcr.io/mll-lab-nu/efe:mujoco-playground-files-0.7.0@sha256:931d2b59ff197790ac2d917f047334a485f1ae272753ab4ba5de7612aa7edf6d /privileged/environment/rcb_panda.py /opt/tools/rcb_panda.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
