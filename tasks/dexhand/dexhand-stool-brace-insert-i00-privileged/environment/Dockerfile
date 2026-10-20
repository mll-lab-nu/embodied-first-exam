FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.1.1@sha256:5da16fab7b26a7cdd7433ef32b8ead9286a9cf31da833d006f7b4d3e565e1ac9 /privileged/environment/hands.py /privileged/environment/variants/da01e9e342/catalog.json /privileged/environment/variants/d834df3fd3/checker.py /privileged/environment/variants/8a89601fb3/replay.py /privileged/environment/variants/200e107768/runtime.py /privileged/environment/variants/a474b21f41/scene.py /privileged/environment/variants/8ecb966547/task.json /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.1.1@sha256:5da16fab7b26a7cdd7433ef32b8ead9286a9cf31da833d006f7b4d3e565e1ac9 /privileged/environment/assets/pine-grain.png /opt/tools/assets/pine-grain.png
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
