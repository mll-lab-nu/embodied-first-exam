#!/usr/bin/env bash
# Runs only in the fixed manylinux/CUDA builder. No GPU or host venv needed.
set -euo pipefail
CONFIG=/recipe/uipc-build.json
json_value() { python -c 'import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$CONFIG" "$1"; }
case "${1:?prepare, compile or audit required}" in
prepare)
SOURCE_COMMIT="$(json_value source_commit)"
VCPKG_COMMIT="$(json_value vcpkg_commit)"
mkdir -p /build/uipc /build/vcpkg /out/raw /out/wheels
git -C /build/uipc init
git -C /build/uipc remote add origin "$(json_value repository)"
git -C /build/uipc fetch --depth 1 origin "$SOURCE_COMMIT"
git -C /build/uipc checkout --detach FETCH_HEAD
test "$(git -C /build/uipc rev-parse HEAD)" = "$SOURCE_COMMIT"
git -C /build/uipc submodule update --init --recursive --depth 1
git -C /build/vcpkg init
git -C /build/vcpkg remote add origin https://github.com/microsoft/vcpkg.git
git -C /build/vcpkg fetch --depth 1 origin "$VCPKG_COMMIT"
git -C /build/vcpkg checkout --detach FETCH_HEAD
bash /build/vcpkg/bootstrap-vcpkg.sh -disableMetrics
# The old tag archive hash changed. Pin its identical source commit instead;
# retain the original port recipe and dependency version.
python - <<'PYPORT'
import json, pathlib, shutil
config = json.load(open('/recipe/uipc-build.json'))['tinygltf']
port = pathlib.Path('/build/overlays/tinygltf')
shutil.copytree('/build/vcpkg/ports/tinygltf', port)
p = port / 'portfile.cmake'
s = p.read_text()
assert s.count(config['original_sha512']) == 1
assert s.count('REF "v${VERSION}"') == 1
s = s.replace(config['original_sha512'], config['archive_sha512'])
s = s.replace('REF "v${VERSION}"', 'REF ' + config['commit'])
p.write_text(s)
PYPORT
python /recipe/verify_uipc_wheel.py prepare /build/uipc "$CONFIG"
;;
compile)
export VCPKG_OVERLAY_PORTS=/build/overlays
export CMAKE_TOOLCHAIN_FILE=/build/vcpkg/scripts/buildsystems/vcpkg.cmake
export CMAKE_BUILD_PARALLEL_LEVEL="${UIPC_BUILD_JOBS:-3}"
export VCPKG_MAX_CONCURRENCY="$CMAKE_BUILD_PARALLEL_LEVEL"
export SETUPTOOLS_SCM_PRETEND_VERSION_FOR_PYUIPC="$(json_value version)"
python -m build --wheel --no-isolation --outdir /out/raw \
  -C "cmake.define.UIPC_CUDA_ARCHITECTURES=$(json_value architectures)" \
  -C build-dir=/build/uipc-build /build/uipc
;;
audit)
# Match upstream's runtime-library policy: CUDA user libraries come from the
# selected CUDA runtime lock, the NVIDIA driver comes from the host.
for wheel in /out/raw/*.whl; do
  auditwheel repair --plat "$(json_value wheel_platform)" -w /out/wheels "$wheel" \
    --exclude 'libcuda*' --exclude 'libcudart*' --exclude 'libcublas*' \
    --exclude 'libcusparse*' --exclude 'libcusolver*' --exclude 'libcurand*' \
    --exclude 'libcufft*' --exclude 'libnvrtc*' --exclude 'libnvJitLink*'
done
python /recipe/verify_uipc_wheel.py audit /out/wheels "$CONFIG" /build/uipc

;;
*) echo "expected prepare, compile or audit" >&2; exit 2 ;;
esac
