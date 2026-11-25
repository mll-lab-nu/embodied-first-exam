FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.6.2@sha256:643dd976b8c5913cd0552ac310550e09d2d30b4dd8a8a9df66105008e465cb72 /privileged/environment/hands.py /privileged/environment/arm_rig.py /privileged/environment/variants/0f75895231/catalog.json /privileged/environment/variants/112500031b/checker.py /privileged/environment/variants/6e5f22b48c/replay.py /privileged/environment/variants/4b30501d99/runtime.py /privileged/environment/variants/e893d23529/scene.py /privileged/environment/variants/8b67052c4c/task.json /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.6.2@sha256:643dd976b8c5913cd0552ac310550e09d2d30b4dd8a8a9df66105008e465cb72 /privileged/environment/assets/usb_scene.json /opt/tools/assets/usb_scene.json
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
