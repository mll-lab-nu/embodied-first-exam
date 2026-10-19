FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.1.0@sha256:47919ae95e25b8c6daa3c19c9714a4743fd1c18db580589cb8552a71aa689f9d /privileged/environment/hands.py /privileged/tests/grade.py /privileged/environment/arm_rig.py /privileged/environment/variants/495d12a53b/catalog.json /privileged/environment/variants/5655757645/checker.py /privileged/environment/variants/8ccfe3d6c8/replay.py /privileged/environment/variants/93b12f9846/runtime.py /privileged/environment/variants/cc9b3e00d4/scene.py /privileged/environment/variants/e30cc06716/task.json /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.1.0@sha256:47919ae95e25b8c6daa3c19c9714a4743fd1c18db580589cb8552a71aa689f9d /privileged/environment/assets/aa_cell.obj /privileged/environment/assets/battery_door.obj /privileged/environment/assets/variants/36d169133c/manifest.json /privileged/environment/assets/new_aa_wrap.png /privileged/environment/assets/old_aa_wrap.png /privileged/environment/assets/remote_shell.obj /privileged/environment/assets/thumb_pad.obj /tests/assets/
ENV PYTHONPATH=/tests
RUN chmod +x /tests/test.sh
WORKDIR /tests
# resource limits: the verifier step (from the monitor image) and its copy of the limits (docs/protocol/README.md §2.10) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.2.0@sha256:65442d9e9eeb493d785a59d48a321345e2b48186946cc9d55beb684182514b4b /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
