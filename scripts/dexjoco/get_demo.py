"""Download only replay.zarr of the first N demos of a DexJoCo task from the public HF raw dataset."""
import json, os, sys, urllib.request
task, n, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
API = "https://huggingface.co/api/datasets/DexJoCo/DexJoCo-Datasets-Raw/tree/main/"
RAW = "https://huggingface.co/datasets/DexJoCo/DexJoCo-Datasets-Raw/resolve/main/"
demos = sorted(x["path"] for x in json.load(urllib.request.urlopen(API + f"dexjoco_raw_datasets/{task}")) if x["type"] == "directory")
for d in demos[:n]:
    files = json.load(urllib.request.urlopen(API + d + "?recursive=true"))
    for f in files:
        if f["type"] == "file" and "/replay.zarr/" in f["path"]:
            dst = os.path.join(out, task, f["path"].split(f"{task}/", 1)[1])
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            urllib.request.urlretrieve(RAW + f["path"], dst)
    print("got", d.rsplit("/", 1)[1])
