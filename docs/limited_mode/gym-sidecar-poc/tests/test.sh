#!/bin/bash
mkdir -p /logs/verifier
echo "artifacts present in verifier sandbox:"; ls -la /data 2>/dev/null; find / -name final.json -not -path "*/proc/*" 2>/dev/null
python - <<'PY'
import json, os
p = "/data/final.json"
if not os.path.exists(p):
    open("/logs/verifier/reward.txt","w").write("0\n"); json.dump({"success":0,"missing_log":1}, open("/logs/verifier/reward.json","w")); raise SystemExit
d = json.load(open(p)); ok = d["success"] and d["resets"] <= 2
open("/logs/verifier/reward.txt","w").write("1\n" if ok else "0\n")
json.dump({"success": int(ok), "resets": d["resets"], "denied_resets": d["denied"], "n_events": d["n_events"]}, open("/logs/verifier/reward.json","w"))
print(d)
PY
