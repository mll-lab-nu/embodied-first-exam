# Separate verifier sandbox: the same image with the verifier's own copies of the tooling and the frozen instance;
# only the declared artifacts (/app/output/) arrive from the agent.
FROM ghcr.io/mll-lab-nu/efe:robocasa-gr1-0.1.0
COPY test.sh instance.npz /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:robocasa-files-0.4.1@sha256:fdce78f8bd440933c0487383847b1b845a23b973ea33ea4dabe20c2e5a78d471 /privileged/environment/casa_tool.py /privileged/tests/grade.py /tests/
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests
WORKDIR /tests
# resources (PROTOCOL §6) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.5.0@sha256:ecc5f24f1516ca11711d7c2d3ac07c89f79cd9220812c1244498ec71e352402a /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
