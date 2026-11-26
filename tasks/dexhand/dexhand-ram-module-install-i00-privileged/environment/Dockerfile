FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.7.0@sha256:1397f5ba078dbbb9cff655c1ed962b72c3f42282d3bb5f2002f72209401249d2 /privileged/environment/hands.py /privileged/environment/variants/ee0322ea61/catalog.json /privileged/environment/variants/436527ad9b/checker.py /privileged/environment/variants/4d69967a71/replay.py /privileged/environment/variants/3b2b1b62e2/runtime.py /privileged/environment/variants/9a1df1cf5f/scene.py /privileged/environment/variants/1797f2e12e/task.json /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.7.0@sha256:1397f5ba078dbbb9cff655c1ed962b72c3f42282d3bb5f2002f72209401249d2 /privileged/environment/assets/manifest.json /privileged/environment/assets/ram-label.png /privileged/environment/assets/t28_geometry_corrections.json /privileged/environment/assets/t28_scene.xml /opt/tools/assets/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
