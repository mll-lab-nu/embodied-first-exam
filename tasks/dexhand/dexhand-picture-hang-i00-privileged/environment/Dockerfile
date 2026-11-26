FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.7.0@sha256:1397f5ba078dbbb9cff655c1ed962b72c3f42282d3bb5f2002f72209401249d2 /privileged/environment/hands.py /privileged/environment/arm_rig.py /privileged/environment/variants/fb0638f711/catalog.json /privileged/environment/variants/cf1c141a55/checker.py /privileged/environment/variants/4c79bfe5f4/replay.py /privileged/environment/variants/969b07e0b2/runtime.py /privileged/environment/variants/16d2dcef2f/scene.py /privileged/environment/variants/62bf469241/task.json /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.7.0@sha256:1397f5ba078dbbb9cff655c1ed962b72c3f42282d3bb5f2002f72209401249d2 /privileged/environment/assets/water-lilies.png /opt/tools/assets/water-lilies.png
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
