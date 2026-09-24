#!/bin/bash
# Oracle agent: also probes what an agent can and cannot reach, and records it to /app/output/probe.txt
mkdir -p /app/output
{ python -c 'import client;print("sim base:", client.BASE)'; echo "--- can I see the sim's files?"; ls /srv /data 2>&1; echo "--- processes visible:"; ps aux 2>/dev/null | wc -l; cat /proc/1/cmdline | tr '\0' ' '; echo; echo "--- hidden endpoint:"; python -c "import client,requests;print(requests.get(client.BASE+'/state').status_code)"; echo "--- 3rd reset:"; } > /app/output/probe.txt 2>&1
python - <<'PY' >> /app/output/probe.txt 2>&1
import client
obs = client.reset(); print(obs)
pos = 0
for a in [3, 3, 3, -2]:          # overshoot then correct: 3+3+3=9 -> left -> -2 = 7
    obs, done = client.step(a); print(obs, done)
    if done: break
print("second reset:", client.reset())
for a in [7]:
    print(client.step(a))
try: client.reset()
except Exception as e: print("third reset ->", e)
PY
