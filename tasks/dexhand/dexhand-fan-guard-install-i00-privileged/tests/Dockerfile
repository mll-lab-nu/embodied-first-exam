FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.11.0@sha256:4e16e8b63a4d2c93ed37a7a8b24ba27238c4a81764b9a9f02446640defa55519 /privileged/environment/hands.py /privileged/tests/grade.py /privileged/tests/checked_replay.py /privileged/environment/variants/5504b0fa5b/catalog.json /privileged/environment/variants/19a12120ad/checker.py /privileged/environment/geometry.py /privileged/environment/variants/fef84ad4b3/replay.py /privileged/environment/variants/7e3fcc99ed/runtime.py /privileged/environment/variants/594155d137/scene.py /privileged/environment/variants/e8011d953f/task.json /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.11.0@sha256:4e16e8b63a4d2c93ed37a7a8b24ba27238c4a81764b9a9f02446640defa55519 /privileged/environment/assets/blade-0.stl /privileged/environment/assets/blade-1.stl /privileged/environment/assets/blade-2.stl /tests/assets/
ENV PYTHONPATH=/tests
RUN chmod +x /tests/test.sh
WORKDIR /tests
# resources (PROTOCOL §6) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.5.0@sha256:ecc5f24f1516ca11711d7c2d3ac07c89f79cd9220812c1244498ec71e352402a /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
