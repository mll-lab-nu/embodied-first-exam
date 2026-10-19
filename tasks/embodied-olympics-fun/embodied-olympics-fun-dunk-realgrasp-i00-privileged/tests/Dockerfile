# Separate verifier sandbox (PROTOCOL §2.6): the same simulator image with the verifier's own copies of the tooling, the
# world package, the family's rules and the frozen instance (the grader, the tooling and the world package's core from
# the files-only image images/embodied-olympics-fun-files/). Nothing the agent did in its container reaches this one:
# Harbor uploads only /app/output/.
FROM ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1
COPY instance.json rfo_task.py test.sh /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-files-0.1.0@sha256:49a33342a72b57b56742cc754e427205a30f39dfcd69a99d1d7275c0eae4a619 /grade.py /tests/grade.py
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-files-0.1.0@sha256:49a33342a72b57b56742cc754e427205a30f39dfcd69a99d1d7275c0eae4a619 /rcb_rfo.py /tests/rcb_rfo.py
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-files-0.1.0@sha256:49a33342a72b57b56742cc754e427205a30f39dfcd69a99d1d7275c0eae4a619 /rfo/__init__.py /tests/rfo/__init__.py
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-files-0.1.0@sha256:49a33342a72b57b56742cc754e427205a30f39dfcd69a99d1d7275c0eae4a619 /rfo/scene.py /tests/rfo/scene.py
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-files-0.1.0@sha256:49a33342a72b57b56742cc754e427205a30f39dfcd69a99d1d7275c0eae4a619 /rfo/looks.py /tests/rfo/looks.py
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-files-0.1.0@sha256:49a33342a72b57b56742cc754e427205a30f39dfcd69a99d1d7275c0eae4a619 /rfo/world.py /tests/rfo/world.py
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-files-0.1.0@sha256:49a33342a72b57b56742cc754e427205a30f39dfcd69a99d1d7275c0eae4a619 /rfo/referee.py /tests/rfo/referee.py
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-files-0.1.0@sha256:49a33342a72b57b56742cc754e427205a30f39dfcd69a99d1d7275c0eae4a619 /rfo/task.py /tests/rfo/task.py
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-files-0.1.0@sha256:49a33342a72b57b56742cc754e427205a30f39dfcd69a99d1d7275c0eae4a619 /rfo/realhand.py /tests/rfo/realhand.py
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests
WORKDIR /tests
# resource limits: the verifier step (from the monitor image) and its copy of the limits (docs/protocol/README.md §2.10) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.2.0@sha256:65442d9e9eeb493d785a59d48a321345e2b48186946cc9d55beb684182514b4b /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
