FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.7.0@sha256:7e39aed8edd8439a6d102f9f40856d90e592df93173af4cd68681064a95da7d2 /privileged/environment/hands.py /privileged/environment/arm_rig.py /privileged/environment/variants/7ebefc2891/catalog.json /privileged/environment/variants/f716640f13/checker.py /privileged/environment/variants/8fc7dc9e74/replay.py /privileged/environment/variants/d5d28e5b35/runtime.py /privileged/environment/variants/8c4f757749/scene.py /privileged/environment/variants/00311b4e44/task.json /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.7.0@sha256:7e39aed8edd8439a6d102f9f40856d90e592df93173af4cd68681064a95da7d2 /privileged/environment/assets/cup.obj /privileged/environment/assets/spoon.obj /opt/tools/assets/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
