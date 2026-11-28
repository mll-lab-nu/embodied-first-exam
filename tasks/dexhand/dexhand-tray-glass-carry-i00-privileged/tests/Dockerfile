FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.11.0@sha256:0fac42ee8fe3c9987a4a1a37497aca8eb990881ae42408af32c42acc4df4b23c /privileged/environment/hands.py /privileged/tests/grade.py /privileged/tests/checked_replay.py /privileged/environment/catalog.json /privileged/environment/variants/bd227f1806/checker.py /privileged/environment/variants/b8d126ab19/replay.py /privileged/environment/variants/edb2fa483d/runtime.py /privileged/environment/variants/833515eb2e/scene.py /privileged/environment/variants/36fdc6d2ed/task.json /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.11.0@sha256:0fac42ee8fe3c9987a4a1a37497aca8eb990881ae42408af32c42acc4df4b23c /privileged/environment/assets/sharpa_bimanual_hands.xml /privileged/environment/assets/t48_tray_glasses.xml /tests/assets/
ENV PYTHONPATH=/tests
RUN chmod +x /tests/test.sh
WORKDIR /tests
# resources (docs/protocol/resources.md) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.5.0@sha256:ecc5f24f1516ca11711d7c2d3ac07c89f79cd9220812c1244498ec71e352402a /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
