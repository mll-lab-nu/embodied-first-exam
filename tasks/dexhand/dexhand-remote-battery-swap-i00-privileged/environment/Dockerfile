FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.1.1@sha256:5da16fab7b26a7cdd7433ef32b8ead9286a9cf31da833d006f7b4d3e565e1ac9 /privileged/environment/hands.py /privileged/environment/arm_rig.py /privileged/environment/variants/495d12a53b/catalog.json /privileged/environment/variants/5655757645/checker.py /privileged/environment/variants/1607580247/replay.py /privileged/environment/variants/93b12f9846/runtime.py /privileged/environment/variants/cc9b3e00d4/scene.py /privileged/environment/variants/e30cc06716/task.json /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.1.1@sha256:5da16fab7b26a7cdd7433ef32b8ead9286a9cf31da833d006f7b4d3e565e1ac9 /privileged/environment/assets/aa_cell.obj /privileged/environment/assets/battery_door.obj /privileged/environment/assets/variants/36d169133c/manifest.json /privileged/environment/assets/new_aa_wrap.png /privileged/environment/assets/old_aa_wrap.png /privileged/environment/assets/remote_shell.obj /privileged/environment/assets/thumb_pad.obj /opt/tools/assets/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
