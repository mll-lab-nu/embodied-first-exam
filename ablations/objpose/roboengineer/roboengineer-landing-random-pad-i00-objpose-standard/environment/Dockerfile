FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends libgl1 libosmesa6 && rm -rf /var/lib/apt/lists/*
COPY nominal-requirements.txt /tmp/nominal-requirements.txt
RUN pip install --no-cache-dir -r /tmp/nominal-requirements.txt
WORKDIR /app
COPY public/scripts /app/scripts
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.3.0-abl-pose@sha256:29dcec8ca59eb0522c6676c6157ee67c34f7b839458b2adc4ebfd5cc0ca29d6e /standard/environment/public/scripts/quadrotor_landing/public/client.py /standard/environment/public/scripts/quadrotor_landing/public/model.py /standard/environment/public/scripts/quadrotor_landing/public/nominal.py /standard/environment/public/scripts/quadrotor_landing/public/policy.py /app/scripts/quadrotor_landing/public/
ENV PYTHONPATH=/app PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 MUJOCO_GL=osmesa LANDING_SERVICE_URL=http://127.0.0.1:8000
RUN mkdir -p /app/output
