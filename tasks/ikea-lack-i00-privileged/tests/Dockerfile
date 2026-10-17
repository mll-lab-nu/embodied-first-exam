# Separate verifier sandbox (PROTOCOL §4): the same image with the verifier's own copies of the tooling and the scene's
# binding. Harbor uploads only the declared artifacts (/app/output/), so nothing the agent changed in its container
# reaches the verdict.
FROM ghcr.io/mll-lab-nu/eai-ikea-mujoco:0.3.0
# Replay video (PROTOCOL §4, board 0136; evidence only): MuJoCo's renderer on CPU software OpenGL (OSMesa) and ffmpeg.
# --no-deps: the physics packages (mujoco, numpy) stay the base image's, unchanged (the grader checks the runtime binding).
RUN apt-get update && apt-get install -y --no-install-recommends libosmesa6=25.0.7-2+deb13u1 && rm -rf /var/lib/apt/lists/*  && pip install --no-cache-dir --no-deps PyOpenGL==3.1.10 imageio==2.37.0 imageio-ffmpeg==0.6.0 pillow==12.3.0
ENV MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa
COPY grade.py rcb_ikea.py render_video.py video_view.json test.sh runtime_binding.json /tests/
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests
WORKDIR /tests
# resource limits: the verifier step and its copy of the limits (docs/PROTOCOL.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
