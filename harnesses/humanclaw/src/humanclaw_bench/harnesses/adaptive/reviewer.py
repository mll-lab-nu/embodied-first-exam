"""Direct loopback review requests through the existing metered provider gateway."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from ..provider_errors import provider_failure


def independent_review(services, payload, deadline):
    """Bypass outbound proxies only for loopback; retry explicit transient review failures."""
    parsed = urlsplit(services.url)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.username or parsed.password:
        raise ValueError("Independent review requires the authenticated loopback gateway")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(services.url + "/v1/responses", data=json.dumps(payload).encode(),
        headers={"Authorization": "Bearer " + services.bearer, "Content-Type": "application/json"})
    for attempt in range(1, 5):
        failure = None
        try:
            if time.monotonic() >= deadline or services.closed.is_set():
                raise TimeoutError("Episode closed before independent review")
            terminal = None
            with opener.open(request, timeout=min(600, max(.01, deadline-time.monotonic()))) as response:
                for line in response:
                    if not line.startswith(b"data: ") or line[6:].strip() == b"[DONE]":
                        continue
                    item = json.loads(line[6:])
                    if item.get("type") in {"response.completed", "response.failed", "response.incomplete"}:
                        terminal = item
                    elif item.get("type") == "error":
                        failure = provider_failure(error=item.get("error") or item)
            if terminal and terminal["type"] == "response.completed" and failure is None:
                text = "".join(c.get("text", "") for o in terminal["response"].get("output", []) for c in o.get("content", []))
                answer = json.loads(text.strip().removeprefix("```json").removesuffix("```").strip())
                if not isinstance(answer, dict) or answer.get("status") not in {"pass", "fail", "inconclusive"} or not isinstance(answer.get("reason"), str):
                    raise ValueError("Invalid independent review verdict")
                return {"status": answer["status"], "reason": answer["reason"], "attempts": attempt,
                        **({"reference_cases": answer["reference_cases"]} if isinstance(answer.get("reference_cases"), list) else {})}
            result = (terminal or {}).get("response", {})
            failure = failure or provider_failure(error=result.get("error"), incomplete=result.get("incomplete_details"))
            if failure is None:
                failure = {"category": "review_response", "retryable": False, "message": "Missing complete review response"}
        except urllib.error.HTTPError as exc:
            try:
                body = json.loads(exc.read())
            except (ValueError, UnicodeError):
                body = {}
            failure = provider_failure(status=exc.code, error=body.get("error") if isinstance(body, dict) else None)
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            failure = {"category": "review_transport" if isinstance(exc, OSError) else "review_response",
                       "retryable": False, "message": str(exc)}
        if not failure["retryable"] or attempt == 4:
            return {"status": "inconclusive", "reason": failure.get("message") or failure["category"],
                    "infrastructure_error": failure, "attempts": attempt}
        # The gateway owns provider cooldown and meters each actual HTTP attempt.
    raise AssertionError("Review retry loop did not terminate")
