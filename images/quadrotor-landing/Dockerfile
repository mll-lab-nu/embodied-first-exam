# Operator prepares the pinned residual before building; never use this image as the agent base.
FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends libgl1 libosmesa6 ffmpeg && rm -rf /var/lib/apt/lists/*
COPY images/quadrotor-landing/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt scipy==1.17.0
COPY images/quadrotor-landing/assets/residual.npz images/quadrotor-landing/assets/provenance.json /opt/landing/
RUN python -c "import hashlib; assert hashlib.sha256(open('/opt/landing/residual.npz','rb').read()).hexdigest() == 'bebb6c7f9bc7364b296006c77542a9698162665dac6fb74e769e5583fc7a00ef'"
ENV PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 MUJOCO_GL=osmesa LP_NUM_THREADS=4 LANDING_RENDER_QUALITY=cpu
WORKDIR /srv
