# Base image = ManiSkill 3.0.1 + SAPIEN 3.0.3 + libmypaint 1.6.1 (images/robopaint/). The agent's container holds the scene (the
# agent's copy of the frozen instance), the target picture, its licence notice and the tooling; Session.score() asks the `scorer`.
FROM ghcr.io/mll-lab-nu/efe:robopaint-0.2.0
COPY instance.json NOTICE-exemplar.md /app/
COPY --from=ghcr.io/mll-lab-nu/efe:robopaint-pictures-files-0.1.0@sha256:3ce92526aa79918994ccb934390221e1dd6c3f4364109a40e5746140def6062e /oil-saintevictoire-i01/target.png /app/target.png
COPY --from=ghcr.io/mll-lab-nu/efe:robopaint-files-0.1.0@sha256:e97f8e066284e7490b3dc8bc24f9b634761f95396e8236bced1ff445c271355f /rcb_brush.py /opt/tools/rcb_brush.py
RUN uv pip uninstall --python /opt/venv/bin/python svgpathtools && mkdir -p /app/output
ENV PYTHONPATH=/opt/tools
WORKDIR /app
