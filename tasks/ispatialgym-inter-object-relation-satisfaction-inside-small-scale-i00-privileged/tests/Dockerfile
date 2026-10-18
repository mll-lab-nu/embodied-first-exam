# Separate verifier sandbox (PROTOCOL §4, Appendix H.1): eai-ispatialgym as built (its BDDL problems and upstream's own
# success check), the frozen start every copy shares, this task's goal.json (restored onto it and checked against
# upstream's TRO by sha256), the measured facts and the tooling. Only /app/output/ reaches it.
FROM ghcr.io/mll-lab-nu/eai-ispatialgym:0.2.0
COPY instance.json goal.json facts.json upstream.json rcb_ispatialgym.py grade.py test.sh /tests/
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV OMNIGIBSON_HEADLESS=1
WORKDIR /tests
# resource limits: the verifier step and its copy of the limits (docs/protocol/README.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
