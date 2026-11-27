# RoboCasa365 privileged task: the benchmark image, the task's tooling and its frozen instance.
FROM ghcr.io/mll-lab-nu/efe:robocasa365-0.1.0
COPY instance.npz /app/instance.npz
COPY --from=ghcr.io/mll-lab-nu/efe:robocasa365-files-0.7.0@sha256:0dad1b28d16dd1311ed627d7b1c78fa05cea481a4ed507ba835efcd9c552394e /privileged/environment/casa_tool.py /opt/tools/casa_tool.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
