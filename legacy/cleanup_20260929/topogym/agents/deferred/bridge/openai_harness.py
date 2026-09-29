"""Optional Responses API reference harness, using only Python's standard library.

No automatic retry of billable requests: ambiguous usage keeps its reservation
and stops the episode. Images/history selection here is a harness policy, not a
benchmark restriction. Requires explicit --model and OPENAI_API_KEY.
"""
import argparse
import base64
import hashlib
import json
import os
import time
from urllib.parse import quote
from urllib.request import Request, urlopen
import uuid

from .client import Client


INSTRUCTIONS = '''You are controlling a persistent robot environment with irreversible actions.
Follow the task/action contract in the supplied prompt. Return one JSON object, without Markdown:
{"action":"segment","code":"env.step(...)","frames":[],"reason":""}
or {"action":"inspect","code":"","frames":["segment_001/front/000001.png"],"reason":""}
or {"action":"stop","code":"","frames":[],"reason":"why you cannot continue"}.
Only the evaluator can declare success. You can inspect any saved frame or manifest by its path.
All control-tick frames are stored. The initial/default visual input is the latest frame from all cameras;
request additional frames or manifests as needed. You choose how much history to inspect.
The harness supplies recent conversation turns; older images/manifests remain available on disk.
Use the observation and action schema; do not assume the smoke task's actions work on other tasks.
'''


class OpenAIResponses:
    def __init__(self, key):
        self.key = key

    def _request(self, path, payload):
        return Request("https://api.openai.com/v1"+path, data=json.dumps(payload).encode(),
            headers={"Authorization": "Bearer "+self.key, "Content-Type": "application/json"})

    def count(self, payload):
        with urlopen(self._request("/responses/input_tokens", payload), timeout=120) as response:
            return json.load(response)["input_tokens"]

    def generate(self, payload, on_progress):
        final, characters, last = None, 0, 0
        with urlopen(self._request("/responses", dict(payload, stream=True, store=False)), timeout=3600) as stream:
            for line in stream:
                if not line.startswith(b"data:"):
                    continue
                data = line[5:].strip()
                if data == b"[DONE]":
                    break
                event = json.loads(data)
                if event.get("type") == "response.output_text.delta":
                    characters += len(event["delta"])
                    if time.monotonic()-last >= 1:
                        on_progress(characters)
                        last = time.monotonic()
                if event.get("type") in ("response.completed", "response.incomplete", "response.failed"):
                    final = event["response"]
                if event.get("type") == "error":
                    raise RuntimeError(f"Provider stream error: {event.get('message', '')}")
        if final is None or final.get("usage") is None:
            raise RuntimeError("Stream ended without a usage receipt; reservation remains outstanding")
        return final


def artifact_content(client, paths):
    content = []
    for path in paths:
        if not isinstance(path, str):
            raise ValueError("Artifact paths must be strings")
        endpoint = "/artifacts/"+quote(path, safe="/")
        data = client.request(endpoint, raw=True)
        if path.endswith(".png"):
            content.extend([dict(type="input_text", text=path),
                dict(type="input_image", image_url="data:image/png;base64,"+base64.b64encode(data).decode())])
        elif path.endswith(".json"):
            content.append(dict(type="input_text", text=path+"\n"+data.decode()))
        else:
            raise ValueError("Inspect accepts PNG frames or JSON manifests")
    return content


def run(client, provider, *, model, max_output_tokens=8192, history_turns=8):
    if max_output_tokens < 1 or history_turns < 1:
        raise ValueError("Output cap and history_turns must be positive")
    if client.state()["budget"]["mode"] != "metered":
        raise ValueError("Start the bridge with --mode metered")
    history, requested, feedback = [], None, ""
    try:
        while (state := client.state())["state"] == "ready":
            if requested is None:
                manifest = client.request("/artifacts/"+state["latest_manifest"])
                requested = [v["path"] for v in manifest["frames"][-1]["cameras"].values()]
            prompt = client.request("/v1/prompt")["prompt"]
            content = [dict(type="input_text", text=prompt+"\nPrevious result: "+feedback)]
            content += artifact_content(client, requested)
            current = dict(role="user", content=content)
            payload = dict(model=model, instructions=INSTRUCTIONS, input=history[-2*history_turns:]+[current])
            inputs = provider.count(payload)
            available = state["budget"]["remaining"] - inputs
            if available <= 0:
                client.request("/v1/finish", dict(outcome="budget_exhausted", reason="Remaining budget cannot fit the next model input"))
                break
            cap = min(max_output_tokens, available)
            call_id = str(uuid.uuid4())
            client.request("/v1/usage/reserve", dict(call_id=call_id, input_tokens=inputs,
                                                    max_output_tokens=cap, model=model))
            response = provider.generate(dict(payload, max_output_tokens=cap),
                lambda n: client.request("/v1/usage/progress", dict(call_id=call_id, output_chars=n)))
            client.request("/v1/usage/complete", dict(call_id=call_id, usage=response["usage"],
                response=dict(provider_response=response,
                              request=dict(model=model, prompt=prompt, instructions=INSTRUCTIONS,
                                  sha256=hashlib.sha256(json.dumps(payload).encode()).hexdigest()), max_output_tokens=cap,
                              harness=dict(history_turns=history_turns, selected_artifacts=requested))))
            if client.state()["state"] != "ready":
                break
            text = "".join(part.get("text", "") for item in response.get("output", [])
                           if item.get("type") == "message" for part in item.get("content", [])
                           if part.get("type") == "output_text")
            history += [current, dict(role="assistant", content=text or "[No output text]")]
            history = history[-2*history_turns:]
            requested = None
            try:
                if response.get("status") != "completed":
                    raise ValueError(f"Model response was {response.get('status')}; write a shorter reply")
                command = json.loads(text)
                if command["action"] == "segment":
                    feedback = json.dumps(client.submit(command["code"], request_id=call_id,
                        expected_segment=state["next_segment"], call_id=call_id))
                elif command["action"] == "inspect":
                    paths = command["frames"]
                    if not isinstance(paths, list) or not paths:
                        raise ValueError("frames must be a nonempty list of saved paths")
                    # Validate now, so malformed requests are recoverable next turn.
                    artifact_content(client, paths)
                    requested, feedback = paths, "Requested historical artifacts follow."
                elif command["action"] == "stop":
                    client.request("/v1/finish", dict(reason=str(command.get("reason", "Agent stopped"))))
                else:
                    raise ValueError("Unknown action; choose segment, inspect or stop")
            except (ValueError, KeyError, TypeError) as exc:
                feedback = f"Request rejected before further execution: {exc}"
    except BaseException as exc:
        # Never release an ambiguous reservation, replay actions or retry billing.
        client.request("/v1/finish", dict(reason=f"Harness stopped: {type(exc).__name__}: {exc}"))
        raise
    return client.state()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--model", required=True)
    parser.add_argument("--max-output-tokens", type=int, default=8192)
    parser.add_argument("--history-turns", type=int, default=8)
    args = parser.parse_args()
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise SystemExit("Set OPENAI_API_KEY in the environment; never put it in policy code or the browser")
    result = run(Client(args.url), OpenAIResponses(key), model=args.model,
                 max_output_tokens=args.max_output_tokens, history_turns=args.history_turns)
    print(json.dumps({k: result[k] for k in ("state", "reason", "budget", "success_within_budget")}, indent=2))


if __name__ == "__main__":
    main()
