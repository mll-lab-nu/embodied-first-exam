# Privileged mode: the agent and the simulator share this container (docs/protocol/README.md §3). eai-ispatialgym, with a layer
# that removes what states or solves a task and asserts nothing of it is left (scrub.sh, bind-mounted for the build only),
# and this task's frozen start (instance.json, the copy the standard twin and the verifier also hold): no goal, no target,
# no success check here; the verifier has them (tests/).
FROM ghcr.io/mll-lab-nu/efe-private:ispatialgym-0.2.0
COPY instance.json /app/instance.json
COPY goal.png /app/goal.png
COPY --from=ghcr.io/mll-lab-nu/efe-private:ispatialgym-files-0.1.0@sha256:d7698c93db51cd166c0523be6ca01fe662a54016be37e8b0897efc939b6963cc /privileged/environment/rcb_ispatialgym.py /opt/tools/rcb_ispatialgym.py
RUN --mount=type=bind,source=scrub,target=/tmp/scrub sh /tmp/scrub/scrub.sh \
      /opt/ispatialgym/ispatialgym/assets/bddl/activity_definitions/camera_relocalization/problem2.bddl && mkdir -p /app/output
ENV PYTHONPATH=/opt/tools OMNIGIBSON_HEADLESS=1
WORKDIR /app
