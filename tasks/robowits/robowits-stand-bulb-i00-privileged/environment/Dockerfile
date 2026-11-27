# Base image = RoboWits + Genesis 0.4.7 (see images/robowits/). Everything task-specific is copied here.
FROM ghcr.io/mll-lab-nu/efe:robowits-0.1.1
COPY instance.json /app/instance.json
COPY --from=ghcr.io/mll-lab-nu/efe:robowits-files-0.6.0@sha256:b6288da83664c4337ff6496a7656119fa8565bfc831c18bc03a3791c68fd9546 /privileged/tests/rcb_robowits.py /opt/tools/rcb_robowits.py
ENV PYTHONPATH=/opt/tools QD_OFFLINE_CACHE=0
RUN mkdir -p /app/output
WORKDIR /app
