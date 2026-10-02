# Base image = ManiSkill 3.0.1 + SAPIEN 3.0.3 + libmypaint 1.6.1 (images/robopaint/). The agent's container holds the scene (the
# agent's copy of the frozen instance), the target picture, its licence notice and the tooling; Session.score() asks the `scorer`.
FROM ghcr.io/mll-lab-nu/eai-robopaint:0.2.0
COPY instance.json target.png NOTICE-exemplar.md ARPHICPL.TXT /app/
COPY rcb_brush.py /opt/tools/rcb_brush.py
RUN uv pip uninstall --python /opt/venv/bin/python svgpathtools && mkdir -p /app/output
ENV PYTHONPATH=/opt/tools
WORKDIR /app
