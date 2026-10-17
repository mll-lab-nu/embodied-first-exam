"""Stand-in for `live_video.py encode <data>` in the finalize.sh test. STUB_VIDEO: ok | fail | crash | sleep."""
import json, os, sys, time
d = sys.argv[2]; what = os.environ.get("STUB_VIDEO", "ok")
open(os.path.join(d, "stub_video_calls"), "a").write("x")
if what == "ok":
    open(os.path.join(d, "live.mp4"), "w").write("mp4")
    print(json.dumps({"video": os.path.join(d, "live.mp4"), "frames": 7, "slots": 7, "every": 3, "error": None}))
elif what == "fail":
    print(json.dumps({"video": None, "frames": 0, "error": "no frame was taken"})); sys.exit(1)
elif what == "crash":
    os._exit(139)
elif what == "sleep":
    time.sleep(600)
