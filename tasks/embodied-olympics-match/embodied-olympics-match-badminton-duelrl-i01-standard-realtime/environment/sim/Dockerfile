# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:olympiad-0.1.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 /sim/metering/ /srv/metering/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 /privileged/environment/fullsim/spectator/ /srv/spectator/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 /sim/bodies/franka_panda/ /srv/bodies/franka_panda/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 /privileged/environment/fullsim/renderers/cycles/ /srv/renderers/cycles/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 /privileged/environment/fullsim/renderers/isaac/ /srv/renderers/isaac/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 /privileged/environment/fullsim/renderers/mujoco/ /srv/renderers/mujoco/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 /privileged/environment/fullsim/renderers/mujoco_showcase/ /srv/renderers/mujoco_showcase/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 /sim/skilleval/probe/ /srv/skilleval/probe/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 /shared/environment/fullsim/sports/badminton/seat/ /srv/sport/seat/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 /sim/skilleval/tests/fixture/ /srv/skilleval/tests/fixture/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 /shared/tests/grade.py /srv/core/grading.py
COPY --from=ghcr.io/mll-lab-nu/efe:control-transfer-anycar-files-0.3.0@sha256:e2bea2b8566a020ea097719ff4ee25de59e960bc0ee6816b8aa1eae47614e329 /LICENSE.anycar /srv/renderers/presentation/LICENSE.booster_t1
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 /shared/tests/variants/9b6a93718e/sport_grade.py /srv/sport/grade.py
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 /privileged/environment/fullsim/sports/badminton/presentation/assets/LICENSE.franka_emika_panda /srv/sport/sim/scene/assets/LICENSE.menagerie-franka
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 \
     /privileged/environment/fullsim/bodies/limits.py \
     /privileged/environment/fullsim/bodies/selfcollision.py \
     /srv/bodies/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 \
     /sim/variants/f2ac92d9b2/core/README.md \
     /sim/variants/6e764a014e/core/__init__.py \
     /sim/core/builtin_seat.py \
     /privileged/environment/fullsim/core/channel.py \
     /sim/core/client.py \
     /privileged/environment/fullsim/core/diaglog.py \
     /privileged/environment/fullsim/core/diagnose.py \
     /privileged/environment/fullsim/core/episode.py \
     /sim/core/game.py \
     /privileged/environment/fullsim/core/http.py \
     /sim/core/launch.py \
     /privileged/environment/fullsim/core/local.py \
     /privileged/environment/fullsim/core/observe.py \
     /privileged/environment/fullsim/core/outcome.py \
     /privileged/environment/fullsim/core/realtime.py \
     /sim/core/rng.py \
     /privileged/environment/fullsim/core/score.py \
     /privileged/environment/fullsim/core/seats.py \
     /shared/tests/seeds.py \
     /sim/core/serve.py \
     /sim/core/service.py \
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
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 \
     /privileged/environment/fullsim/renderers/__init__.py \
     /privileged/environment/fullsim/renderers/base.py \
     /privileged/environment/fullsim/renderers/budget.py \
     /privileged/environment/fullsim/renderers/export.py \
     /privileged/environment/fullsim/renderers/label.py \
     /privileged/environment/fullsim/renderers/pathtrace.py \
     /privileged/environment/fullsim/renderers/scene_check.py \
     /srv/renderers/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 \
     /privileged/environment/fullsim/sports/badminton/presentation/assets/LICENSE.franka_emika_panda \
     /sim/renderers/presentation/LICENSE.kuka_iiwa_14 \
     /sim/renderers/presentation/__init__.py \
     /sim/renderers/presentation/assets.py \
     /sim/renderers/presentation/lod.json \
     /sim/renderers/presentation/menagerie.json \
     /srv/renderers/presentation/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 \
     /privileged/environment/fullsim/skilleval/__init__.py \
     /privileged/environment/fullsim/skilleval/cases.py \
     /privileged/environment/fullsim/skilleval/contract.py \
     /privileged/environment/fullsim/skilleval/declare.py \
     /sim/skilleval/evaluate.py \
     /shared/environment/fullsim/skilleval/host.py \
     /privileged/environment/fullsim/skilleval/inloop.py \
     /privileged/environment/fullsim/skilleval/layer.py \
     /privileged/environment/fullsim/skilleval/runtest.py \
     /sim/skilleval/sandbox.py \
     /privileged/environment/fullsim/skilleval/skillhost.py \
     /privileged/environment/fullsim/skilleval/toolkit.py \
     /srv/skilleval/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 /privileged/environment/fullsim/skilleval/tests/test_skilleval.py /srv/skilleval/tests/test_skilleval.py
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 /privileged/environment/fullsim/sports/badminton/presentation/assets/LICENSE.franka_emika_panda /srv/sport/presentation/assets/LICENSE.franka_emika_panda
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 \
     /privileged/environment/fullsim/sports/badminton/presentation/assets/franka_emika_panda/assets/link0_0.obj \
     /privileged/environment/fullsim/sports/badminton/presentation/assets/franka_emika_panda/assets/link0_1.obj \
     /privileged/environment/fullsim/sports/badminton/presentation/assets/franka_emika_panda/assets/link0_10.obj \
     /privileged/environment/fullsim/sports/badminton/presentation/assets/franka_emika_panda/assets/link0_11.obj \
     /privileged/environment/fullsim/sports/badminton/presentation/assets/franka_emika_panda/assets/link0_2.obj \
     /privileged/environment/fullsim/sports/badminton/presentation/assets/franka_emika_panda/assets/link0_3.obj \
     /privileged/environment/fullsim/sports/badminton/presentation/assets/franka_emika_panda/assets/link0_4.obj \
     /privileged/environment/fullsim/sports/badminton/presentation/assets/franka_emika_panda/assets/link0_5.obj \
     /privileged/environment/fullsim/sports/badminton/presentation/assets/franka_emika_panda/assets/link0_7.obj \
     /privileged/environment/fullsim/sports/badminton/presentation/assets/franka_emika_panda/assets/link0_8.obj \
     /privileged/environment/fullsim/sports/badminton/presentation/assets/franka_emika_panda/assets/link0_9.obj \
     /privileged/environment/fullsim/sports/badminton/presentation/assets/franka_emika_panda/assets/link1.obj \
     /privileged/environment/fullsim/sports/badminton/presentation/assets/franka_emika_panda/assets/link2.obj \
     /privileged/environment/fullsim/sports/badminton/presentation/assets/franka_emika_panda/assets/link3_0.obj \
     /privileged/environment/fullsim/sports/badminton/presentation/assets/franka_emika_panda/assets/link3_1.obj \
     /privileged/environment/fullsim/sports/badminton/presentation/assets/franka_emika_panda/assets/link3_2.obj \
     /privileged/environment/fullsim/sports/badminton/presentation/assets/franka_emika_panda/assets/link3_3.obj \
     /privileged/environment/fullsim/sports/badminton/presentation/assets/franka_emika_panda/assets/link4_0.obj \
     /privileged/environment/fullsim/sports/badminton/presentation/assets/franka_emika_panda/assets/link4_1.obj \
     /privileged/environment/fullsim/sports/badminton/presentation/assets/franka_emika_panda/assets/link4_2.obj \
     /privileged/environment/fullsim/sports/badminton/presentation/assets/franka_emika_panda/assets/link4_3.obj \
     /privileged/environment/fullsim/sports/badminton/presentation/assets/franka_emika_panda/assets/link5_0.obj \
     /privileged/environment/fullsim/sports/badminton/presentation/assets/franka_emika_panda/assets/link5_1.obj \
     /privileged/environment/fullsim/sports/badminton/presentation/assets/franka_emika_panda/assets/link5_2.obj \
     /privileged/environment/fullsim/sports/badminton/presentation/assets/franka_emika_panda/assets/link6_0.obj \
     /privileged/environment/fullsim/sports/badminton/presentation/assets/franka_emika_panda/assets/link6_1.obj \
     /privileged/environment/fullsim/sports/badminton/presentation/assets/franka_emika_panda/assets/link6_10.obj \
     /privileged/environment/fullsim/sports/badminton/presentation/assets/franka_emika_panda/assets/link6_11.obj \
     /sim/sport/presentation/assets/franka_emika_panda/assets/link6_12.obj \
     /sim/sport/presentation/assets/franka_emika_panda/assets/link6_13.obj \
     /privileged/environment/fullsim/sports/badminton/presentation/assets/franka_emika_panda/assets/link6_14.obj \
     /privileged/environment/fullsim/sports/badminton/presentation/assets/franka_emika_panda/assets/link6_15.obj \
     /privileged/environment/fullsim/sports/badminton/presentation/assets/franka_emika_panda/assets/link6_16.obj \
     /privileged/environment/fullsim/sports/badminton/presentation/assets/franka_emika_panda/assets/link6_2.obj \
     /privileged/environment/fullsim/sports/badminton/presentation/assets/franka_emika_panda/assets/link6_3.obj \
     /privileged/environment/fullsim/sports/badminton/presentation/assets/franka_emika_panda/assets/link6_4.obj \
     /privileged/environment/fullsim/sports/badminton/presentation/assets/franka_emika_panda/assets/link6_5.obj \
     /privileged/environment/fullsim/sports/badminton/presentation/assets/franka_emika_panda/assets/link6_6.obj \
     /sim/sport/presentation/assets/franka_emika_panda/assets/link6_7.obj \
     /privileged/environment/fullsim/sports/badminton/presentation/assets/franka_emika_panda/assets/link6_8.obj \
     /privileged/environment/fullsim/sports/badminton/presentation/assets/franka_emika_panda/assets/link6_9.obj \
     /privileged/environment/fullsim/sports/badminton/presentation/assets/franka_emika_panda/assets/link7_0.obj \
     /privileged/environment/fullsim/sports/badminton/presentation/assets/franka_emika_panda/assets/link7_1.obj \
     /privileged/environment/fullsim/sports/badminton/presentation/assets/franka_emika_panda/assets/link7_2.obj \
     /privileged/environment/fullsim/sports/badminton/presentation/assets/franka_emika_panda/assets/link7_3.obj \
     /privileged/environment/fullsim/sports/badminton/presentation/assets/franka_emika_panda/assets/link7_4.obj \
     /privileged/environment/fullsim/sports/badminton/presentation/assets/franka_emika_panda/assets/link7_5.obj \
     /privileged/environment/fullsim/sports/badminton/presentation/assets/franka_emika_panda/assets/link7_6.obj \
     /privileged/environment/fullsim/sports/badminton/presentation/assets/franka_emika_panda/assets/link7_7.obj \
     /srv/sport/presentation/assets/franka_emika_panda/assets/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 /privileged/environment/fullsim/sports/badminton/presentation/assets/franka_emika_panda/panda_nohand.xml /srv/sport/presentation/assets/franka_emika_panda/panda_nohand.xml
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 /privileged/environment/fullsim/sports/badminton/presentation/presentation.toml /srv/sport/presentation/presentation.toml
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 \
     /sim/sport/reference_check.py \
     /privileged/environment/fullsim/sports/badminton/robot_model.py \
     /privileged/environment/fullsim/sports/badminton/skill_api.py \
     /sim/variants/8cffd84f39/sport/sport.toml \
     /srv/sport/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 \
     /privileged/environment/fullsim/sports/badminton/sim/bduel.py \
     /privileged/environment/fullsim/sports/badminton/sim/bm.py \
     /privileged/environment/fullsim/sports/badminton/sim/wc.py \
     /srv/sport/sim/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 \
     /shared/environment/fullsim/sports/badminton/sim/scene/assets/link0.stl \
     /shared/environment/fullsim/sports/badminton/sim/scene/assets/link1.stl \
     /shared/environment/fullsim/sports/badminton/sim/scene/assets/link2.stl \
     /shared/environment/fullsim/sports/badminton/sim/scene/assets/link3.stl \
     /shared/environment/fullsim/sports/badminton/sim/scene/assets/link4.stl \
     /shared/environment/fullsim/sports/badminton/sim/scene/assets/link5_collision_0.obj \
     /shared/environment/fullsim/sports/badminton/sim/scene/assets/link5_collision_1.obj \
     /shared/environment/fullsim/sports/badminton/sim/scene/assets/link5_collision_2.obj \
     /shared/environment/fullsim/sports/badminton/sim/scene/assets/link6.stl \
     /shared/environment/fullsim/sports/badminton/sim/scene/assets/link7.stl \
     /srv/sport/sim/scene/assets/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-sim-files-0.1.1@sha256:a6b9bafd62ee655d17a3c29abfcb7ce81c52541f2fa5c4106fccd69ed03de765 \
     /privileged/environment/fullsim/sports/badminton/sim/scene/bm_duel.xml \
     /privileged/environment/fullsim/sports/badminton/sim/scene/bm_scene.xml \
     /privileged/environment/fullsim/sports/badminton/sim/scene/mk_court.py \
     /privileged/environment/fullsim/sports/badminton/sim/scene/mk_duel_scene.py \
     /srv/sport/sim/scene/
