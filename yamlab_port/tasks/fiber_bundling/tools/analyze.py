"""Summarize an oracle run (numpy only): per-phase stats + events."""
import json, sys
import numpy as np
d = sys.argv[1]
S = np.load(f"{d}/states.npz", allow_pickle=True); M = json.load(open(f"{d}/metrics.json"))
ph = S["phase"]; names = list(S["link_names"])
links = S["links"]
print("steps", len(ph), "success", M["success"], "failed", M["failed"], M.get("failure_reason"))
for p in dict.fromkeys(ph):
    m = ph == p; i = np.where(m)[0]
    print(f"{p:10s} steps {i[0]:5d}-{i[-1]:5d}  front_off max {np.nanmax(S['front_offset'][m])*1000:7.2f} mm end {S['front_offset'][i[-1]]*1000:6.2f}  "
          f"front_ahead end {S['front_ahead'][i[-1]]*1000:7.1f} mm  max_radial end {S['max_radial'][i[-1]]*1000:6.1f}  bend max {np.nanmax(S['max_bend'][m]):5.1f}  "
          f"force max {np.nanmax(S['force'][m]):.3g}")
t5 = names.index("trunk_05")
print("trunk_05 start", links[0, t5, :3], "end", links[-1, t5, :3])
for e in M["events"]:
    def fmt(v):
        if isinstance(v, dict): return {a: fmt(b) for a, b in v.items()}
        if isinstance(v, list):
            try: return np.round(np.array(v, float), 4).tolist()
            except Exception: return [fmt(x) for x in v]
        if isinstance(v, float): return round(v, 5)
        return v
    print({k: fmt(v) for k, v in e.items() if k not in ("grasp_rel",)})
print("FINAL", M["final_metrics"])
