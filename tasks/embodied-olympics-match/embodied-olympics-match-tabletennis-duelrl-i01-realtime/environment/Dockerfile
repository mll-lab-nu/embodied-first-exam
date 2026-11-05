# The player's container: no simulator, only Python with the standard client pins and the generic `game`
# command of the core (core/game.py, the sport's shortcuts filled in by tools/generate.py).
FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
COPY client-requirements.txt /opt/client-requirements.txt
RUN pip install --no-cache-dir -r /opt/client-requirements.txt
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-files-0.3.0@sha256:0c6710ec1d7682bc4bf1b828a71d4c8b6c21193a279f13ad7e39d683307a95af /standard-realtime/environment/game /usr/local/bin/game
RUN chmod +x /usr/local/bin/game && mkdir -p /app/output
# sport.toml [seat] / [seat.high]: the player image's extras for this task
RUN pip install --no-cache-dir -c /opt/client-requirements.txt opencv-python-headless==5.0.0.93 && pip check
ENV SEAT=A
ENV SIM_URL=http://localhost:8000
WORKDIR /app
