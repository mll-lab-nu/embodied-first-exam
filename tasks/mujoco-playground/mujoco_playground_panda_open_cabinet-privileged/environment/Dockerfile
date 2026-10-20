FROM ghcr.io/mll-lab-nu/efe:mujoco-0.1.2
COPY instance.json /app/instance.json
COPY --from=ghcr.io/mll-lab-nu/efe:mujoco-playground-files-0.2.0@sha256:dbe851469cb734095f60732d3f45f099189bf791e4969e2120e1b86b778b7bd3 /privileged/environment/rcb_panda.py /opt/tools/rcb_panda.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
