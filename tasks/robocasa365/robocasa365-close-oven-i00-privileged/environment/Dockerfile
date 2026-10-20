# RoboCasa365 privileged task: the benchmark image, the task's tooling and its frozen instance.
FROM ghcr.io/mll-lab-nu/efe:robocasa365-0.1.0
COPY instance.npz /app/instance.npz
COPY --from=ghcr.io/mll-lab-nu/efe:robocasa365-files-0.2.1@sha256:5d51b0625904529afc822ec9f95e173f8549d9bfbd808a0b193d9ebf6b6a9a9f /privileged/environment/casa_tool.py /opt/tools/casa_tool.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
