# Separate verifier sandbox (PROTOCOL §4): the same simulator image with the verifier's own copies of the tooling and the graders'
# frozen instance (+ the target picture and its licence) baked in. Nothing the agent did in its container reaches this one — Harbor
# uploads only the declared artifacts (/app/output/), so a patched scorer or a swapped interpreter cannot influence the verdict.
FROM ghcr.io/mll-lab-nu/efe:robopaint-0.2.0
COPY instance.json test.sh NOTICE-exemplar.md /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:robopaint-pictures-files-0.1.0@sha256:3ce92526aa79918994ccb934390221e1dd6c3f4364109a40e5746140def6062e /xingshu-feng-i00/target.png /tests/target.png
COPY --from=ghcr.io/mll-lab-nu/efe:robopaint-files-0.1.1@sha256:09f9ccd61a130b651b6eeb7475be7bd9d31cc46f6f41e7a09bf4fae9a184a3b5 /privileged/grade.py /tests/grade.py
COPY --from=ghcr.io/mll-lab-nu/efe:robopaint-files-0.1.1@sha256:09f9ccd61a130b651b6eeb7475be7bd9d31cc46f6f41e7a09bf4fae9a184a3b5 /rcb_brush.py /tests/rcb_brush.py
COPY --from=ghcr.io/mll-lab-nu/efe:robopaint-files-0.1.1@sha256:09f9ccd61a130b651b6eeb7475be7bd9d31cc46f6f41e7a09bf4fae9a184a3b5 /rcb_brush_score.py /tests/rcb_brush_score.py
COPY --from=ghcr.io/mll-lab-nu/efe:robopaint-files-0.1.1@sha256:09f9ccd61a130b651b6eeb7475be7bd9d31cc46f6f41e7a09bf4fae9a184a3b5 /rcb_brush_strict.py /tests/rcb_brush_strict.py
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests
WORKDIR /tests
# resource limits: the verifier step (from the monitor image) and its copy of the limits (docs/protocol/README.md §2.10) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.3.0@sha256:53154417782408df8309194971b08b18c3682d2b337e2e3b2eb4c88fe025ab85 /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
