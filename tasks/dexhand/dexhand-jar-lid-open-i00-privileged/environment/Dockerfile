FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.5.0@sha256:ceea7a90b9c905345ca0a18a598fd56c600a9ccdcb633339f0d92b3e7577ca09 /privileged/environment/hands.py /privileged/environment/arm_rig.py /privileged/environment/variants/8bebf98a58/replay.py /privileged/environment/variants/0c73de31b5/runtime.py /privileged/environment/variants/a4f4d5a733/scene.py /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.5.0@sha256:ceea7a90b9c905345ca0a18a598fd56c600a9ccdcb633339f0d92b3e7577ca09 /privileged/environment/assets/continuous-glass.obj /privileged/environment/assets/label.obj /privileged/environment/assets/label.png /privileged/environment/assets/variants/300aa019ac/manifest.json /opt/tools/assets/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
