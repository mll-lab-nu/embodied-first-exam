# LIBERO-MAX privileged task: the LIBERO-MAX image, the task's tooling and its frozen instance.
FROM ghcr.io/mll-lab-nu/efe:libero-max-0.1.1
COPY instance.json /app/instance.json
COPY --from=ghcr.io/mll-lab-nu/efe:libero-max-files-0.5.0@sha256:5fce3c4cd840e71f65f73072e745683724ebe7cb741374b8d4f0ba846bb20374 /privileged/environment/lmx_tool.py /opt/tools/lmx_tool.py
ENV PYTHONPATH=/opt/tools:/opt/libero-max/overlay:/opt/libero-max/src
RUN mkdir -p /app/output
WORKDIR /app
