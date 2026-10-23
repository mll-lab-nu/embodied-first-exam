"""Review platform: one page per trial (review.html) with the video, the timeline, the log by turns and the recap
cards to judge. It serves pages/K.json and the media of the work directory, and appends each judgment to
judgments.csv (the latest row per reviewer, trial and card counts). The JSON endpoints are the contract a different
platform needs to reproduce (docs/data.md). usage (from analysis/cross-bench/review/): python -m web.app [--port 8046]"""
from __future__ import annotations
import argparse, csv, json, os, re, time
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from pipeline.paths import DATA, RAW, sample

HERE = os.path.dirname(os.path.abspath(__file__))
JUDG = f"{DATA}/judgments.csv"
FIELDS = ["time", "reviewer", "key", "claim", "cat", "method", "verdict", "comment", "seconds"]
VERDICTS = {"正确", "不认同", "证据不足", ""}
LOOK = re.compile(r"^e\d+-\d+\.jpg$")

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(GZipMiddleware, minimum_size=2000)


def keys() -> list[str]:
    return [s["key"] for s in sample() if os.path.exists(f"{DATA}/pages/{s['key']}.json")]


def page(key: str) -> dict:
    if key not in keys():
        raise HTTPException(404)
    return json.load(open(f"{DATA}/pages/{key}.json"))


def file(path: str, **kw):
    if not os.path.exists(path):
        raise HTTPException(404)
    return FileResponse(path, **kw)


@app.get("/")
def index():
    return FileResponse(f"{HERE}/review.html", headers={"Cache-Control": "no-cache"})


@app.get("/kit.css")
def kit():
    return FileResponse(f"{HERE}/kit.css")


@app.get("/api/trials")
def trials():
    out = []
    for k in keys():
        p = page(k)
        out.append({"key": k, "agent": p["agent"], "task": p["task"], "success": p["success"],
                    "cards": [c["id"] for c in p["cards"] if c["section"] != "style"]})
    return out


@app.get("/api/page/{key}")
def get_page(key: str):
    return page(key)


@app.get("/api/event/{key}/{eid}")
def event(key: str, eid: str):
    page(key)
    for line in open(f"{DATA}/events/{key}.jsonl"):
        e = json.loads(line)
        if e["id"] == eid:
            return {"text": e["text"], "out": e["out"]}
    raise HTTPException(404)


@app.get("/api/search/{key}")
def search(key: str, q: str):
    """Event ids whose full text or full output matches q (regex, or plain text when q is not a valid regex)."""
    page(key)
    try:
        rx = re.compile(q, re.I)
    except re.error:
        rx = re.compile(re.escape(q), re.I)
    return [e["id"] for e in map(json.loads, open(f"{DATA}/events/{key}.jsonl")) if rx.search(e["text"]) or rx.search(e["out"])]


@app.get("/api/judgments")
def judgments(reviewer: str = ""):
    out = {}
    if os.path.exists(JUDG):
        for r in csv.DictReader(open(JUDG)):
            if r["reviewer"] == reviewer.strip():
                out.setdefault(r["key"], {})[r["claim"]] = {"verdict": r["verdict"], "comment": r["comment"]}
    return out


class Judgment(BaseModel):
    reviewer: str
    key: str
    claim: str
    verdict: str
    comment: str = ""
    seconds: float = 0


@app.post("/api/judge")
def judge(j: Judgment):
    c = next((c for c in page(j.key)["cards"] if c["id"] == j.claim), None)
    if c is None or j.verdict not in VERDICTS or not j.reviewer.strip():
        raise HTTPException(400)
    new = not os.path.exists(JUDG) or os.path.getsize(JUDG) == 0
    with open(JUDG, "a", newline="") as fh:
        w = csv.DictWriter(fh, FIELDS)
        if new:
            w.writeheader()
        w.writerow({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "reviewer": j.reviewer.strip(), "key": j.key, "claim": j.claim,
                    "cat": c["kind"], "method": c["section"], "verdict": j.verdict, "comment": j.comment.strip(), "seconds": round(j.seconds, 1)})
    return JSONResponse({"ok": True})


@app.get("/video/{key}")
def video(key: str):
    page(key)
    return file(f"{RAW}/{key}/verifier/replay.mp4", media_type="video/mp4")


@app.get("/full/{key}")
def full(key: str):
    page(key)
    return file(f"{DATA}/fullvideo/{key}.mp4", media_type="video/mp4")


@app.get("/poster/{key}/{which}")
def poster(key: str, which: str):
    page(key)
    return file(f"{DATA}/fullvideo/{key}.jpg" if which == "full" else f"{RAW}/{key}/verifier/replay.last.png")


@app.get("/look/{key}/{name}")
def look(key: str, name: str):
    page(key)
    if not LOOK.match(name):
        raise HTTPException(404)
    return file(f"{DATA}/looks/{key}/{name}", headers={"Cache-Control": "max-age=86400"})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8046)
    uvicorn.run(app, host="0.0.0.0", port=ap.parse_args().port, log_level="warning")
