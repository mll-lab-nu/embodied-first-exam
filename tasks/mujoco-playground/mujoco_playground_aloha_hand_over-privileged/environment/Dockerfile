FROM ghcr.io/mll-lab-nu/efe:mujoco-0.1.2
COPY instance.json /app/instance.json
COPY --from=ghcr.io/mll-lab-nu/efe:mujoco-playground-files-0.1.1@sha256:fbd7136fbe91fbbb5458c7c4354ec2abb744ce55e230e8251cba8a9e85399435 /privileged/environment/rcb_aloha.py /opt/tools/rcb_aloha.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
