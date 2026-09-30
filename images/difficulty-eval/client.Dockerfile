FROM node:22.20.0-bookworm-slim@sha256:b21fe589dfbe5cc39365d0544b9be3f1f33f55f3c86c87a76ff65a02f8f5848e AS codex
RUN npm install -g @openai/codex@0.157.0 && npm cache clean --force
FROM python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
COPY --from=codex /usr/local/ /usr/local/
RUN apt-get update && apt-get install -y --no-install-recommends bash ca-certificates curl git ripgrep \
    && rm -rf /var/lib/apt/lists/*
COPY requirements/difficulty-eval-client.lock /opt/requirements/client.lock
RUN pip install --no-cache-dir --require-hashes -r /opt/requirements/client.lock
ENV PYTHONUNBUFFERED=1
WORKDIR /app
