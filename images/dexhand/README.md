# DexHand simulator image

`ghcr.io/mll-lab-nu/efe:dexhand-<VERSION>` (tag from `VERSION`): Python 3.12 slim with MuJoCo 3.4.0, numpy, scipy,
imageio (ffmpeg), Pillow and PyOpenGL (`requirements.txt`, exact pins), OSMesa and EGL libraries for CPU rendering,
and three pinned asset sets, each checked file by file (sha256 and size) against its manifest:

| Path in the image | Assets | License | Manifest |
|---|---|---|---|
| `/opt/dexhand/hand` (`DEXHAND_ASSET_DIR`) | Sharpa Wave hand (MJCF, meshes, license), [MuJoCo Menagerie](https://github.com/google-deepmind/mujoco_menagerie/tree/0059d4335f8156206f63a35662313385f7ad6d74/sharpa_wave) `0059d4335f8156206f63a35662313385f7ad6d74` | Apache-2.0 | `asset-manifest.json` |
| `/opt/dexhand/wuji_v2_2` (`WUJI_ASSET_DIR`) | Wuji Hand 2.2 (`hand2/hand2_2`) physics subset: MJCF, meshes, license, changelog; [wuji-description](https://github.com/wuji-technology/wuji-description/tree/829c9aa27cb12c3a49d5b8d63c9869dd8f656702) `829c9aa27cb12c3a49d5b8d63c9869dd8f656702` | MIT | `wuji-asset-manifest.json` (installed as `manifest.json`) |
| `/opt/dexhand/tianji` (`TIANJI_ASSET_DIR`, `DEXHAND_TIANJI_DIR`) | Tianji Marvin dual-arm meshes (DexForce `embodichain_data` `TianjiMarvin.zip`; inertias from Genesis `dual_arms_primitives.urdf`), converted by `tianji/tianji_model.py` | Apache-2.0 / MIT (`tianji/NOTICE.md`, `tianji/PROVENANCE.json`) | `tianji-asset-manifest.json` |

There is no task code, policy, demonstration or reference trajectory in the image: every task directory carries its
own runtime copy (`/opt/tools` in privileged mode, `/srv` in the standard `sim` service), and nothing is downloaded at
run time.

```bash
# prepare_assets.py runs on the host; the Tianji conversion needs these exact versions (tianji/source-manifest.json):
python3 -m pip install -r images/dexhand/requirements-assets.txt   # trimesh==4.11.2 mujoco==3.4.0 numpy==2.3.5 scipy==1.16.3
python3 images/dexhand/prepare_assets.py      # fetch the pinned sources into the git-ignored assets/ and verify them
sudo docker build -t ghcr.io/mll-lab-nu/efe:dexhand-$(cat images/dexhand/VERSION) images/dexhand
```

The published image is `ghcr.io/mll-lab-nu/efe:dexhand-0.2.0`. After a `docker push` of a new version, write its digest
(`sha256:...`) to `DIGEST`; every task's `FROM` and standard `sim.image` are pinned to it.

`prepare_assets.py` reuses files that already match their manifest and rebuilds the Tianji meshes from the pinned
public archives (`tianji/source-manifest.json`) when no verified copy exists; the conversion must reproduce
`tianji-asset-manifest.json` byte for byte. Local simulator runs outside the image set `DEXHAND_ASSET_DIR`,
`WUJI_ASSET_DIR` and `TIANJI_ASSET_DIR` to the prepared `images/dexhand/assets/{hand,wuji_v2_2,tianji}` and
`MUJOCO_GL=egl` (or `osmesa`). Benchmark notes: [docs/benchmarks/dexhand.md](../../docs/benchmarks/dexhand.md).
