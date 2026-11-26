FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.7.0@sha256:7e39aed8edd8439a6d102f9f40856d90e592df93173af4cd68681064a95da7d2 /privileged/environment/hands.py /privileged/environment/arm_rig.py /privileged/environment/variants/17cc46fd5d/catalog.json /privileged/environment/variants/989e170b27/checker.py /privileged/environment/variants/52e9f44eef/replay.py /privileged/environment/variants/328103d2bd/runtime.py /privileged/environment/variants/4053e4abc2/scene.py /privileged/environment/task.json /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.7.0@sha256:7e39aed8edd8439a6d102f9f40856d90e592df93173af4cd68681064a95da7d2 /privileged/environment/assets/meshes/continuous_collar.obj /privileged/environment/assets/meshes/continuous_hollow_head.obj /privileged/environment/assets/meshes/rim.obj /privileged/environment/assets/meshes/smooth_full_tire.obj /opt/tools/assets/meshes/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.7.0@sha256:7e39aed8edd8439a6d102f9f40856d90e592df93173af4cd68681064a95da7d2 /privileged/environment/assets/t50_scene.json /opt/tools/assets/t50_scene.json
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
