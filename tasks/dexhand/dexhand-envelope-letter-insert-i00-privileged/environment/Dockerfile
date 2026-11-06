FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.5.0@sha256:e90c3817d6fee11cd727b5f82252740849e5b66ced87c7fce411b4747e911166 /privileged/environment/hands.py /privileged/environment/arm_rig.py /privileged/environment/variants/5fa6d893dc/catalog.json /privileged/environment/variants/2bb13ebb1b/checker.py /privileged/environment/variants/b4896254f6/replay.py /privileged/environment/variants/5661886e48/runtime.py /privileged/environment/variants/eca9b98723/scene.py /privileged/environment/variants/b3c3eacf51/task.json /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.5.0@sha256:e90c3817d6fee11cd727b5f82252740849e5b66ced87c7fce411b4747e911166 /privileged/environment/assets/letter.png /opt/tools/assets/letter.png
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
