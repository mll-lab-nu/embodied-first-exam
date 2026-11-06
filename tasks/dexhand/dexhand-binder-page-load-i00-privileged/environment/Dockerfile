FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.5.0@sha256:e90c3817d6fee11cd727b5f82252740849e5b66ced87c7fce411b4747e911166 /privileged/environment/hands.py /privileged/environment/variants/8cafafaea9/catalog.json /privileged/environment/variants/cbf4353688/checker.py /privileged/environment/variants/95a47458e9/replay.py /privileged/environment/variants/979d961057/runtime.py /privileged/environment/variants/be8d26ca72/scene.py /privileged/environment/variants/c102aa24ba/task.json /opt/tools/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
