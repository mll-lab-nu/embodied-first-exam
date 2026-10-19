# Privileged mode: Embodied Safety Exam's simulator (ese, images/ese/) in the agent's own container. Its scripted
# solutions (every family's reference, literal execution and named strategies) are removed before the agent starts
# (scrub.py; docs/benchmarks/embodied-safety-exam.md "Privileged tasks"). The frozen instance is copied from here; scrub.py and the
# tooling come from the files-only image ese-files (images/ese-files/; source:
# embodied_first_exam/benchmarks/embodied-safety-exam/).
FROM ghcr.io/mll-lab-nu/efe-private:ese-0.5.4
COPY --from=ghcr.io/mll-lab-nu/efe-private:ese-files-0.1.0@sha256:03813f0484542de85c6c80fbc16d39787333c359ae036dd1d7d88c637a4480d1 /privileged/scrub.py /tmp/scrub.py
RUN python /tmp/scrub.py && rm /tmp/scrub.py
COPY instance.json /app/instance.json
COPY --from=ghcr.io/mll-lab-nu/efe-private:ese-files-0.1.0@sha256:03813f0484542de85c6c80fbc16d39787333c359ae036dd1d7d88c637a4480d1 /standard/rcb_rsb.py /opt/tools/rcb_rsb.py
COPY --from=ghcr.io/mll-lab-nu/efe-private:ese-files-0.1.0@sha256:03813f0484542de85c6c80fbc16d39787333c359ae036dd1d7d88c637a4480d1 /standard/candidate_identity.py /opt/tools/candidate_identity.py
COPY --from=ghcr.io/mll-lab-nu/efe-private:ese-files-0.1.0@sha256:03813f0484542de85c6c80fbc16d39787333c359ae036dd1d7d88c637a4480d1 /privileged/rcb_rsb_privileged.py /opt/tools/rcb_rsb_privileged.py
ENV PYTHONPATH=/opt/tools RCB_RSB_INSTANCE=/app/instance.json
RUN mkdir -p /app/output
WORKDIR /app
