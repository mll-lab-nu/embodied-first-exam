# Separate verifier sandbox: the same image with the verifier's own copies of the tooling and the frozen instance;
# only the declared artifacts (/app/output/) arrive from the agent.
FROM ghcr.io/mll-lab-nu/efe:robocasa365-0.1.0
COPY test.sh instance.npz /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:robocasa365-files-0.8.0@sha256:ad8015a0b5be06e76f69125f7feecf0a79f7a7777cd6a58ac75039acc33ba8fc /privileged/environment/casa_tool.py /tests/casa_tool.py
COPY --from=ghcr.io/mll-lab-nu/efe:robocasa-files-0.7.0@sha256:bb997aaf05146f51c3db1683a44d951771d122de25c530b524083b0b990ef080 /privileged/tests/grade.py /tests/grade.py
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests
WORKDIR /tests
# resources (PROTOCOL §6) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.5.0@sha256:ecc5f24f1516ca11711d7c2d3ac07c89f79cd9220812c1244498ec71e352402a /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
