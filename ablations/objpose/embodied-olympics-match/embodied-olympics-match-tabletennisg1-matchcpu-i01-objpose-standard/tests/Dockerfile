# Separate verifier sandbox: grades the sim service's artifacts; needs nothing but Python.
FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
COPY test.sh /tests/test.sh
COPY grade.py /tests/grade.py
COPY eo_judge /tests/eo_judge
COPY task /tests/task
COPY sport_grade.py /tests/sport_grade.py
COPY contract.json /tests/contract.json
COPY nocode_audit.py /tests/nocode_audit.py
COPY taskspec.json /tests/taskspec.json
COPY fexam_reward.py /tests/fexam_reward.py
COPY rcb_ablation_reward.py /tests/rcb_ablation_reward.py
RUN chmod +x /tests/test.sh
# resources (PROTOCOL §6) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.5.0@sha256:ecc5f24f1516ca11711d7c2d3ac07c89f79cd9220812c1244498ec71e352402a /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
