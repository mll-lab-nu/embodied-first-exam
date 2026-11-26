FROM ghcr.io/mll-lab-nu/efe:mujoco-0.1.2
COPY instance.json /app/instance.json
COPY --from=ghcr.io/mll-lab-nu/efe:mujoco-playground-files-0.7.0@sha256:347e83daa4047f377fc94b83537d406fa4c5c6c79b6b18367aba47ccd652659b /privileged/environment/rcb_aloha.py /opt/tools/rcb_aloha.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
