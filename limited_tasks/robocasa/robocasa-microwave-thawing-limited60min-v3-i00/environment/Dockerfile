FROM docker.io/library/python:3.11.13-slim-bookworm
RUN pip install --no-cache-dir numpy==1.26.4 pillow==10.4.0
COPY client/ /app/
WORKDIR /app
ENV PYTHONPATH=/app
RUN mkdir -p /app/output
