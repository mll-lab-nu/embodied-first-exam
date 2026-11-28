FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.11.0@sha256:0fac42ee8fe3c9987a4a1a37497aca8eb990881ae42408af32c42acc4df4b23c /privileged/environment/variants/653ead04f6/catalog.json /privileged/environment/hands.py /privileged/environment/variants/1ccb553961/replay.py /privileged/environment/variants/6efba74799/runtime.py /privileged/environment/variants/af13909348/scene.py /privileged/environment/variants/34b8665d5b/task.json /opt/tools/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
