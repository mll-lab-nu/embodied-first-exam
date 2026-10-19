# behavior: BEHAVIOR-1K 3.9.2, fixed

`efe-private:behavior-0.1.1` (`VERSION`; named `rcb-behavior:0.1.1` before protocol v1.0, same Dockerfile) = the official
BEHAVIOR-1K 3.9.2 image **by digest** + ffmpeg (for replay videos). Every BEHAVIOR result in this repo ran on this
version, which is the one the 2026 BEHAVIOR Challenge pins.

| | |
|---|---|
| Base | `stanfordvl/behavior:3.9.2@sha256:2702900192741904e69a573aa7869ea51c592586f9791050796efc37faa893fb` (OmniGibson 3.9.2, Isaac Sim 5.1.0, cuRobo; 16 layers) |
| Our layers | 17: ffmpeg `7:6.1.1-3ubuntu5` + 146 dependencies (`dpkg.lock`); 18: `WORKDIR /app` (empty) |
| Tested image | built 2026-09-20; layer 17 diff ID `sha256:c062e78294a5a767f0a9857b35996d2e0c2fdae23a3244a063eaee39601c55c3` |
| Dataset | none; mounted read-only at `/data` from `$RCB_BEHAVIOR_DATA` (BEHAVIOR Data Bundle license: no redistribution) |

## Why the digest, not the tag
Tags move. Upstream released 3.9.3 on 2026-09-23, and `stanfordvl/behavior:latest` moved to it. A registry can also re-push
`3.9.2` itself. The digest names exactly the bytes we tested.

## Why apt is pinned to a snapshot
`apt-get install ffmpeg` without a pin takes whatever the archive holds that day. A rebuild on 2026-09-26 differed from the
tested image in the ffmpeg layer (libapparmor1 `24.04.8` instead of `24.04.7`, published 2026-09-23). Pinning only
`ffmpeg=` would not help: its 146 dependencies still float, and superseded update versions leave the archive index.
The Dockerfile therefore:
- reads the Ubuntu archive as it was on 2026-09-20 (`--snapshot 20260920T090000Z`, snapshot.ubuntu.com);
- fails the build unless the resulting package state equals `dpkg.lock`, the tested image's full `dpkg-query` list.

A rebuild then has the tested package versions. The layer bytes still differ (file times), so only the image built on
2026-09-20 has the layer 17 diff ID above.

## Not published: build it (`BUILD_ONLY`)
behavior is never pushed to a registry (user decision 2026-09-28; PROTOCOL §2.4):
- it contains NVIDIA Isaac Sim 5.1.0 and Omniverse Kit (from the official image), whose licences forbid redistribution
  (NOTICE);
- its base has a 13.7 GB layer, above ghcr.io's 10 GB per-layer limit.

Each host builds it from the repository root (`BUILD_ONLY` has the command, the licences and the data it needs): the build
pulls the public base from StanfordVL (14.7 GB), runs the pinned apt step and is tagged
`ghcr.io/mll-lab-nu/efe-private:behavior-0.1.1`, the name the tasks use:
```bash
docker build -t ghcr.io/mll-lab-nu/efe-private:behavior-$(cat images/behavior/VERSION) -f images/behavior/Dockerfile .
```
A host that built it as `rcb-behavior:0.1.1` may `docker tag` that image instead (the same build).

To check a build against the tested image:
```bash
img=ghcr.io/mll-lab-nu/efe-private:behavior-0.1.1
base=stanfordvl/behavior@sha256:2702900192741904e69a573aa7869ea51c592586f9791050796efc37faa893fb
# 1. layers 1-16 are the official base
diff <(docker image inspect -f '{{range .RootFS.Layers}}{{println .}}{{end}}' $base | head -16) \
     <(docker image inspect -f '{{range .RootFS.Layers}}{{println .}}{{end}}' $img | head -16)
# 2. the packages are the tested ones
docker run --rm --entrypoint dpkg-query $img -W -f='${db:Status-Status} ${Package}:${Architecture} ${Version}\n' \
  | LC_ALL=C sort | diff - images/behavior/dpkg.lock
```
Both print nothing for a good image.
