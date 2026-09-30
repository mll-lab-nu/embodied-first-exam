ARG RUNTIME_IMAGE
FROM node:22.20.0-bookworm-slim@sha256:b21fe589dfbe5cc39365d0544b9be3f1f33f55f3c86c87a76ff65a02f8f5848e AS codex
RUN npm install -g @openai/codex@0.157.0 && npm cache clean --force
FROM ${RUNTIME_IMAGE}
COPY --from=codex /usr/local/ /usr/local/
