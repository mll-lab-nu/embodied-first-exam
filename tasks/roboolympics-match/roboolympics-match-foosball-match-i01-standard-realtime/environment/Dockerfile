# The player's container: no simulator, only Python with the standard client pins and the generic `game`
# command of the core (core/game.py, the sport's shortcuts filled in by tools/generate.py).
FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
COPY client-requirements.txt /opt/client-requirements.txt
RUN pip install --no-cache-dir -r /opt/client-requirements.txt
COPY --from=ghcr.io/mll-lab-nu/efe:roboolympics-match-files-0.1.0@sha256:a66af6a80dec19c3c27fc8099c1fe9f64449344eefcb27b9b68bb05e53a9b3da /standard-realtime/environment/variants/e40d94fdba/game /usr/local/bin/game
RUN chmod +x /usr/local/bin/game && mkdir -p /app/output
ENV SEAT=A
ENV SIM_URL=http://localhost:8000
WORKDIR /app
