# MyoSuite task (privileged): MyoSuite 2.12.2 on MuJoCo (images/myosuite/), the task's tooling and its frozen instance.
# CPU only. The base image has MyoSuite's trained baselines removed (they are this benchmark's reference solutions).
FROM ghcr.io/mll-lab-nu/efe:myosuite-0.1.1
COPY instance.npz /app/instance.npz
COPY --from=ghcr.io/mll-lab-nu/efe:myosuite-files-0.9.0@sha256:ac495582d703fef1a000932aa461f1bb2500a79c1ac503025a9683becde529d8 /privileged/environment/rcb_myosuite.py /opt/tools/rcb_myosuite.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
