FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.5.0@sha256:7dd5f1b6f2f7ff07177fd29ca94c58f814020de5ad00367a3f8b617afad3cac8 /privileged/environment/hands.py /privileged/tests/grade.py /privileged/tests/checked_replay.py /privileged/environment/variants/ee9d42f685/catalog.json /privileged/environment/variants/224ae0a903/replay.py /privileged/environment/variants/c8196a34ef/runtime.py /privileged/environment/variants/d820e9bb74/task.json /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.5.0@sha256:7dd5f1b6f2f7ff07177fd29ca94c58f814020de5ad00367a3f8b617afad3cac8 /privileged/environment/assets/variants/c3c6de27f8/manifest.json /privileged/environment/assets/pot_sharpa.xml /privileged/environment/assets/reset.json /tests/assets/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.5.0@sha256:7dd5f1b6f2f7ff07177fd29ca94c58f814020de5ad00367a3f8b617afad3cac8 /privileged/environment/assets/pot/pot_0.stl /privileged/environment/assets/pot/pot_1.stl /privileged/environment/assets/pot/pot_4.stl /privileged/environment/assets/pot/pot_5.stl /privileged/environment/assets/pot/pot_6.stl /tests/assets/pot/
ENV PYTHONPATH=/tests
RUN chmod +x /tests/test.sh
WORKDIR /tests
# resources (PROTOCOL §6) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.5.0@sha256:ecc5f24f1516ca11711d7c2d3ac07c89f79cd9220812c1244498ec71e352402a /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
