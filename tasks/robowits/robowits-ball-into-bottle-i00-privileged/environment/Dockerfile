# Base image = RoboWits + Genesis 0.4.7 (see images/robowits/). Everything task-specific is copied here.
FROM ghcr.io/mll-lab-nu/efe:robowits-0.1.1
COPY instance.json /app/instance.json
COPY --from=ghcr.io/mll-lab-nu/efe:robowits-files-0.7.0@sha256:ce770ea26b8713a44994c36801d208d99ae44b558b5d2c5b8f40f7d8825cfdb2 /privileged/tests/rcb_robowits.py /opt/tools/rcb_robowits.py
ENV PYTHONPATH=/opt/tools QD_OFFLINE_CACHE=0
RUN mkdir -p /app/output
WORKDIR /app
