FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.11.0@sha256:5bd382fdadf7a766bfdb014dd30350f5c1a5f87e5bcb559a3a0539b2d2cce7aa /privileged/environment/hands.py /privileged/tests/grade.py /privileged/tests/checked_replay.py /privileged/environment/variants/712876a05f/catalog.json /privileged/environment/variants/cbf4353688/checker.py /privileged/environment/variants/95a47458e9/replay.py /privileged/environment/variants/979d961057/runtime.py /privileged/environment/variants/be8d26ca72/scene.py /privileged/environment/variants/af2dff5621/task.json /tests/
ENV PYTHONPATH=/tests
RUN chmod +x /tests/test.sh
WORKDIR /tests
# resources (docs/protocol/resources.md) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.5.0@sha256:ecc5f24f1516ca11711d7c2d3ac07c89f79cd9220812c1244498ec71e352402a /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
