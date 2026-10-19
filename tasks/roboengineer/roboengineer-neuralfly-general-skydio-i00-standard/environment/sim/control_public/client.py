"""Agent-side policy client. Preserve the exact service bytes plus concise revision diagnoses."""

import base64, json, hashlib, os, urllib.request, urllib.error
from pathlib import Path


class Client:
    def __init__(self, url="http://127.0.0.1:8000", out="/app/output/trace", timeout_s=None):
        self.url = url
        self.timeout_s = float(
            timeout_s if timeout_s is not None else os.environ.get("CONTROL_DEPLOY_TIMEOUT_S", "1800")
        )
        if not 0 < self.timeout_s <= 129600:
            raise ValueError("Client request timeout")
        self.out = Path(out)
        self.out.mkdir(parents=True, exist_ok=True)

    def call(self, operation, arguments):
        request = json.dumps(arguments, allow_nan=False).encode()
        req = urllib.request.Request(
            self.url + "/" + operation, data=request, headers={"Content-Type": "application/json"}
        )
        # Allocate by requests so failed calls also retain distinct trace entries.
        indices = [
            int(p.name.split("-", 1)[0]) for p in self.out.glob("*.request.json") if p.name.split("-", 1)[0].isdigit()
        ]
        index = max(indices, default=-1) + 1
        prefix = self.out / f"{index:03d}-{operation}"
        prefix.with_suffix(".request.json").write_bytes(request)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as response:
                raw = response.read()
        except urllib.error.HTTPError as error:
            raw = error.read()
            prefix.with_suffix(".response.json").write_bytes(raw)
            prefix.with_suffix(".error.json").write_text(json.dumps({"http_status": error.code}))
            raise
        except urllib.error.URLError as error:
            prefix.with_suffix(".error.json").write_text(json.dumps({"transport_error": str(error.reason)}))
            raise
        prefix.with_suffix(".response.json").write_bytes(raw)
        result = json.loads(raw)
        # describe.feedback is documentation; only deploy returns episode payloads.
        episodes = result.get("feedback", []) if operation in ("deploy", "result") else []
        if not isinstance(episodes, list):
            raise ValueError("Invalid deployment feedback")
        for i, episode in enumerate(episodes):
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

    def result(self, round_id):
        """The stored response of a completed deployment round (when a deploy response was lost); runs nothing."""
        return self.call("result", {"round_id": round_id})


def artifact(path):
    return {"npz_base64": base64.b64encode(Path(path).read_bytes()).decode()}
