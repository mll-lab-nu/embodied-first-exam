# LabUtopia task (privileged): LabUtopia on Isaac Sim (images/labutopia/), the task's tooling and its frozen instance.
# The base image has LabUtopia's scripted controllers removed (they are this benchmark's reference solutions).
FROM ghcr.io/mll-lab-nu/eai-labutopia:0.1.0
COPY instance.json /app/instance.json
COPY rcb_labutopia.py /opt/tools/rcb_labutopia.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
