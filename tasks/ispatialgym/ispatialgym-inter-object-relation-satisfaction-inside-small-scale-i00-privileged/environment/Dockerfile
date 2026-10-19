# Privileged mode: the agent and the simulator share this container (docs/protocol/README.md §3). eai-ispatialgym, with a layer
# that removes what states or solves a task and asserts nothing of it is left (scrub.sh, bind-mounted for the build only),
# and this task's frozen start (instance.json, the copy the standard twin and the verifier also hold): no goal, no target,
# no success check here; the verifier has them (tests/).
FROM ghcr.io/mll-lab-nu/efe-private:ispatialgym-0.2.0
COPY instance.json /app/instance.json
COPY --from=ghcr.io/mll-lab-nu/efe:ispatialgym-goals-files-0.1.0@sha256:a5b14edb2270793a3d97edeb2ff151646532f30221fe40b55867d33732c97e7f /inter-object-relation-satisfaction-inside-small-scale-i00/goal.png /app/goal.png
COPY --from=ghcr.io/mll-lab-nu/efe:ispatialgym-files-0.2.0@sha256:f07933a4ac0bab0b0743f4754d67587798e70e47c10057c44827a94d6cbb8ea9 /privileged/environment/rcb_ispatialgym.py /opt/tools/rcb_ispatialgym.py
RUN --mount=type=bind,source=scrub,target=/tmp/scrub sh /tmp/scrub/scrub.sh \
      /opt/ispatialgym/ispatialgym/assets/bddl/activity_definitions/inter_object_relation_satisfaction/problem0.bddl && mkdir -p /app/output
ENV PYTHONPATH=/opt/tools OMNIGIBSON_HEADLESS=1
WORKDIR /app
