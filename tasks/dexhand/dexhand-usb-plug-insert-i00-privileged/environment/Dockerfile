FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.6.1@sha256:31eb441eccc44a6da7e30ae46aae8eae10eead0d4dae1b50d15457541c911a1b /privileged/environment/hands.py /privileged/environment/arm_rig.py /privileged/environment/variants/7bf46258f3/catalog.json /privileged/environment/variants/112500031b/checker.py /privileged/environment/variants/6e5f22b48c/replay.py /privileged/environment/variants/4b30501d99/runtime.py /privileged/environment/variants/e893d23529/scene.py /privileged/environment/variants/9e4e9f9962/task.json /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.6.1@sha256:31eb441eccc44a6da7e30ae46aae8eae10eead0d4dae1b50d15457541c911a1b /privileged/environment/assets/usb_scene.json /opt/tools/assets/usb_scene.json
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
