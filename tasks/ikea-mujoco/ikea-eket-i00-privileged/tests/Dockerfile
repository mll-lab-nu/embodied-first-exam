# Separate verifier sandbox (PROTOCOL §4): the same image with the verifier's own copies of the tooling and the scene's
# binding. Harbor uploads only the declared artifacts (/app/output/), so nothing the agent changed in its container
# reaches the verdict.
FROM ghcr.io/mll-lab-nu/efe:ikea-mujoco-0.3.0
# Replay video (PROTOCOL §4, board 0136; evidence only): MuJoCo's renderer on CPU software OpenGL (OSMesa) and ffmpeg.
# --no-deps: the physics packages (mujoco, numpy) stay the base image's, unchanged (the grader checks the runtime binding).
RUN apt-get update && apt-get install -y --no-install-recommends libosmesa6=25.0.7-2+deb13u1 && rm -rf /var/lib/apt/lists/*  && pip install --no-cache-dir --no-deps PyOpenGL==3.1.10 imageio==2.37.0 imageio-ffmpeg==0.6.0 pillow==12.3.0
ENV MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa
COPY video_view.json test.sh runtime_binding.json /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:ikea-mujoco-files-0.2.0@sha256:ef781f64782ba358796690541cee410d3fa50f1d33af9e39247011a668b35065 /privileged/environment/rcb_ikea.py /privileged/tests/grade.py /privileged/tests/render_video.py /tests/
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests
WORKDIR /tests
# resource limits: the verifier step (from the monitor image) and its copy of the limits (docs/protocol/README.md §2.10) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.2.0@sha256:65442d9e9eeb493d785a59d48a321345e2b48186946cc9d55beb684182514b4b /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
