FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.6.0@sha256:76ecdba39db6329198383e5fa6c89613bd95185ab974a2895521d32237900b24 /privileged/environment/hands.py /privileged/environment/variants/8cafafaea9/catalog.json /privileged/environment/variants/cbf4353688/checker.py /privileged/environment/variants/95a47458e9/replay.py /privileged/environment/variants/979d961057/runtime.py /privileged/environment/variants/be8d26ca72/scene.py /privileged/environment/variants/c102aa24ba/task.json /opt/tools/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
