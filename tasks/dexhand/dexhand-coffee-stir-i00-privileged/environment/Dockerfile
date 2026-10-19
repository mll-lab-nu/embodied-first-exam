FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.1.0@sha256:47919ae95e25b8c6daa3c19c9714a4743fd1c18db580589cb8552a71aa689f9d /privileged/environment/hands.py /privileged/environment/arm_rig.py /privileged/environment/variants/7ebefc2891/catalog.json /privileged/environment/variants/f716640f13/checker.py /privileged/environment/variants/7148f5b942/replay.py /privileged/environment/variants/d5d28e5b35/runtime.py /privileged/environment/variants/b7be4f3f96/scene.py /privileged/environment/variants/00311b4e44/task.json /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.1.0@sha256:47919ae95e25b8c6daa3c19c9714a4743fd1c18db580589cb8552a71aa689f9d /privileged/environment/assets/cup.obj /privileged/environment/assets/spoon.obj /opt/tools/assets/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
