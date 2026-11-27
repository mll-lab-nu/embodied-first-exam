# RoboCasa365 privileged task: the benchmark image, the task's tooling and its frozen instance.
FROM ghcr.io/mll-lab-nu/efe:robocasa365-0.1.0
COPY instance.npz /app/instance.npz
COPY --from=ghcr.io/mll-lab-nu/efe:robocasa365-files-0.9.0@sha256:51372afbb4261657433546f3064c7adf21db20966f1c4a42cc327a9d3e853432 /privileged/environment/casa_tool.py /opt/tools/casa_tool.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
