# syntax=docker/dockerfile:1.7
# The BlenderKit models RoboWits' 30 seed tasks load (assets/metadata.json; 26 of our RoboWits families need some),
# downloaded with the builder's own BlenderKit API key and converted / re-centred with Blender 5.1 exactly as RoboWits'
# assets/setup_assets.sh does, plus two fixes below. The models are licensed to whoever downloads them and must not be
# redistributed as files (images/robowits/NOTICE): this build exports them to a host folder, never into an image.
# Run: images/robowits/fetch_blenderkit.sh <dir> (the key is a BuildKit secret: never in a layer, the history or the log).
ARG BASE=ghcr.io/mll-lab-nu/efe:robowits-0.1.1
FROM ${BASE} AS base

FROM base AS blenderkit
RUN apt-get update && apt-get install -y --no-install-recommends xz-utils libxi6 libxxf86vm1 libxfixes3 libxkbcommon0 \
      libsm6 libice6 libxrender1 libxext6 libx11-6 libgl1 && rm -rf /var/lib/apt/lists/*
RUN curl -Ls https://download.blender.org/release/Blender5.1/blender-5.1.2-linux-x64.tar.xz | tar -xJ -C /opt && \
    ln -s /opt/blender-5.1.2-linux-x64/blender /usr/local/bin/blender && blender --version | head -1
WORKDIR /opt/robowits
# MIN_MODELS: sanity floor for the download pass (67 = the free models); completeness is checked at the end of this stage
# against assets/metadata.json. PASS: change it to re-run the download (its cache key is the command text, not the secret).
ARG MIN_MODELS=67
ARG PASS=1
# three passes (the script skips what is already there): a transient network error must not fail the whole build
RUN --mount=type=secret,id=blenderkit_api_key,required=true \
    for i in 1 2 3; do python assets/download_blenderkit_asset.py --api-key "$(cat /run/secrets/blenderkit_api_key)" \
        --assets-dir /opt/robowits/assets >/tmp/download.out 2>&1 && break; sleep 10; done; \
    grep -E "Done:|Skipped|Failed" /opt/robowits/assets/download_assets.log | tail -3; \
    find /opt/robowits/assets/blender_kit -name '*.blend*' -delete; \
    n=$(ls /opt/robowits/assets/blender_kit/*/obj.glb | wc -l); echo "BlenderKit models: $n (pass $PASS)"; test "$n" -ge "$MIN_MODELS"
COPY blender_tools.py big_textures.py /opt/rcb_build/
# 04 pinch_card's "bank card" (9b4245ca..., scale 0.8) is no longer on BlenderKit: the "Apple Card" model (997ebb58..., a real
# 86 x 54 x 0.7 mm card) scaled by 1/0.8, so the task's own scale gives a real card again
RUN --mount=type=secret,id=blenderkit_api_key,required=true \
    python -c "import sys, logging; sys.path.insert(0, 'assets'); import download_blenderkit_asset as d; \
lg = d.setup_logger('/tmp/card.log'); ok = d.process_asset('997ebb58-8ada-4a83-b8a0-b82ef0dc036b', open('/run/secrets/blenderkit_api_key').read().strip(), '/opt/robowits/assets', lg); print('apple card:', ok)" \
      >/tmp/card.out 2>&1; grep -E "apple card|Done" /tmp/card.out | tail -2; \
    src=/opt/robowits/assets/blender_kit/997ebb58-8ada-4a83-b8a0-b82ef0dc036b/obj.glb; dst=/opt/robowits/assets/blender_kit/9b4245ca-361f-4940-a23d-090b1e547a52; \
    if [ -f "$src" ] && [ ! -f "$dst/obj.glb" ]; then mkdir -p "$dst" && blender --background --python /opt/rcb_build/blender_tools.py -- scale 1.25 "$src" "$dst/obj.glb" 2>&1 | grep "scale:"; fi; \
    rm -rf "$(dirname "$src")"
# two models embed a 16667 x 16668 PNG, which PIL refuses to decode (the scene build crashes): only those two images are
# downscaled (to 8192 px), inside the GLB; geometry and every other texture stay byte-identical
RUN big=$(python /opt/rcb_build/big_textures.py list /opt/robowits/assets/blender_kit); \
    [ -z "$big" ] || python /opt/rcb_build/big_textures.py fix 8192 $big; \
    test -z "$(python /opt/rcb_build/big_textures.py list /opt/robowits/assets/blender_kit)"
# every model RoboWits' tasks load (assets/metadata.json: free + full_plan) must be here
RUN python -c "import json, os; m = json.load(open('assets/metadata.json')); ids = m['free'] + m['full_plan']; \
missing = [i for i in ids if not os.path.isfile(f'assets/blender_kit/{i}/obj.glb')]; \
print(len(ids) - len(missing), 'of', len(ids), 'models present; missing:', missing); raise SystemExit(1 if missing else 0)"

# only the model folder leaves the build: `--output type=local,dest=<dir>` writes <dir>/<uuid>/obj.glb
FROM scratch AS export
COPY --from=blenderkit /opt/robowits/assets/blender_kit /
