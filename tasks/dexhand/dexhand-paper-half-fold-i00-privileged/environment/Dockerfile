FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.5.0@sha256:ceea7a90b9c905345ca0a18a598fd56c600a9ccdcb633339f0d92b3e7577ca09 /privileged/environment/hands.py /privileged/environment/variants/edbd9a7b31/catalog.json /privileged/environment/variants/8f7e53cd06/replay.py /privileged/environment/variants/5e548e1cba/runtime.py /privileged/environment/scene_sharpa.xml /privileged/environment/shell.py /opt/tools/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
