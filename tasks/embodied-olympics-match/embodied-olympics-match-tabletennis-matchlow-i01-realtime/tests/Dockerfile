# Separate verifier sandbox: grades the sim service's artifacts; needs nothing but Python.
FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
COPY test.sh /tests/test.sh
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-files-0.4.0@sha256:0d8eb42153dfb410f293e1ab6da62c5f3b7f08901fbb8c91f1d98e6729ebf88f /standard-realtime/tests/grade.py /tests/grade.py
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-files-0.4.0@sha256:0d8eb42153dfb410f293e1ab6da62c5f3b7f08901fbb8c91f1d98e6729ebf88f /shared/tests/sport_grade.py /tests/sport_grade.py
COPY contract.json /tests/contract.json
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-files-0.4.0@sha256:0d8eb42153dfb410f293e1ab6da62c5f3b7f08901fbb8c91f1d98e6729ebf88f /shared/tests/nocode_audit.py /tests/nocode_audit.py
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-files-0.4.0@sha256:0d8eb42153dfb410f293e1ab6da62c5f3b7f08901fbb8c91f1d98e6729ebf88f /shared/tests/seeds.py /tests/seeds.py
COPY fexam_reward.py /tests/fexam_reward.py
RUN chmod +x /tests/test.sh
# resources (PROTOCOL §6) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.5.0@sha256:ecc5f24f1516ca11711d7c2d3ac07c89f79cd9220812c1244498ec71e352402a /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
