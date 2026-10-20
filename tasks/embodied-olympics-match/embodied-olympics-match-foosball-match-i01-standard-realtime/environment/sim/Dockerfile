# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:olympiad-0.1.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 /sim/metering/ /srv/metering/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 /privileged/environment/fullsim/renderers/ /srv/renderers/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 /shared/tests/grade.py /srv/core/grading.py
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 \
     /sim/variants/1952a67dfc/core/README.md \
     /sim/core/__init__.py \
     /privileged/environment/fullsim/core/channel.py \
     /sim/core/client.py \
     /privileged/environment/fullsim/core/diaglog.py \
     /privileged/environment/fullsim/core/diagnose.py \
     /privileged/environment/fullsim/core/episode.py \
     /sim/core/game.py \
     /privileged/environment/fullsim/core/http.py \
     /privileged/environment/fullsim/core/launch.py \
     /privileged/environment/fullsim/core/local.py \
     /privileged/environment/fullsim/core/observe.py \
     /privileged/environment/fullsim/core/outcome.py \
     /privileged/environment/fullsim/core/realtime.py \
     /sim/core/rng.py \
     /privileged/environment/fullsim/core/score.py \
     /privileged/environment/fullsim/core/seats.py \
     /shared/tests/seeds.py \
     /privileged/environment/fullsim/core/serve.py \
     /privileged/environment/fullsim/core/service.py \
     /privileged/environment/fullsim/core/spec.py \
     /sim/core/spectator.py \
     /privileged/environment/fullsim/core/sport.py \
     /privileged/environment/fullsim/core/testkit.py \
     /privileged/environment/fullsim/core/turn.py \
     /privileged/environment/fullsim/core/workers.py \
     /srv/core/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 \
     /sim/core/metering/__init__.py \
     /privileged/environment/fullsim/core/metering/api_errors.py \
     /privileged/environment/fullsim/core/metering/think_clock.py \
     /srv/core/metering/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 \
     /privileged/environment/fullsim/core/tests/fixture/plugin.py \
     /sim/core/tests/fixture/sport.toml \
     /srv/core/tests/fixture/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 \
     /privileged/environment/fullsim/core/tests/fixture_images/plugin.py \
     /sim/core/tests/fixture_images/sport.toml \
     /srv/core/tests/fixture_images/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 \
     /privileged/environment/fullsim/core/tests/fixture_turn/plugin.py \
     /sim/core/tests/fixture_turn/sport.toml \
     /srv/core/tests/fixture_turn/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 \
     /sim/core/tests/test_core.py \
     /privileged/environment/fullsim/core/tests/test_diagnose.py \
     /srv/core/tests/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 /privileged/environment/fullsim/spectator/broadcast_log.py /srv/spectator/broadcast_log.py
