FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.6.2@sha256:643dd976b8c5913cd0552ac310550e09d2d30b4dd8a8a9df66105008e465cb72 /privileged/environment/hands.py /privileged/environment/variants/5504b0fa5b/catalog.json /privileged/environment/variants/19a12120ad/checker.py /privileged/environment/geometry.py /privileged/environment/variants/fef84ad4b3/replay.py /privileged/environment/variants/7e3fcc99ed/runtime.py /privileged/environment/variants/594155d137/scene.py /privileged/environment/variants/e8011d953f/task.json /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.6.2@sha256:643dd976b8c5913cd0552ac310550e09d2d30b4dd8a8a9df66105008e465cb72 /privileged/environment/assets/blade-0.stl /privileged/environment/assets/blade-1.stl /privileged/environment/assets/blade-2.stl /opt/tools/assets/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
