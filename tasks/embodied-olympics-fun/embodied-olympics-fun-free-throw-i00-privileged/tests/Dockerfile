# Separate verifier sandbox (PROTOCOL H.1): the same simulator image with the verifier's own copies of the tooling, the
# world package, the family's rules and the frozen instance (the grader, the tooling and the world package's core from
# the files-only image images/embodied-olympics-fun-files/). Nothing the agent did in its container reaches this one:
# Harbor uploads only /app/output/.
FROM ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1
COPY instance.json rfo_task.py test.sh /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-files-0.8.0@sha256:d9c06edb0e5eb9a5c72a90fd971ae469b1758feb8a3ec76722b7f7df80013e46 /grade.py /tests/grade.py
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-files-0.8.0@sha256:d9c06edb0e5eb9a5c72a90fd971ae469b1758feb8a3ec76722b7f7df80013e46 /rcb_rfo.py /tests/rcb_rfo.py
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-files-0.8.0@sha256:d9c06edb0e5eb9a5c72a90fd971ae469b1758feb8a3ec76722b7f7df80013e46 /rfo/__init__.py /tests/rfo/__init__.py
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-files-0.8.0@sha256:d9c06edb0e5eb9a5c72a90fd971ae469b1758feb8a3ec76722b7f7df80013e46 /rfo/scene.py /tests/rfo/scene.py
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-files-0.8.0@sha256:d9c06edb0e5eb9a5c72a90fd971ae469b1758feb8a3ec76722b7f7df80013e46 /rfo/looks.py /tests/rfo/looks.py
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-files-0.8.0@sha256:d9c06edb0e5eb9a5c72a90fd971ae469b1758feb8a3ec76722b7f7df80013e46 /rfo/world.py /tests/rfo/world.py
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-files-0.8.0@sha256:d9c06edb0e5eb9a5c72a90fd971ae469b1758feb8a3ec76722b7f7df80013e46 /rfo/referee.py /tests/rfo/referee.py
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-files-0.8.0@sha256:d9c06edb0e5eb9a5c72a90fd971ae469b1758feb8a3ec76722b7f7df80013e46 /rfo/task.py /tests/rfo/task.py
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-files-0.8.0@sha256:d9c06edb0e5eb9a5c72a90fd971ae469b1758feb8a3ec76722b7f7df80013e46 /rfo/realhand.py /tests/rfo/realhand.py
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests
WORKDIR /tests
# resources (PROTOCOL §6) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.5.0@sha256:ecc5f24f1516ca11711d7c2d3ac07c89f79cd9220812c1244498ec71e352402a /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
