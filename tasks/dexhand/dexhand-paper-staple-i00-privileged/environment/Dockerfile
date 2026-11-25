FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.6.1@sha256:31eb441eccc44a6da7e30ae46aae8eae10eead0d4dae1b50d15457541c911a1b /privileged/environment/hands.py /privileged/environment/arm_rig.py /privileged/environment/variants/7007e3344c/catalog.json /privileged/environment/variants/5fbaabcafe/checker.py /privileged/environment/variants/05a1fea9f4/replay.py /privileged/environment/variants/b0fbea4c81/runtime.py /privileged/environment/variants/d9b4fae7c9/scene.py /privileged/environment/variants/21b77c3a43/task.json /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.6.1@sha256:31eb441eccc44a6da7e30ae46aae8eae10eead0d4dae1b50d15457541c911a1b /privileged/environment/assets/stapler_base_shell.obj /privileged/environment/assets/stapler_handle_shell.obj /opt/tools/assets/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
