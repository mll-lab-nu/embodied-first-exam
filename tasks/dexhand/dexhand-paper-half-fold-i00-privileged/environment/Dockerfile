FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.6.2@sha256:643dd976b8c5913cd0552ac310550e09d2d30b4dd8a8a9df66105008e465cb72 /privileged/environment/hands.py /privileged/environment/variants/edbd9a7b31/catalog.json /privileged/environment/variants/8f7e53cd06/replay.py /privileged/environment/variants/5e548e1cba/runtime.py /privileged/environment/scene_sharpa.xml /privileged/environment/shell.py /opt/tools/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
