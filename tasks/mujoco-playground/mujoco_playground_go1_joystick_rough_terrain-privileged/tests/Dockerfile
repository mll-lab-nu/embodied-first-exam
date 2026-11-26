# Separate verifier sandbox (PROTOCOL §4): the same image with the verifier's own copies of the tooling and the frozen
# instance. Nothing the agent did in its container reaches this one: Harbor uploads only the declared artifacts.
FROM ghcr.io/mll-lab-nu/efe:mujoco-0.1.3
COPY instance.json test.sh /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:mujoco-playground-files-0.7.0@sha256:347e83daa4047f377fc94b83537d406fa4c5c6c79b6b18367aba47ccd652659b /privileged/environment/rcb_quadruped.py /privileged/tests/grade.py /tests/
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests
WORKDIR /tests
# resources (PROTOCOL §6) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.5.0@sha256:ecc5f24f1516ca11711d7c2d3ac07c89f79cd9220812c1244498ec71e352402a /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
