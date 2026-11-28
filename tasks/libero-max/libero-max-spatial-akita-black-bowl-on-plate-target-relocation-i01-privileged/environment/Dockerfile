# LIBERO-MAX privileged task: the LIBERO-MAX image, the task's tooling and its frozen instance.
FROM ghcr.io/mll-lab-nu/efe:libero-max-0.1.1
COPY instance.json /app/instance.json
COPY --from=ghcr.io/mll-lab-nu/efe:libero-max-files-0.7.0@sha256:d86ed6487b22d8a3ee255667a7bf9fb53accbf916cc81db2a62c88261269c6b8 /privileged/environment/lmx_tool.py /opt/tools/lmx_tool.py
ENV PYTHONPATH=/opt/tools:/opt/libero-max/overlay:/opt/libero-max/src
RUN mkdir -p /app/output
WORKDIR /app
