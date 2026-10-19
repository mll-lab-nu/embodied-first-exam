# eai-roboarc-files: RoboARC's privileged tooling, rcb_topogym.py with render_bridge.py and nyx_direct.py
# (embodied_first_exam/benchmarks/roboarc/, the one source), the only copy the privileged tasks' agent and verifier images use: their
# environment/Dockerfile and tests/Dockerfile take them with COPY --from=<this image@digest> (scripts/files_image.py;
# FILES.json pins it). Files only, nothing runs from it. Public, like ghcr.io/mll-lab-nu/efe:roboarc-<version>. Build with
# `python3 scripts/files_image.py build roboarc-files` (stages context/: the files with their checkout modes and
# content-derived mtimes), push, then `pin` the pushed digest.
FROM scratch
COPY . /
