FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.1.0@sha256:47919ae95e25b8c6daa3c19c9714a4743fd1c18db580589cb8552a71aa689f9d /privileged/environment/hands.py /privileged/environment/variants/1395090125/catalog.json /privileged/environment/variants/19a12120ad/checker.py /privileged/environment/geometry.py /privileged/environment/variants/cf073b6469/replay.py /privileged/environment/variants/7e3fcc99ed/runtime.py /privileged/environment/variants/3c244c9682/scene.py /privileged/environment/variants/60f55fdb91/task.json /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.1.0@sha256:47919ae95e25b8c6daa3c19c9714a4743fd1c18db580589cb8552a71aa689f9d /privileged/environment/assets/blade-0.stl /privileged/environment/assets/blade-1.stl /privileged/environment/assets/blade-2.stl /opt/tools/assets/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
