# The privileged twin's development container: the sim service's image (the formal match's Python, MuJoCo 3.3.7 and
# NumPy builds: PROTOCOL H.7) with a full copy of the simulator at /opt/fullsim (the sim tree /srv, the seat's robot
# toolkit in sport/seat included, plus tools/g1tt_priv: the formal match's runner) and the rules (the seat's
# /opt/rules/RULES.md, copied from the seat image).
FROM ghcr.io/mll-lab-nu/efe:embodied-olympics-match-tabletennisg1-0.1.0@sha256:8bc6d02f91aa5730bbf93bc5c1c4a477feee6f5846ff8c609aaa3a25e0eb36af
RUN cp -a /srv /opt/fullsim && mkdir -p /opt/fullsim/tools /app/output
COPY g1tt_priv/ /opt/fullsim/tools/g1tt_priv/
COPY rules/ /opt/rules/
ENV PYTHONPATH=/opt/fullsim PYTHONDONTWRITEBYTECODE=1 MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
RUN chmod -R a+rX /opt/fullsim /opt/rules
WORKDIR /app
