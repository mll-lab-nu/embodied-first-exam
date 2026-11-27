FROM ghcr.io/mll-lab-nu/efe:mujoco-0.1.2
COPY instance.json /app/instance.json
COPY --from=ghcr.io/mll-lab-nu/efe:mujoco-playground-files-0.10.0@sha256:450a6892bef87b047a06f190b4c61d71ac0a01818ddc40fa49ed706ab78e055f /privileged/environment/rcb_aloha.py /opt/tools/rcb_aloha.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
