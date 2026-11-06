# Separate verifier sandbox (PROTOCOL §4): the same image with the verifier's own copies of the tooling and the scene's
# binding. Harbor uploads only the declared artifacts (/app/output/), so nothing the agent changed in its container
# reaches the verdict.
FROM ghcr.io/mll-lab-nu/efe:ikea-mujoco-0.3.0
# Replay video (PROTOCOL §4; evidence only): MuJoCo's renderer on CPU software OpenGL (OSMesa) and ffmpeg.
# --no-deps: the physics packages (mujoco, numpy) stay the base image's, unchanged (the grader checks the runtime binding).
RUN apt-get update && apt-get install -y --no-install-recommends libosmesa6=25.0.7-2+deb13u1 && rm -rf /var/lib/apt/lists/*  && pip install --no-cache-dir --no-deps PyOpenGL==3.1.10 imageio==2.37.0 imageio-ffmpeg==0.6.0 pillow==12.3.0
ENV MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa
COPY video_view.json test.sh runtime_binding.json /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:ikea-mujoco-files-0.4.1@sha256:0762b1ed42558611d3ad634171b5ce838847013ddb17aa2011f2f397ad800a62 /privileged/environment/rcb_ikea.py /privileged/tests/grade.py /privileged/tests/render_video.py /tests/
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests
WORKDIR /tests
# resources (PROTOCOL §6) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.5.0@sha256:ecc5f24f1516ca11711d7c2d3ac07c89f79cd9220812c1244498ec71e352402a /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
