# MyoSuite task (privileged): MyoSuite 2.12.2 on MuJoCo (images/myosuite/), the task's tooling and its frozen instance.
# CPU only. The base image has MyoSuite's trained baselines removed (they are this benchmark's reference solutions).
FROM ghcr.io/mll-lab-nu/efe:myosuite-0.1.1
COPY instance.npz /app/instance.npz
COPY --from=ghcr.io/mll-lab-nu/efe:myosuite-files-0.6.0@sha256:8130d2e62a65ff7e8b092823e84a64bb2b36ef6c7f04aa4b91e4242a9d3da33f /privileged/environment/rcb_myosuite.py /opt/tools/rcb_myosuite.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
