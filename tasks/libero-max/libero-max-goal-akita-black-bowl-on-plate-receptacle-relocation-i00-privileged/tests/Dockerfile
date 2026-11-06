# Separate verifier sandbox: the same image with the verifier's own copies of the tooling and the frozen instance;
# only the declared artifacts (/app/output/) arrive from the agent.
FROM ghcr.io/mll-lab-nu/efe:libero-max-0.1.1
COPY test.sh instance.json /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:libero-max-files-0.4.1@sha256:2e9e6f1c7bb3835523d2b6694aaaabb052fee0683abe81e1bf530918428cab11 /privileged/environment/lmx_tool.py /privileged/tests/grade.py /tests/
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests:/opt/libero-max/overlay:/opt/libero-max/src
WORKDIR /tests
# resources (PROTOCOL §6) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.5.0@sha256:ecc5f24f1516ca11711d7c2d3ac07c89f79cd9220812c1244498ec71e352402a /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
