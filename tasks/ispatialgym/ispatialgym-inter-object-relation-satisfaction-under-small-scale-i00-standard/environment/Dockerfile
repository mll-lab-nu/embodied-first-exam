# Standard mode: the agent container has NO simulator and no iSpatialGym code — only Python, the client and the goal
# image. The base image and the pip pins are the shared eai-standard client (embodied_first_exam/standard/client.env,
# client-requirements.txt).
FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
COPY client-requirements.txt /tmp/client-requirements.txt
RUN pip install --no-cache-dir -r /tmp/client-requirements.txt
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.2.0@sha256:f8ebfef83b723e4a1cc2ab7b7aa5bc1edbcefcc09d44b0506c070460854be064 /rcb_client.py /rcb1.py /opt/tools/
ENV PYTHONPATH=/opt/tools
COPY --from=ghcr.io/mll-lab-nu/efe:ispatialgym-goals-files-0.1.0@sha256:a5b14edb2270793a3d97edeb2ff151646532f30221fe40b55867d33732c97e7f /inter-object-relation-satisfaction-under-small-scale-i00/goal.png /app/goal.png
RUN mkdir -p /app/output
WORKDIR /app
