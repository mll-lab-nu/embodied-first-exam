FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.1.0@sha256:47919ae95e25b8c6daa3c19c9714a4743fd1c18db580589cb8552a71aa689f9d /privileged/environment/hands.py /privileged/environment/arm_rig.py /privileged/environment/variants/3f0ed7cb2c/catalog.json /privileged/environment/variants/f0caa6842d/checker.py /privileged/environment/variants/b818bb923e/replay.py /privileged/environment/variants/2b6719073f/runtime.py /privileged/environment/variants/d3ffa410d3/scene.py /privileged/environment/variants/1d21e930d4/task.json /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.1.0@sha256:47919ae95e25b8c6daa3c19c9714a4743fd1c18db580589cb8552a71aa689f9d /privileged/environment/assets/source/ASSET_PROVENANCE.md /privileged/environment/assets/source/SHARPA-APACHE-2.0.txt /privileged/environment/assets/source/hario_mechanism.py /opt/tools/assets/source/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
