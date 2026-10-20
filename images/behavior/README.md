# behavior: BEHAVIOR-1K 3.9.2, fixed

`efe-private:behavior-0.1.2` (`VERSION`) = the official BEHAVIOR-1K 3.9.2 image **by digest** + ffmpeg (for replay
videos), the stack the 2026 BEHAVIOR Challenge pins. The recipe (`Dockerfile`) needs no build context; every BEHAVIOR-1K
task carries it verbatim and builds it when it cannot pull the private image (`BUILD_ONLY`).

| | |
|---|---|
| Base | `stanfordvl/behavior:3.9.2@sha256:2702900192741904e69a573aa7869ea51c592586f9791050796efc37faa893fb` (OmniGibson 3.9.2, Isaac Sim 5.1.0, cuRobo; 16 layers) |
| Our layers | 17: ffmpeg `7:6.1.1-3ubuntu5` + 146 dependencies (the package state `dpkg.lock`, checked by sha256); 18: `WORKDIR /app` (empty) |
| Published image | built 2026-10-19 with BuildKit's inline cache; layer 17 diff ID `sha256:e08e357324a963d9a1976433a672fa6e210ce2ec60df862f26c60ebfa086964e` |
| Dataset | none; mounted read-only at `/data` from `$RCB_BEHAVIOR_DATA` (BEHAVIOR Data Bundle license: no redistribution) |

## Why the digest, not the tag
Tags move. Upstream released 3.9.3 on 2026-09-23, and `stanfordvl/behavior:latest` moved to it. A registry can also re-push
`3.9.2` itself. The digest names exactly the bytes we tested.

## Why apt is pinned to a snapshot
`apt-get install ffmpeg` without a pin takes whatever the archive holds that day (a rebuild on 2026-09-26 got libapparmor1
`24.04.8`, published 2026-09-23, instead of `24.04.7`). Pinning only `ffmpeg=` would not help: its 146 dependencies still
float, and superseded update versions leave the archive index. The recipe therefore:
- reads the Ubuntu archive as it was on 2026-09-20 (`--snapshot 20260920T090000Z`, snapshot.ubuntu.com);
- fails the build unless the resulting package state (the sorted `dpkg-query` list) has the sha256 of `dpkg.lock`, the
  tested package list. The build reads no file of this repository: `dpkg.lock` is the readable copy of that list.

A rebuild then has the tested package versions. The layer bytes still differ (file times), so a local build has another
layer 17 diff ID than the published image; the packages are the same.

## Private: the tasks' build cache (`BUILD_ONLY`)
The image contains NVIDIA Isaac Sim 5.1.0 and Omniverse Kit (from the official image), whose licences forbid a public copy
(NOTICE). It is pushed to the organization's private package with BuildKit's inline cache, and every BEHAVIOR-1K task
names it in `build.cache_from`: with access, Docker pulls its layers instead of building them; without, the task builds the
same recipe from Docker Hub (the base, 14.7 GB) and snapshot.ubuntu.com. To build it by hand:
```bash
docker build --build-arg BUILDKIT_INLINE_CACHE=1 -t ghcr.io/mll-lab-nu/efe-private:behavior-$(cat images/behavior/VERSION) - < images/behavior/Dockerfile
```

To check an image against the recipe:
```bash
img=ghcr.io/mll-lab-nu/efe-private:behavior-0.1.2
base=stanfordvl/behavior@sha256:2702900192741904e69a573aa7869ea51c592586f9791050796efc37faa893fb
# 1. layers 1-16 are the official base
diff <(docker image inspect -f '{{range .RootFS.Layers}}{{println .}}{{end}}' $base | head -16) \
     <(docker image inspect -f '{{range .RootFS.Layers}}{{println .}}{{end}}' $img | head -16)
# 2. the packages are the tested ones
docker run --rm --entrypoint dpkg-query $img -W -f='${db:Status-Status} ${Package}:${Architecture} ${Version}\n' \
  | LC_ALL=C sort | diff - images/behavior/dpkg.lock
```
Both print nothing for a good image.
