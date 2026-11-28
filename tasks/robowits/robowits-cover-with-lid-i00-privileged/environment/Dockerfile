# Base image = RoboWits + Genesis 0.4.7 (see images/robowits/). Everything task-specific is copied here.
FROM ghcr.io/mll-lab-nu/efe:robowits-0.1.1
COPY instance.json /app/instance.json
COPY --from=ghcr.io/mll-lab-nu/efe:robowits-files-0.8.0@sha256:763b7fc62cab021d13b3d5c4f3533e2a68498484687125dd08221873a5d343ef /privileged/tests/rcb_robowits.py /opt/tools/rcb_robowits.py
ENV PYTHONPATH=/opt/tools QD_OFFLINE_CACHE=0
RUN mkdir -p /app/output
WORKDIR /app
