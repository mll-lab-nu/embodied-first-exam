FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.5.0@sha256:7dd5f1b6f2f7ff07177fd29ca94c58f814020de5ad00367a3f8b617afad3cac8 /privileged/environment/hands.py /privileged/tests/grade.py /privileged/tests/checked_replay.py /privileged/environment/arm_rig.py /privileged/environment/variants/85d44635c5/catalog.json /privileged/environment/variants/cf1c141a55/checker.py /privileged/environment/variants/4c79bfe5f4/replay.py /privileged/environment/variants/969b07e0b2/runtime.py /privileged/environment/variants/95e2695c2d/scene.py /privileged/environment/variants/cf26dc5048/task.json /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.5.0@sha256:7dd5f1b6f2f7ff07177fd29ca94c58f814020de5ad00367a3f8b617afad3cac8 /privileged/environment/assets/water-lilies.png /tests/assets/water-lilies.png
ENV PYTHONPATH=/tests
RUN chmod +x /tests/test.sh
WORKDIR /tests
# resources (PROTOCOL §6) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.5.0@sha256:ecc5f24f1516ca11711d7c2d3ac07c89f79cd9220812c1244498ec71e352402a /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
