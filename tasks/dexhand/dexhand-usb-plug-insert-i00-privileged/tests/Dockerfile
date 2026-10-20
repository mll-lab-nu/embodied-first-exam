FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.2.0@sha256:972cfacca6dbd5cac0d2f18799076c830efeb384928663e44b8fdcacdc57b89c /privileged/environment/hands.py /privileged/tests/grade.py /privileged/environment/arm_rig.py /privileged/environment/variants/c1ce7ef43a/catalog.json /privileged/environment/variants/112500031b/checker.py /privileged/environment/variants/6e5f22b48c/replay.py /privileged/environment/variants/4b30501d99/runtime.py /privileged/environment/variants/e893d23529/scene.py /privileged/environment/variants/ccb1b8661e/task.json /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.2.0@sha256:972cfacca6dbd5cac0d2f18799076c830efeb384928663e44b8fdcacdc57b89c /privileged/environment/assets/usb_scene.json /tests/assets/usb_scene.json
ENV PYTHONPATH=/tests
RUN chmod +x /tests/test.sh
WORKDIR /tests
# resource limits: the verifier step (from the monitor image) and its copy of the limits (docs/protocol/README.md §2.10) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.2.0@sha256:65442d9e9eeb493d785a59d48a321345e2b48186946cc9d55beb684182514b4b /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
