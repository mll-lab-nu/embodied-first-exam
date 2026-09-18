#!/usr/bin/env bash
# tests/instance.npz is the task identity: its sha256 must match task.toml and environment/instance.npz.
t="$1"; rc=0
want=$(python3 -c "import tomllib,sys; print(tomllib.load(open(sys.argv[1],'rb'))['metadata']['instance_sha256'])" "$t/task.toml")
have=$(sha256sum "$t/tests/instance.npz" | cut -d' ' -f1)
env_=$(sha256sum "$t/environment/instance.npz" | cut -d' ' -f1)
[ "$want" = "$have" ] || { echo "FAIL $t: instance_sha256 in task.toml ($want) != tests/instance.npz ($have)"; rc=1; }
[ "$have" = "$env_" ] || { echo "FAIL $t: environment/instance.npz differs from tests/instance.npz"; rc=1; }
exit $rc
