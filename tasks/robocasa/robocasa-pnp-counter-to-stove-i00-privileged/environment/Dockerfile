# RoboCasa privileged task: the benchmark image, the task's tooling and its frozen instance.
FROM ghcr.io/mll-lab-nu/efe:robocasa-0.1.0
COPY instance.npz /app/instance.npz
COPY --from=ghcr.io/mll-lab-nu/efe:robocasa-files-0.6.0@sha256:a0fd0e294af7e2f6140d08f31fca13dc32c8186d4086ceabfa406290b0dbde88 /privileged/environment/casa_tool.py /opt/tools/casa_tool.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
