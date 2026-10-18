# Separate verifier sandbox (PROTOCOL §4): the same simulator image with the verifier's own copies of the tooling and the graders'
# frozen instance (+ the target picture and its licence) baked in. Nothing the agent did in its container reaches this one — Harbor
# uploads only the declared artifacts (/app/output/), so a patched scorer or a swapped interpreter cannot influence the verdict.
FROM ghcr.io/mll-lab-nu/eai-robopaint:0.2.0
COPY grade.py instance.json target.png rcb_brush.py rcb_brush_score.py rcb_brush_strict.py test.sh NOTICE-exemplar.md /tests/
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests
WORKDIR /tests
# resource limits: the verifier step and its copy of the limits (docs/protocol/README.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
