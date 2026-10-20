# Separate verifier sandbox: grades the sim service's artifacts; needs nothing but Python.
FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
COPY test.sh /tests/test.sh
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-files-0.1.2@sha256:c0925be70f6af507ffa373b136519456d18c283af22e5ea6a74700bab88cd9bb /shared/tests/grade.py /tests/grade.py
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-files-0.1.2@sha256:c0925be70f6af507ffa373b136519456d18c283af22e5ea6a74700bab88cd9bb /shared/tests/variants/9b6a93718e/sport_grade.py /tests/sport_grade.py
COPY contract.json /tests/contract.json
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-files-0.1.2@sha256:c0925be70f6af507ffa373b136519456d18c283af22e5ea6a74700bab88cd9bb /shared/tests/nocode_audit.py /tests/nocode_audit.py
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-files-0.1.2@sha256:c0925be70f6af507ffa373b136519456d18c283af22e5ea6a74700bab88cd9bb /shared/tests/seeds.py /tests/seeds.py
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-files-0.1.2@sha256:c0925be70f6af507ffa373b136519456d18c283af22e5ea6a74700bab88cd9bb /standard-realtime/tests/fexam_reward.py /tests/fexam_reward.py
RUN chmod +x /tests/test.sh
# resource limits: the verifier step (from the monitor image) and its copy of the limits (docs/protocol/README.md §2.10) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.3.0@sha256:53154417782408df8309194971b08b18c3682d2b337e2e3b2eb4c88fe025ab85 /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
