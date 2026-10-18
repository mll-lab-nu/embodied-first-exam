# Separate verifier sandbox: grades the sim service's artifacts; needs nothing but Python.
FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
COPY test.sh /tests/test.sh
COPY grade.py /tests/grade.py
COPY sport_grade.py /tests/sport_grade.py
COPY contract.json /tests/contract.json
COPY nocode_audit.py /tests/nocode_audit.py
COPY seeds.py /tests/seeds.py
COPY fexam_reward.py /tests/fexam_reward.py
RUN chmod +x /tests/test.sh
# resource limits: the verifier step and its copy of the limits (docs/protocol/README.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
