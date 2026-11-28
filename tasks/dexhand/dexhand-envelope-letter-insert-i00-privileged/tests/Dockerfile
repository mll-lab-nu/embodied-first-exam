FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.11.0@sha256:0fac42ee8fe3c9987a4a1a37497aca8eb990881ae42408af32c42acc4df4b23c /privileged/environment/hands.py /privileged/tests/grade.py /privileged/tests/checked_replay.py /privileged/environment/arm_rig.py /privileged/environment/variants/5fa6d893dc/catalog.json /privileged/environment/variants/2bb13ebb1b/checker.py /privileged/environment/variants/b4896254f6/replay.py /privileged/environment/variants/5661886e48/runtime.py /privileged/environment/variants/de68684f1e/scene.py /privileged/environment/variants/b3c3eacf51/task.json /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.11.0@sha256:0fac42ee8fe3c9987a4a1a37497aca8eb990881ae42408af32c42acc4df4b23c /privileged/environment/assets/letter.png /tests/assets/letter.png
ENV PYTHONPATH=/tests
RUN chmod +x /tests/test.sh
WORKDIR /tests
# resources (docs/protocol/resources.md) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.5.0@sha256:ecc5f24f1516ca11711d7c2d3ac07c89f79cd9220812c1244498ec71e352402a /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
