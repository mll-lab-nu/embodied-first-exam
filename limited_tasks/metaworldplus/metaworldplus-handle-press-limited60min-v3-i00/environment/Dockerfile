FROM python:3.10.18-slim-bookworm@sha256:445b9efb2c047a7ccdb30d293fd6b1aa0f62a55062dc2b69051df91e10848749
RUN pip install --no-cache-dir numpy==1.26.4 scipy==1.14.0 pillow==10.4.0
WORKDIR /app
COPY client/ /app/
RUN mkdir -p /app/output
ENV PYTHONPATH=/app PYTHONUNBUFFERED=1
