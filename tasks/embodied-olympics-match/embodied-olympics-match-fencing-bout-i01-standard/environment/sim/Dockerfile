# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:olympiad-0.1.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 /sim/metering/ /srv/metering/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 /privileged/environment/fullsim/renderers/ /srv/renderers/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 /sim/bodies/hands/ /srv/bodies/hands/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 /sim/sport/phrases/ /srv/sport/phrases/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 /sim/bodies/unitree_g1/meshes/ /srv/bodies/unitree_g1/meshes/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 /sim/bodies/unitree_g1/meshes_25k/ /srv/bodies/unitree_g1/meshes_25k/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 /sim/bodies/unitree_g1/policy/ /srv/bodies/unitree_g1/policy/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 /shared/tests/grade.py /srv/core/grading.py
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 /standard/tests/sport_grade.py /srv/sport/grade.py
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 \
     /sim/bodies/__init__.py \
     /sim/bodies/assembly.py \
     /sim/variants/c44ee09420/bodies/configuration.json \
     /sim/bodies/contacts.py \
     /privileged/environment/fullsim/bodies/limits.py \
     /privileged/environment/fullsim/bodies/selfcollision.py \
     /privileged/environment/fullsim/bodies/servo.py \
     /privileged/environment/fullsim/bodies/sources.py \
     /srv/bodies/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 \
     /sim/bodies/unitree_g1/LICENSE \
     /sim/core/metering/__init__.py \
     /sim/bodies/unitree_g1/agile.py \
     /sim/bodies/unitree_g1/body.py \
     /sim/bodies/unitree_g1/body.toml \
     /sim/bodies/unitree_g1/falcon.py \
     /sim/bodies/unitree_g1/kick.py \
     /sim/bodies/unitree_g1/model.xml \
     /srv/bodies/unitree_g1/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 \
     /sim/variants/e1942b1e0a/core/README.md \
     /sim/variants/90659b685d/core/__init__.py \
     /privileged/environment/fullsim/core/channel.py \
     /sim/core/client.py \
     /privileged/environment/fullsim/core/diaglog.py \
     /privileged/environment/fullsim/core/diagnose.py \
     /privileged/environment/fullsim/core/episode.py \
     /sim/core/game.py \
     /privileged/environment/fullsim/core/http.py \
     /sim/variants/be82e3ee8c/core/launch.py \
     /privileged/environment/fullsim/core/local.py \
     /privileged/environment/fullsim/core/observe.py \
     /privileged/environment/fullsim/core/outcome.py \
     /sim/core/realtime.py \
     /sim/core/rng.py \
     /privileged/environment/fullsim/core/score.py \
     /sim/variants/f3714cdf28/core/seats.py \
     /shared/tests/seeds.py \
     /privileged/environment/fullsim/core/serve.py \
     /privileged/environment/fullsim/core/service.py \
     /privileged/environment/fullsim/core/spec.py \
     /sim/variants/5d35992bd9/core/spectator.py \
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
     /sim/variants/1152f6097a/core/tests/test_core.py \
     /privileged/environment/fullsim/core/tests/test_diagnose.py \
     /srv/core/tests/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 /privileged/environment/fullsim/spectator/broadcast_log.py /srv/spectator/broadcast_log.py
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 \
     /sim/sport/bout.py \
     /sim/variants/af9f8435de/sport/builtin_players.py \
     /sim/sport/cameras.py \
     /sim/sport/fencing.py \
     /sim/sport/opponent.py \
     /sim/sport/phrases.py \
     /sim/variants/afcaf8dc64/sport/plugin.py \
     /sim/variants/e0276d90dd/sport/reference_check.py \
     /sim/sport/rules_check.md \
     /sim/variants/6175a42e64/sport/sport.toml \
     /srv/sport/
