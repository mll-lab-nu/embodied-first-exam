FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.11.0@sha256:4e16e8b63a4d2c93ed37a7a8b24ba27238c4a81764b9a9f02446640defa55519 /privileged/environment/hands.py /privileged/environment/variants/3840cb4b04/catalog.json /privileged/environment/variants/2f476ee029/checker.py /privileged/environment/variants/d2bc9037f8/replay.py /privileged/environment/variants/eb836781a3/runtime.py /privileged/environment/variants/862070f80d/scene.py /privileged/environment/variants/b8a169a7d9/task.json /opt/tools/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
