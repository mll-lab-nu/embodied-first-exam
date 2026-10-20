FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.1.1@sha256:5da16fab7b26a7cdd7433ef32b8ead9286a9cf31da833d006f7b4d3e565e1ac9 /privileged/environment/hands.py /privileged/environment/arm_rig.py /privileged/environment/variants/af4ca24aff/catalog.json /privileged/environment/variants/0093c53b9d/checker.py /privileged/environment/variants/40f0888ab7/replay.py /privileged/environment/variants/48e11c53de/runtime.py /privileged/environment/variants/78e1d563c1/scene.py /privileged/environment/variants/0e8a7ea9b2/task.json /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.1.1@sha256:5da16fab7b26a7cdd7433ef32b8ead9286a9cf31da833d006f7b4d3e565e1ac9 /privileged/environment/assets/vacuum_scene.xml /opt/tools/assets/vacuum_scene.xml
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
