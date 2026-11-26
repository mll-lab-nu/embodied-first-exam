# Base image = RoboWits + Genesis 0.4.7 (see images/robowits/). Everything task-specific is copied here.
FROM ghcr.io/mll-lab-nu/efe:robowits-0.1.1
COPY instance.json /app/instance.json
COPY --from=ghcr.io/mll-lab-nu/efe:robowits-files-0.5.0@sha256:9fd037f7a00a78a598499f74e8e05f352ec64a53cd36581949c9eea9f470f154 /privileged/tests/rcb_robowits.py /opt/tools/rcb_robowits.py
ENV PYTHONPATH=/opt/tools QD_OFFLINE_CACHE=0
RUN mkdir -p /app/output
WORKDIR /app
