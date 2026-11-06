# Separate verifier sandbox (PROTOCOL §4): the MuJoCo image with the verifier's own copies of the tooling and the
# frozen instance; only the declared artifacts (/app/output/) arrive from the agent.
FROM ghcr.io/mll-lab-nu/efe:mujoco-0.1.2
COPY instance.json test.sh /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:mujoco-playground-files-0.5.1@sha256:9990d2f1e2f7771f2da16ad8f69e07b06a2e8a989ff51f02489178ed0b87fbae /privileged/environment/rcb_panda.py /privileged/tests/variants/c5bde2d42e/grade.py /tests/
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests
WORKDIR /tests
# resources (PROTOCOL §6) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.5.0@sha256:ecc5f24f1516ca11711d7c2d3ac07c89f79cd9220812c1244498ec71e352402a /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
