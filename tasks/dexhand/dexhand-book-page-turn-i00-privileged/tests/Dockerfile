FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.6.0@sha256:76ecdba39db6329198383e5fa6c89613bd95185ab974a2895521d32237900b24 /privileged/environment/hands.py /privileged/tests/grade.py /privileged/tests/checked_replay.py /privileged/environment/arm_rig.py /privileged/environment/variants/95910c1514/catalog.json /privileged/environment/variants/feaa1d1d97/checker.py /privileged/environment/variants/1aa464ff7f/replay.py /privileged/environment/variants/13c6999f14/runtime.py /privileged/environment/variants/1afea4c64a/scene.py /privileged/environment/variants/0e164430d9/task.json /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.6.0@sha256:76ecdba39db6329198383e5fa6c89613bd95185ab974a2895521d32237900b24 /privileged/environment/assets/cover.png /privileged/environment/assets/variants/06a814fcf5/manifest.json /privileged/environment/assets/page-01.png /privileged/environment/assets/page-02.png /privileged/environment/assets/page-03.png /privileged/environment/assets/page-04.png /privileged/environment/assets/page-05.png /privileged/environment/assets/page-06.png /privileged/environment/assets/page-07.png /privileged/environment/assets/page-08.png /privileged/environment/assets/page-09.png /privileged/environment/assets/page-10.png /privileged/environment/assets/page-11.png /privileged/environment/assets/page-12.png /privileged/environment/assets/page-13.png /privileged/environment/assets/page-14.png /privileged/environment/assets/page-15.png /privileged/environment/assets/page-16.png /tests/assets/
ENV PYTHONPATH=/tests
RUN chmod +x /tests/test.sh
WORKDIR /tests
# resources (PROTOCOL §6) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.5.0@sha256:ecc5f24f1516ca11711d7c2d3ac07c89f79cd9220812c1244498ec71e352402a /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
