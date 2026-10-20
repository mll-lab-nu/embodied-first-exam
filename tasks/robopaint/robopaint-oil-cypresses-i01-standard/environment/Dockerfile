# Standard mode: the agent container has NO simulator, no brush model and no tooling — only Python, the client, the target picture
# (target.png) and its licence notice. Base image and pip pins: the one client base of every standard task
# (embodied_first_exam/standard/client.env, client-requirements.txt; written by the generator).
FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
RUN pip install --no-cache-dir certifi==2026.7.22 charset-normalizer==3.5.2 idna==3.20 numpy==2.5.3 pillow==12.3.0 requests==2.34.2 scipy==1.18.1 urllib3==2.8.0
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.2.0@sha256:f8ebfef83b723e4a1cc2ab7b7aa5bc1edbcefcc09d44b0506c070460854be064 /rcb_client.py /rcb1.py /opt/tools/
COPY NOTICE-exemplar.md /app/
COPY --from=ghcr.io/mll-lab-nu/efe:robopaint-pictures-files-0.1.0@sha256:3ce92526aa79918994ccb934390221e1dd6c3f4364109a40e5746140def6062e /oil-cypresses-i01/target.png /app/target.png
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
