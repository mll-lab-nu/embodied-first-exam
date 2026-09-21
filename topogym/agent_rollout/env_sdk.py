"""Standalone stdlib SDK. Published in each trial as topogym_env.py."""
import argparse
import json
import os
import uuid
from urllib.error import HTTPError
from urllib.request import Request, ProxyHandler, build_opener


class EnvironmentError(RuntimeError):
    pass


class Environment:
    def __init__(self, endpoint=None, token=None, timeout_s=3600):
        self.endpoint = endpoint or os.environ["TOPOGYM_ENV_URL"]
        self.token = token or os.environ["TOPOGYM_ENV_TOKEN"]
        self.timeout_s = timeout_s
        self.revision = None
        self.opener = build_opener(ProxyHandler({}))
        self.describe()

    def _call(self, method, params=None, *, mutate=False, request_id=None):
        data = dict(method=method, params=params or {}, request_id=request_id or str(uuid.uuid4()))
        if mutate:
            data["expected_revision"] = self.revision
        request = Request(self.endpoint, data=json.dumps(data, allow_nan=False).encode(),
            headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"})
        try:
            with self.opener.open(request, timeout=self.timeout_s) as stream:
                result = json.load(stream)
        except HTTPError as exc:
            result = json.load(exc)
            raise EnvironmentError(result.get("error", "Environment request failed")) from None
        self.revision = result["state_revision"]
        return result

    def describe(self):
        return self._call("describe")

    def observe(self):
        return self._call("observe")

    render = observe

    def list_entities(self):
        return self._call("list_entities")

    def get_state(self, fields=None):
        return self._call("get_state", {} if fields is None else {"fields": fields})

    def get_pose(self, entity, frame="world"):
        return self._call("get_pose", dict(entity=entity, frame=frame))

    def step(self, action, steps=1):
        return self._call("step", dict(action=action, steps=steps), mutate=True)

    def reset(self):
        return self._call("reset", mutate=True)

    def finish(self):
        return self._call("finish", mutate=True)


def connect(**kwargs):
    return Environment(**kwargs)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TopoGym live environment client (JSON output)")
    parser.add_argument("method", choices=("describe", "observe", "render", "list_entities", "get_state", "get_pose", "step", "reset", "finish"))
    parser.add_argument("--params", default="{}", help="JSON keyword arguments")
    args = parser.parse_args()
    print(json.dumps(getattr(connect(), args.method)(**json.loads(args.params)), indent=2))
