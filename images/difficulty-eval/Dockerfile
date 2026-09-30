FROM docker:28.4.0-cli@sha256:6a73c9433f2ba4279815be1e60f5739288b939dda1e48151d8c393537802de37 AS docker
FROM node:22.20.0-bookworm-slim@sha256:b21fe589dfbe5cc39365d0544b9be3f1f33f55f3c86c87a76ff65a02f8f5848e AS codex
RUN npm install -g @openai/codex@0.157.0 && npm cache clean --force
FROM python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
RUN apt-get update && apt-get install -y --no-install-recommends bash ca-certificates curl git ripgrep libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=docker /usr/local/bin/docker /usr/local/bin/docker
COPY --from=docker /usr/local/libexec/docker/cli-plugins/ /usr/local/libexec/docker/cli-plugins/
COPY --from=codex /usr/local/ /usr/local/
COPY requirements/difficulty-eval-controller.lock /opt/requirements/controller.lock
RUN pip install --no-cache-dir --require-hashes -r /opt/requirements/controller.lock
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/opt/topogym \
    TOPOGYM_HARBOR=/usr/local/bin/harbor TOPOGYM_CONTAINER=1
WORKDIR /opt/topogym
COPY . /opt/topogym/
RUN chmod -R a+rX /opt/topogym
ARG BOOTSTRAP_SHA
LABEL topogym.bootstrap-sha=$BOOTSTRAP_SHA topogym.role=controller-image
RUN test -z "$BOOTSTRAP_SHA" || test "$(bash images/difficulty-eval/source_hash.sh /opt/topogym)" = "$BOOTSTRAP_SHA"
RUN python images/difficulty-eval/patch_harbor.py \
    && python scripts/difficulty_release.py build-info --bootstrap-sha "$BOOTSTRAP_SHA" \
    && python scripts/difficulty_eval.py --list-tasks \
    && python scripts/sample_difficulty_instances.py --output /tmp/topogym-plan-build \
    && rm -rf /tmp/topogym-plan-build \
    && codex --version && harbor --version && docker compose version
ENTRYPOINT ["bash", "/opt/topogym/images/difficulty-eval/entrypoint.sh"]
