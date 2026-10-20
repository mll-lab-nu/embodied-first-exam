# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:olympiad-0.1.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 /sim/variants/fe6241f817/metering/ /srv/metering/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 /privileged/environment/fullsim/renderers/ /srv/renderers/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 /sim/bodies/hands/ /srv/bodies/hands/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 /privileged/environment/fullsim/skilleval/probe/ /srv/skilleval/probe/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 /sim/sport/opponents/ /srv/sport/opponents/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 /sim/skilleval/tests/fixture/ /srv/skilleval/tests/fixture/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 /shared/tests/grade.py /srv/core/grading.py
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 \
     /sim/bodies/__init__.py \
     /sim/bodies/assembly.py \
     /sim/bodies/configuration.json \
     /sim/bodies/contacts.py \
     /privileged/environment/fullsim/bodies/limits.py \
     /privileged/environment/fullsim/bodies/selfcollision.py \
     /privileged/environment/fullsim/bodies/servo.py \
     /privileged/environment/fullsim/bodies/sources.py \
     /srv/bodies/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 \
     /sim/bodies/ssl_robot/LICENSE \
     /sim/core/metering/__init__.py \
     /sim/bodies/ssl_robot/assist.py \
     /sim/bodies/ssl_robot/body.py \
     /sim/bodies/ssl_robot/body.toml \
     /sim/bodies/ssl_robot/kicker.py \
     /sim/bodies/ssl_robot/model.xml \
     /sim/bodies/ssl_robot/trajectory.py \
     /srv/bodies/ssl_robot/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 \
     /sim/core/README.md \
     /privileged/environment/fullsim/core/__init__.py \
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
     /privileged/environment/fullsim/core/spectator.py \
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
     /sim/variants/9fe653229b/core/tests/test_core.py \
     /privileged/environment/fullsim/core/tests/test_diagnose.py \
     /srv/core/tests/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 \
     /privileged/environment/fullsim/skilleval/__init__.py \
     /privileged/environment/fullsim/skilleval/cases.py \
     /privileged/environment/fullsim/skilleval/contract.py \
     /privileged/environment/fullsim/skilleval/declare.py \
     /privileged/environment/fullsim/skilleval/evaluate.py \
     /shared/environment/fullsim/skilleval/host.py \
     /privileged/environment/fullsim/skilleval/inloop.py \
     /privileged/environment/fullsim/skilleval/layer.py \
     /privileged/environment/fullsim/skilleval/runtest.py \
     /privileged/environment/fullsim/skilleval/sandbox.py \
     /privileged/environment/fullsim/skilleval/skillhost.py \
     /privileged/environment/fullsim/skilleval/toolkit.py \
     /srv/skilleval/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 /privileged/environment/fullsim/skilleval/tests/test_skilleval.py /srv/skilleval/tests/test_skilleval.py
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 /privileged/environment/fullsim/spectator/broadcast_log.py /srv/spectator/broadcast_log.py
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 \
     /shared/environment/fullsim/sports/soccer_ssl/grade.py \
     /sim/sport/skill_api.py \
     /srv/sport/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 \
     /sim/sport/sim/__init__.py \
     /sim/sport/sim/ball.py \
     /sim/sport/sim/camera.py \
     /sim/sport/sim/field.py \
     /sim/sport/sim/frames.py \
     /sim/sport/sim/odometry.py \
     /sim/sport/sim/onboard.py \
     /sim/sport/sim/referee.py \
     /sim/sport/sim/stub_robot.py \
     /sim/sport/sim/world.py \
     /srv/sport/sim/
