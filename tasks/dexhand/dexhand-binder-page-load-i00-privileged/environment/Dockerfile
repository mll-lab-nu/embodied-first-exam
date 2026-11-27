FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.11.0@sha256:4e16e8b63a4d2c93ed37a7a8b24ba27238c4a81764b9a9f02446640defa55519 /privileged/environment/hands.py /privileged/environment/variants/712876a05f/catalog.json /privileged/environment/variants/cbf4353688/checker.py /privileged/environment/variants/95a47458e9/replay.py /privileged/environment/variants/979d961057/runtime.py /privileged/environment/variants/be8d26ca72/scene.py /privileged/environment/variants/af2dff5621/task.json /opt/tools/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
