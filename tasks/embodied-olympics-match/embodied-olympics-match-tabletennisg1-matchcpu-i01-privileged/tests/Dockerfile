# The privileged twin's verifier: the sim service's image; the trusted simulator (root only) and a public read-only
# copy for the program (/opt/dev), both the image's own /srv plus tools/g1tt_priv.
FROM ghcr.io/mll-lab-nu/efe:embodied-olympics-match-tabletennisg1-0.1.0@sha256:8bc6d02f91aa5730bbf93bc5c1c4a477feee6f5846ff8c609aaa3a25e0eb36af
ENV PYTHONDONTWRITEBYTECODE=1 MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
RUN mkdir -p /opt/trusted && cp -a /srv /opt/trusted/sim && cp -a /srv /opt/dev && mkdir -p /opt/trusted/sim/tools /opt/dev/tools
COPY g1tt_priv/ /opt/trusted/sim/tools/g1tt_priv/
COPY g1tt_priv/ /opt/dev/tools/g1tt_priv/
COPY formal.py /opt/trusted/formal.py
COPY match_instance.json test.sh /tests/
RUN chmod 700 /opt/trusted && chmod -R a-w,a+rX /opt/dev && chmod +x /tests/test.sh && mkdir -p /logs/verifier
WORKDIR /opt/trusted
# resources (PROTOCOL §6) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.5.0@sha256:ecc5f24f1516ca11711d7c2d3ac07c89f79cd9220812c1244498ec71e352402a /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
