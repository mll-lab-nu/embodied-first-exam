# Standard mode: the agent container has NO simulator and no DexJoCo code, only Python and the client, on the shared
# pinned client base with the shared pins (embodied_first_exam/standard/client.env, client-requirements.txt).
FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
COPY client-requirements.txt /tmp/client-requirements.txt
RUN pip install --no-cache-dir -r /tmp/client-requirements.txt
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.2.0@sha256:f8ebfef83b723e4a1cc2ab7b7aa5bc1edbcefcc09d44b0506c070460854be064 /rcb_client.py /rcb1.py /opt/tools/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
