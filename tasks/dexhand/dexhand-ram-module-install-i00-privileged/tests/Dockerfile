FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.9.0@sha256:0d919cb5a25357018eb8cfe31b532a510cdafcaad67383b0ffd852e0866254c7 /privileged/environment/hands.py /privileged/tests/grade.py /privileged/tests/checked_replay.py /privileged/environment/variants/ee0322ea61/catalog.json /privileged/environment/variants/436527ad9b/checker.py /privileged/environment/variants/4d69967a71/replay.py /privileged/environment/variants/3b2b1b62e2/runtime.py /privileged/environment/variants/9a1df1cf5f/scene.py /privileged/environment/variants/1797f2e12e/task.json /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.9.0@sha256:0d919cb5a25357018eb8cfe31b532a510cdafcaad67383b0ffd852e0866254c7 /privileged/environment/assets/manifest.json /privileged/environment/assets/ram-label.png /privileged/environment/assets/t28_geometry_corrections.json /privileged/environment/assets/t28_scene.xml /tests/assets/
ENV PYTHONPATH=/tests
RUN chmod +x /tests/test.sh
WORKDIR /tests
# resources (PROTOCOL §6) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.5.0@sha256:ecc5f24f1516ca11711d7c2d3ac07c89f79cd9220812c1244498ec71e352402a /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
