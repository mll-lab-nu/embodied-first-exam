FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.6.2@sha256:643dd976b8c5913cd0552ac310550e09d2d30b4dd8a8a9df66105008e465cb72 /privileged/environment/hands.py /privileged/environment/arm_rig.py /privileged/environment/variants/dfdc60104a/catalog.json /privileged/environment/variants/f0caa6842d/checker.py /privileged/environment/variants/6d3fd8f682/replay.py /privileged/environment/variants/2b6719073f/runtime.py /privileged/environment/variants/49286a9a86/scene.py /privileged/environment/variants/cbe55a04ec/task.json /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.6.2@sha256:643dd976b8c5913cd0552ac310550e09d2d30b4dd8a8a9df66105008e465cb72 /privileged/environment/assets/source/SHARPA-APACHE-2.0.txt /privileged/environment/assets/source/hario_mechanism.py /opt/tools/assets/source/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
