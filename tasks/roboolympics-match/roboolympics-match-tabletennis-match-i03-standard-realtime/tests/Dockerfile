# Separate verifier sandbox: grades the sim service's artifacts; needs nothing but Python.
FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
COPY test.sh /tests/test.sh
COPY --from=ghcr.io/mll-lab-nu/efe:roboolympics-match-files-0.1.1@sha256:90ff02735ace55c77f571a3c7fd602ef0fb295fd27837d6734e5b7cc3cf5cc05 /shared/tests/grade.py /tests/grade.py
COPY --from=ghcr.io/mll-lab-nu/efe:roboolympics-match-files-0.1.1@sha256:90ff02735ace55c77f571a3c7fd602ef0fb295fd27837d6734e5b7cc3cf5cc05 /shared/tests/sport_grade.py /tests/sport_grade.py
COPY --from=ghcr.io/mll-lab-nu/efe:roboolympics-match-files-0.1.1@sha256:90ff02735ace55c77f571a3c7fd602ef0fb295fd27837d6734e5b7cc3cf5cc05 /standard-realtime/tests/contract.json /tests/contract.json
COPY --from=ghcr.io/mll-lab-nu/efe:roboolympics-match-files-0.1.1@sha256:90ff02735ace55c77f571a3c7fd602ef0fb295fd27837d6734e5b7cc3cf5cc05 /shared/tests/nocode_audit.py /tests/nocode_audit.py
COPY --from=ghcr.io/mll-lab-nu/efe:roboolympics-match-files-0.1.1@sha256:90ff02735ace55c77f571a3c7fd602ef0fb295fd27837d6734e5b7cc3cf5cc05 /shared/tests/seeds.py /tests/seeds.py
COPY fexam_reward.py /tests/fexam_reward.py
RUN chmod +x /tests/test.sh
# resource limits: the verifier step (from the monitor image) and its copy of the limits (docs/protocol/README.md §2.10) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.2.0@sha256:65442d9e9eeb493d785a59d48a321345e2b48186946cc9d55beb684182514b4b /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
