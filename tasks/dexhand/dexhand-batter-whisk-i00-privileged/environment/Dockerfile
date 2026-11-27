FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.9.0@sha256:0d919cb5a25357018eb8cfe31b532a510cdafcaad67383b0ffd852e0866254c7 /privileged/environment/hands.py /privileged/environment/arm_rig.py /privileged/environment/variants/bc48a3e915/catalog.json /privileged/environment/variants/5b6c0efb04/checker.py /privileged/environment/variants/b1a971bef9/replay.py /privileged/environment/variants/0bd2e5aa3c/runtime.py /privileged/environment/variants/270ae05e98/scene.py /privileged/environment/variants/0b89750a2c/task.json /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.9.0@sha256:0d919cb5a25357018eb8cfe31b532a510cdafcaad67383b0ffd852e0866254c7 /privileged/environment/assets/rosle-bowl-original.obj /privileged/environment/assets/rosle-whisk-wires-original.obj /opt/tools/assets/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
