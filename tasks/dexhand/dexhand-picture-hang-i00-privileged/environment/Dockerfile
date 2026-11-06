FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.6.0@sha256:76ecdba39db6329198383e5fa6c89613bd95185ab974a2895521d32237900b24 /privileged/environment/hands.py /privileged/environment/arm_rig.py /privileged/environment/variants/85d44635c5/catalog.json /privileged/environment/variants/cf1c141a55/checker.py /privileged/environment/variants/4c79bfe5f4/replay.py /privileged/environment/variants/969b07e0b2/runtime.py /privileged/environment/variants/16d2dcef2f/scene.py /privileged/environment/variants/cf26dc5048/task.json /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.6.0@sha256:76ecdba39db6329198383e5fa6c89613bd95185ab974a2895521d32237900b24 /privileged/environment/assets/water-lilies.png /opt/tools/assets/water-lilies.png
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
