"""Agent-side policy client. Preserve the exact service bytes plus concise revision diagnoses."""

import base64, json, hashlib, urllib.request
from pathlib import Path


class Client:
    def __init__(self, url="http://127.0.0.1:8000", out="/app/output/trace"):
        self.url = url
        self.out = Path(out)
        self.out.mkdir(parents=True, exist_ok=True)

    def call(self, operation, arguments):
        request = json.dumps(arguments, allow_nan=False).encode()
        req = urllib.request.Request(
            self.url + "/" + operation, data=request, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=1800) as response:
            raw = response.read()
        index = len(list(self.out.glob("*.response.json")))
        prefix = self.out / f"{index:03d}-{operation}"
        prefix.with_suffix(".request.json").write_bytes(request)
        prefix.with_suffix(".response.json").write_bytes(raw)
        result = json.loads(raw)
        for i, episode in enumerate(result.get("feedback", [])):
            for j, frame in enumerate(episode["images"]):
                b = base64.b64decode(frame["base64"], validate=True)
                if hashlib.sha256(b).hexdigest() != frame["sha256"]:
                    raise ValueError("Frame checksum")
                (self.out / f"{index:03d}-case-{i}-frame-{j}.jpg").write_bytes(b)
        return result

    def describe(self):
        return self.call("describe", {})

    def deploy(self, policy, diagnosis):
        return self.call("deploy", {"policy": policy, "diagnosis": diagnosis})

    def seal(self, round_id, summary):
        return self.call("seal", {"round_id": round_id, "summary": summary})


def artifact(path):
    return {"npz_base64": base64.b64encode(Path(path).read_bytes()).decode()}
