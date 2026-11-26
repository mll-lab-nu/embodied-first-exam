FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.7.0@sha256:1397f5ba078dbbb9cff655c1ed962b72c3f42282d3bb5f2002f72209401249d2 /privileged/environment/hands.py /privileged/environment/catalog.json /privileged/environment/variants/bd227f1806/checker.py /privileged/environment/variants/b8d126ab19/replay.py /privileged/environment/variants/edb2fa483d/runtime.py /privileged/environment/variants/833515eb2e/scene.py /privileged/environment/variants/36fdc6d2ed/task.json /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.7.0@sha256:1397f5ba078dbbb9cff655c1ed962b72c3f42282d3bb5f2002f72209401249d2 /privileged/environment/assets/sharpa_bimanual_hands.xml /privileged/environment/assets/t48_tray_glasses.xml /opt/tools/assets/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
