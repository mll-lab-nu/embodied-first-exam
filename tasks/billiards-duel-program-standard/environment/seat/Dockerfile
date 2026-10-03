# A seat (seat_a, seat_b): no simulator, only Python with the standard client pins (scripts/eai_standard, copied in by the
# generator), OpenCV, and the seat-aware `game` command that talks to the sim service. Both seats use this image.
FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
COPY client-requirements.txt /opt/client-requirements.txt
RUN pip install --no-cache-dir -r /opt/client-requirements.txt && pip install --no-cache-dir opencv-python-headless==5.0.0.93
ENV OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
COPY game /usr/local/bin/game
RUN chmod +x /usr/local/bin/game && mkdir -p /app/output
WORKDIR /app
