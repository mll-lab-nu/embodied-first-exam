# AutoBio task (privileged): AutoBio on MuJoCo 3.3.0 (images/autobio/), the task's tooling and its frozen instance.
# CPU only. The base image has AutoBio's scripted experts removed (they are this benchmark's reference solutions).
FROM ghcr.io/mll-lab-nu/eai-autobio:0.1.0
COPY instance.json /app/instance.json
COPY rcb_autobio.py /opt/tools/rcb_autobio.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
