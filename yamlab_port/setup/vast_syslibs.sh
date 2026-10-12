#!/bin/bash
# User-space system libs for Isaac Sim on vast (no apt install): download .debs and extract into syslibs/.
set -eux
R=/workspace/yamlab_port
mkdir -p $R/syslibs/debs && cd $R/syslibs/debs
apt-get download libhidapi-hidraw0 libhidapi-libusb0 libxt6t64 libglu1-mesa libusb-1.0-0 2>&1 | tail -3 || true
for d in *.deb; do dpkg-deb -x "$d" $R/syslibs/root; done
find $R/syslibs/root -name "*.so*" | head -20
cat > $R/env.sh <<EOS
# source me: YAMLab runtime env on vast
. $R/venv/bin/activate
export OMNI_KIT_ACCEPT_EULA=YES TERM=xterm
export LD_LIBRARY_PATH=$R/syslibs/root/usr/lib/x86_64-linux-gnu:$R/syslibs/root/lib/x86_64-linux-gnu:\${LD_LIBRARY_PATH:-}
export VK_DRIVER_FILES=/etc/vulkan/icd.d/nvidia_icd.json
EOS
echo SYSLIBS_DONE
