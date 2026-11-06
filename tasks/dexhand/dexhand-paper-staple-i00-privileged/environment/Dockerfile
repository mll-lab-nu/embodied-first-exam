FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.5.0@sha256:ceea7a90b9c905345ca0a18a598fd56c600a9ccdcb633339f0d92b3e7577ca09 /privileged/environment/hands.py /privileged/environment/arm_rig.py /privileged/environment/variants/19e44d8c62/catalog.json /privileged/environment/variants/5fbaabcafe/checker.py /privileged/environment/variants/05a1fea9f4/replay.py /privileged/environment/variants/b0fbea4c81/runtime.py /privileged/environment/variants/d9b4fae7c9/scene.py /privileged/environment/variants/2ee4813352/task.json /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.5.0@sha256:ceea7a90b9c905345ca0a18a598fd56c600a9ccdcb633339f0d92b3e7577ca09 /privileged/environment/assets/stapler_base_shell.obj /privileged/environment/assets/stapler_handle_shell.obj /opt/tools/assets/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
