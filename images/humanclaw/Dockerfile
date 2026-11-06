# humanclaw: HumanCLAW (HumanClawBench) environment -- Habitat-Sim acbe6f4 with the HumanCLAW Half-Physics patch (headless,
# CUDA, Bullet), the HumanCLAW runtime (episode loader, Half-Physics env, MotionDiT skill runner, paper metrics) from the
# HumanCLAW source snapshot fetched by commit from this repository (commit fe3d376, tree f60d71a0 of
# harnesses/humanclaw), the paper_fullval_v1 motion weights, and the 41 prepared HSSD val scenes (official hssd-hab
# meshes + the HumanCLAW val41 supplement), materialized (no symlinks). Infrastructure only: no task, no episode list, no
# recorded rollout (the source snapshot's docs/, tools/, harnesses/, experiment configs and episode shards are removed).
# Nothing is mounted or downloaded at run time; an NVIDIA GPU is needed (EGL rendering; MotionDiT on CUDA).
# BUILD_ONLY (images/humanclaw/BUILD_ONLY): HSSD is CC BY-NC 4.0, the body meshes derive from SMPL-X, the motion weights
# were trained on AMASS; the built image is never published. The HSSD supplement is a gated Hugging Face dataset: the
# build takes a Hugging Face token with access to it as the BuildKit secret `hf_token` (never stored in a layer): build
# it by hand (BUILD_ONLY), a task's compose cannot pass the secret.
FROM docker.io/nvidia/cuda:12.4.1-devel-ubuntu22.04@sha256:da6791294b0b04d7e65d87b7451d6f2390b4d36225ab0701ee7dfec5769829f5 AS humanclaw-base
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    NVIDIA_DRIVER_CAPABILITIES=compute,graphics,utility HUMANCLAW_BENCH_HOME=/opt/humanclaw
# system packages from the Ubuntu archive (TODO: pin to snapshot.ubuntu.com/ubuntu/20261001T000000Z once it serves again:
# it answered 502 for every date on 2026-10-27); the NVIDIA EGL vendor entry
RUN rm -f /etc/apt/sources.list.d/cuda*.list && \
    apt-get -o Acquire::Retries=10 update && apt-get -o Acquire::Retries=10 install -y --no-install-recommends \
      python3 python3-dev python3-venv git curl ca-certificates build-essential cmake ninja-build ffmpeg \
      libglvnd-dev libgl-dev libegl-dev libglx-dev libopengl-dev libgles-dev libglu1-mesa-dev libegl1 libgl1 libgomp1 && \
    rm -rf /var/lib/apt/lists/* && mkdir -p /usr/share/glvnd/egl_vendor.d && \
    printf '{"file_format_version":"1.0.0","ICD":{"library_path":"libEGL_nvidia.so.0"}}\n' > /usr/share/glvnd/egl_vendor.d/10_nvidia.json
# Python 3.10 venv: PyTorch 2.6.0 + CUDA 12.4 (HumanCLAW constraints/eval-cu124.txt), every other package pinned,
# their dependencies too (the constraints: every package the venv ends up with, by version)
RUN printf '%s\n' \
      attrs==24.2.0 certifi==2026.10.23 charset-normalizer==3.5.2 contourpy==1.3.2 cycler==0.12.1 \
      filelock==3.32.3 fonttools==4.65.0 fsspec==2026.7.0 gitdb==4.0.12 GitPython==3.1.43 \
      huggingface-hub==0.26.2 idna==3.20 imageio==2.36.0 imageio-ffmpeg==0.6.0 Jinja2==3.1.6 \
      kiwisolver==1.5.1 llvmlite==0.43.0 MarkupSafe==3.0.3 matplotlib==3.9.2 mpmath==1.3.0 \
      networkx==3.4.2 numba==0.60.0 numpy==1.26.4 numpy-quaternion==2023.0.4 nvidia-cublas-cu12==12.4.5.8 \
      nvidia-cuda-cupti-cu12==12.4.127 nvidia-cuda-nvrtc-cu12==12.4.127 nvidia-cuda-runtime-cu12==12.4.127 nvidia-cudnn-cu12==9.1.0.70 nvidia-cufft-cu12==11.2.1.3 \
      nvidia-curand-cu12==10.3.5.147 nvidia-cusolver-cu12==11.6.1.9 nvidia-cusparse-cu12==12.3.1.170 nvidia-cusparselt-cu12==0.6.2 nvidia-nccl-cu12==2.21.5 \
      nvidia-nvjitlink-cu12==12.4.127 nvidia-nvtx-cu12==12.4.127 packaging==26.3 pillow==10.4.0 pyparsing==3.3.3 \
      python-dateutil==3.0.0 python-dotenv==1.0.1 PyYAML==6.0.3 requests==2.34.2 scipy==1.15.3 \
      six==1.17.0 smmap==5.0.3 sympy==1.13.1 tqdm==4.66.5 triton==3.2.0 \
      typing_extensions==4.16.0 tzdata==2026.5 urllib3==2.8.0 \
      > /tmp/pins.txt && \
    python3 -m venv /opt/venv && /opt/venv/bin/pip install pip==24.2 setuptools==75.1.0 wheel==0.44.0 && \
    /opt/venv/bin/pip install -c /tmp/pins.txt torch==2.6.0 --index-url https://download.pytorch.org/whl/cu124 && \
    /opt/venv/bin/pip install -c /tmp/pins.txt numpy==1.26.4 scipy==1.15.3 Pillow==10.4.0 imageio-ffmpeg==0.6.0 python-dotenv==1.0.1 \
      huggingface-hub==0.26.2 attrs==24.2.0 GitPython==3.1.43 imageio==2.36.0 matplotlib==3.9.2 numba==0.60.0 \
      numpy-quaternion==2023.0.4 tqdm==4.66.5
ENV PATH="/opt/venv/bin:${PATH}" VIRTUAL_ENV=/opt/venv
# Network helpers: every git source is fetched at its exact commit (depth 1), retried with backoff, and from a mirror
# where one exists (Eigen: GitLab, which sheds load at times, then its GitHub mirror; a commit hash pins the content)
RUN cat > /usr/local/bin/hc-retry <<'SH' && cat > /usr/local/bin/hc-git-at <<'SH2' && \
    cat > /usr/local/bin/hc-git-submodules <<'SH3' && chmod +x /usr/local/bin/hc-retry /usr/local/bin/hc-git-at /usr/local/bin/hc-git-submodules
#!/bin/bash
# hc-retry CMD...: run CMD up to 6 times, waiting 10, 20, ... s between tries
for i in 1 2 3 4 5 6; do "$@" && exit 0; echo "hc-retry: attempt $i failed: $*" >&2; sleep $((i * 10)); done
exit 1
SH
#!/bin/bash
# hc-git-at DIR SHA URL [URL...]: DIR becomes a checkout of commit SHA (depth 1), fetched from the first URL that has it
set -u
d=$1 sha=$2; shift 2
mkdir -p "$d" && git -C "$d" init -q
for i in 1 2 3 4 5 6; do
  for u in "$@"; do
    if git -C "$d" fetch -q --depth 1 "$u" "$sha"; then git -C "$d" checkout -q FETCH_HEAD && exit 0; fi
  done
  echo "hc-git-at: attempt $i failed: $sha from $*" >&2; sleep $((i * 10))
done
exit 1
SH2
#!/bin/bash
# hc-git-submodules REPO: every submodule of REPO, recursively, at the commit REPO records for it (then a
# `git submodule update --init --recursive` finds them all in place and fetches nothing)
set -eu
r=$1
[ -f "$r/.gitmodules" ] || exit 0
git -C "$r" config -f .gitmodules --get-regexp '^submodule\..*\.path$' | while read -r key path; do
  name=${key#submodule.}; name=${name%.path}
  url=$(git -C "$r" config -f .gitmodules --get "submodule.$name.url")
  sha=$(git -C "$r" ls-tree HEAD "$path" | awk '{print $3}')
  [ -n "$sha" ] || continue
  alt=""
  case "$url" in *gitlab.com/libeigen/eigen*) alt=https://github.com/eigen-mirror/eigen.git ;; esac
  hc-git-at "$r/$path" "$sha" "$url" $alt
  hc-git-submodules "$r/$path"
done
SH3
# the HumanCLAW source snapshot (by commit; its tree hash checked), without what the runtime does not need
RUN git init -q /tmp/hc && cd /tmp/hc && git remote add origin https://github.com/mll-lab-nu/embodied-first-exam && \
    hc-retry git fetch -q --depth 1 --filter=blob:none origin fe3d37676264cba2f71569aa8822428e9c73e1ca && \
    test "$(git rev-parse FETCH_HEAD:harnesses/humanclaw)" = f60d71a04c79411089fc5e606322b96f61cad8dd && \
    git sparse-checkout set --no-cone /harnesses/humanclaw/pyproject.toml /harnesses/humanclaw/LICENSE \
      /harnesses/humanclaw/NOTICE /harnesses/humanclaw/src/ /harnesses/humanclaw/resources/agent/ \
      /harnesses/humanclaw/resources/hssd/ /harnesses/humanclaw/resources/metrics/ /harnesses/humanclaw/resources/seeds/ \
      /harnesses/humanclaw/resources/weights/ /harnesses/humanclaw/resources/assets.json \
      /harnesses/humanclaw/configs/paper_fullval_v1.json /harnesses/humanclaw/patches/habitat-sim/ && \
    hc-retry git checkout -q FETCH_HEAD && mv harnesses/humanclaw /opt/humanclaw && cd / && rm -rf /tmp/hc && \
    rm -rf /opt/humanclaw/src/humanclaw_bench/harnesses /opt/humanclaw/src/humanclaw_bench/libero && \
    echo "6f57ec8130b4ccca7d208a0754ba691d52e44b469cd6dcee220fa193fcad6766  /opt/humanclaw/patches/habitat-sim/humanclaw_halfphysics.patch" | sha256sum -c -
# Habitat-Sim acbe6f4 + the Half-Physics patch: headless, CUDA, Bullet (HumanCLAW patches/habitat-sim/README.md)
RUN hc-git-at /opt/habitat-sim acbe6f4922e68145e401e55c30f9dfea460a3f24 https://github.com/facebookresearch/habitat-sim.git && \
    cd /opt/habitat-sim && hc-git-submodules . && git submodule update -q --init --recursive && \
    test "$(git -C src/deps/bullet3 rev-parse HEAD)" = 2c204c49e56ed15ec5fcfa71d199ab6d6570b3f5 && \
    git apply --check /opt/humanclaw/patches/habitat-sim/humanclaw_halfphysics.patch && \
    git apply /opt/humanclaw/patches/habitat-sim/humanclaw_halfphysics.patch && \
    CMAKE_BUILD_PARALLEL_LEVEL=${HC_BUILD_JOBS:-16} python setup.py build_ext --inplace --headless --with-cuda --bullet \
      --cmake-args="-DCMAKE_CUDA_ARCHITECTURES=80;86;89;90 -DCCACHE_FOUND:FILEPATH=" && \
    HEADLESS=True WITH_CUDA=True WITH_BULLET=True pip install --no-deps --no-build-isolation -e . && \
    pip install --no-deps build/deps/magnum-bindings/src/python && \
    find build -name '*.o' -delete && find . -name .git -prune -exec rm -rf {} + && \
    python -c "import habitat_sim; assert habitat_sim.built_with_bullet; print(habitat_sim.__file__)"
RUN pip install --no-deps -e /opt/humanclaw
# the paper_fullval_v1 motion weights (HumanCLAW/HumanCLAW, public), checked by archive sha256 and by the manifest
RUN curl -fsSL --retry 5 -o /tmp/w.tgz https://huggingface.co/HumanCLAW/HumanCLAW/resolve/77ac3dfbb0d379376695c957189ef2de336f4941/HumanCLAW_pretrained_weights_paper_fullval_v1_20260816.tar.gz && \
    echo "3b3c0c1b232af4c462301655de909a4bc54fd4756bcd42c22e7965fccb650667  /tmp/w.tgz" | sha256sum -c - && \
    mkdir -p /tmp/w && tar -xzf /tmp/w.tgz -C /tmp/w && mkdir -p /opt/humanclaw/weights && \
    mv /tmp/w/HumanCLAW/weights/paper_fullval_v1 /opt/humanclaw/weights/ && \
    cmp /tmp/w/HumanCLAW/resources/weights/paper_fullval_v1.json /opt/humanclaw/resources/weights/paper_fullval_v1.json && \
    rm -rf /tmp/w /tmp/w.tgz
# HSSD: the official hssd-hab files the 41 scenes use (by name and sha256 from the snapshot's asset_requirements.json) and
# the gated HumanCLAW val41 supplement, combined by HumanCLAW's own prepare-hssd, then materialized (no symlinks)
RUN --mount=type=secret,id=hf_token --mount=type=cache,id=humanclaw-hssd,target=/cache python - <<'PY'
import hashlib, json, os, shutil, subprocess, time
import concurrent.futures as cf   # (no `from` imports: a Dockerfile linter reads a line starting with FROM as a stage)
import huggingface_hub as hh
if not os.path.exists("/run/secrets/hf_token"):   # optional, so a build that finds this layer cached needs none
    raise SystemExit("this layer needs the build secret hf_token (images/humanclaw/BUILD_ONLY)")
tok = open("/run/secrets/hf_token").read().strip()
H = "/opt/humanclaw/resources/hssd/humanclaw-hssd-val41"
req = json.load(open(f"{H}/asset_requirements.json"))["assets"]
sup = json.load(open(f"{H}/supplement.json"))
REV, ROOT = "4369cb9876214c7fbebcf552eb532380e4d287e4", "/cache/hssd-hab"   # a build cache, never a layer
# where each file lives in hssd-hab (objects/<c>/, objects/decomposed/<id>/, ...), by name: the tree at REV
where = {}
for f in hh.HfApi().list_repo_tree("hssd/hssd-hab", repo_type="dataset", revision=REV, recursive=True, token=tok):
    if hasattr(f, "size"):
        where.setdefault(f.path.rsplit("/", 1)[-1], []).append(f.path)
def path_of(group, name):   # a name may carry its own subdirectory (semantics: scenes/<id>.semantic_config.json)
    hits = [p for p in where.get(name.rsplit("/", 1)[-1], []) if p.startswith(group + "/") and p.endswith("/" + name)]
    assert len(hits) == 1, (group, name, hits)
    return hits[0]
want = [(path_of(g, n), s) for g in ("objects", "stages", "semantics") for n, s in req[g].items() if n not in sup["files"]]
want.append(("hssd-hab.scene_dataset_config.json", None))
def get(item):
    rel, spec = item
    p = os.path.join(ROOT, rel)
    for attempt in range(8):   # the Hub answers a burst of 10k requests with an occasional error: retry, then fail
        if spec and os.path.isfile(p) and os.path.getsize(p) == spec["size_bytes"]:
            break
        try:
            p = hh.hf_hub_download("hssd/hssd-hab", rel, repo_type="dataset", revision=REV, local_dir=ROOT, token=tok)
            break
        except Exception:
            if attempt == 7:
                raise
            time.sleep(2 ** attempt)
    if spec:
        h = hashlib.sha256(open(p, "rb").read()).hexdigest()
        assert os.path.getsize(p) == spec["size_bytes"] and h == spec["sha256"], rel
with cf.ThreadPoolExecutor(8) as ex:
    list(ex.map(get, want))
a = hh.hf_hub_download(sup["hf"]["repo_id"], sup["hf"]["filename"], repo_type=sup["hf"]["repo_type"],
                    revision="efced861179660780449be19fcfff10141d8409b", local_dir="/cache/supp", token=tok)
import humanclaw_bench.hssd as hs
print(json.dumps(hs.prepare_hssd(ROOT, "/tmp/prep", supplement=a, workers=16)))
os.makedirs("/opt/humanclaw/data", exist_ok=True)
subprocess.run(["cp", "-rL", "/tmp/prep", "/opt/humanclaw/data/humanclaw-hssd-val41"], check=True)
for d in ("/tmp/prep", "/root/.cache"):
    shutil.rmtree(d, ignore_errors=True)
links = subprocess.run(["find", "/opt/humanclaw/data", "-type", "l"], capture_output=True, text=True, check=True).stdout
assert not links.strip(), links[:500]
print(len(want), "official files + the supplement: /opt/humanclaw/data/humanclaw-hssd-val41")
PY
WORKDIR /app
