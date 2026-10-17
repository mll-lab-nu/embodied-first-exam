"""Stand-in for rcb_ambench.py in test_standard_grading.py: count_gpu_faults (the real pattern's first alternative), and
the CLI's `film` (STUB_FILM: ok | fail | crash | sleep). Any other command records itself (no case may replay)."""
import json, os, re, sys, time
def count_gpu_faults(text: str) -> int:
    return len(re.findall(r"PhysX error: GPU \S+ fail to launch|CUDA error", text))
if __name__ == "__main__":
    a = sys.argv[1:]; d = os.environ["RCB_DATA"]
    if a[0] != "film":
        open(os.path.join(d, "tool_called"), "w").write(" ".join(a)); sys.exit(0)
    what = os.environ.get("STUB_FILM", "ok"); video = a[a.index("--video") + 1]
    if what == "ok":
        open(video, "w").write("mp4"); print(json.dumps({"film": {"success": True, "state_sha": "aa"}, "video": video}))
    elif what == "fail":
        sys.exit(3)
    elif what == "crash":
        os._exit(139)
    elif what == "sleep":
        time.sleep(600)
