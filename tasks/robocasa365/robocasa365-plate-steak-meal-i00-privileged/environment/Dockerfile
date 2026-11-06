# RoboCasa365 privileged task: the benchmark image, the task's tooling and its frozen instance.
FROM ghcr.io/mll-lab-nu/efe:robocasa365-0.1.0
COPY instance.npz /app/instance.npz
COPY --from=ghcr.io/mll-lab-nu/efe:robocasa365-files-0.5.1@sha256:92bf047ccf714bd8d3cc1dd8ae53d09e972dfe8234a693d49ca4f1c1d109a330 /privileged/environment/casa_tool.py /opt/tools/casa_tool.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
