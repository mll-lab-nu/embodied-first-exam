FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.6.1@sha256:31eb441eccc44a6da7e30ae46aae8eae10eead0d4dae1b50d15457541c911a1b /privileged/environment/hands.py /privileged/environment/variants/3b44d3e239/catalog.json /privileged/environment/variants/436527ad9b/checker.py /privileged/environment/variants/4d69967a71/replay.py /privileged/environment/variants/3b2b1b62e2/runtime.py /privileged/environment/variants/9a1df1cf5f/scene.py /privileged/environment/variants/5d92a52478/task.json /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.6.1@sha256:31eb441eccc44a6da7e30ae46aae8eae10eead0d4dae1b50d15457541c911a1b /privileged/environment/assets/manifest.json /privileged/environment/assets/ram-label.png /privileged/environment/assets/t28_geometry_corrections.json /privileged/environment/assets/t28_scene.xml /opt/tools/assets/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
