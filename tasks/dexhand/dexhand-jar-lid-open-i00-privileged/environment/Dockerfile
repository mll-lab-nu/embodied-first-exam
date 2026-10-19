FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.1.0@sha256:47919ae95e25b8c6daa3c19c9714a4743fd1c18db580589cb8552a71aa689f9d /privileged/environment/hands.py /privileged/environment/arm_rig.py /privileged/environment/variants/7ce09e87cf/catalog.json /privileged/environment/variants/2009ba31aa/checker.py /privileged/environment/variants/54ffbea106/replay.py /privileged/environment/variants/0c73de31b5/runtime.py /privileged/environment/variants/a4f4d5a733/scene.py /privileged/environment/variants/80a6812ac6/task.json /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.1.0@sha256:47919ae95e25b8c6daa3c19c9714a4743fd1c18db580589cb8552a71aa689f9d /privileged/environment/assets/continuous-glass.obj /privileged/environment/assets/label.obj /privileged/environment/assets/label.png /privileged/environment/assets/variants/8bd4888ce9/manifest.json /opt/tools/assets/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
