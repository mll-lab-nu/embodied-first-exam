"""Trusted harness accounting. Cached/reasoning tokens are subsets, not extras."""
import copy

from .policy import integer


class Budget:
    def __init__(self, limit=2_000_000, mode="metered"):
        self.limit = integer(limit, "token_limit", 1, 2_000_000)
        if mode not in ("metered", "manual"):
            raise ValueError("mode must be metered or manual")
        self.mode, self.calls = mode, {}

    def snapshot(self):
        used = sum(c.get("usage", {}).get("total_tokens", 0) for c in self.calls.values())
        held = sum(c["cap"] for c in self.calls.values() if c["state"] == "pending")
        return dict(limit=self.limit, used=used, reserved=held,
                    remaining=max(0, self.limit-used-held), mode=self.mode,
                    exact=self.mode == "metered" and all(c["state"] == "complete" for c in self.calls.values()),
                    over_budget=used > self.limit, calls=copy.deepcopy(self.calls))

    def reserve(self, call_id, input_tokens, max_output_tokens, model="external"):
        if not isinstance(call_id, str) or not 1 <= len(call_id) <= 128:
            raise ValueError("call_id must be a nonempty string of at most 128 characters")
        integer(input_tokens, "input_tokens")
        integer(max_output_tokens, "max_output_tokens", 1)
        item = dict(input_tokens=input_tokens, max_output_tokens=max_output_tokens,
                    model=str(model), cap=input_tokens+max_output_tokens, state="pending", output_chars=0)
        if call_id in self.calls:
            old = self.calls[call_id]
            if any(old[k] != item[k] for k in ("input_tokens", "max_output_tokens", "model")):
                raise ValueError("Conflicting call_id")
            return
        if any(c["state"] == "pending" for c in self.calls.values()):
            raise ValueError("Only one model call may be pending")
        if item["cap"] > self.snapshot()["remaining"]:
            raise ValueError("Insufficient token budget; reduce output cap or context")
        self.calls[call_id] = item

    def progress(self, call_id, output_chars):
        c = self.calls[call_id]
        integer(output_chars, "output_chars")
        if c["state"] != "pending" or output_chars < c["output_chars"]:
            raise ValueError("Progress must be monotonic on a pending call")
        c["output_chars"] = output_chars

    def complete(self, call_id, usage, response=None):
        c = self.calls[call_id]
        usage = copy.deepcopy(usage)
        for name in ("input_tokens", "output_tokens", "total_tokens"):
            integer(usage.get(name), name)
        if usage["total_tokens"] != usage["input_tokens"] + usage["output_tokens"]:
            raise ValueError("total_tokens must equal input_tokens + output_tokens")
        for group, name, upper in (("input_tokens_details", "cached_tokens", "input_tokens"),
                                   ("output_tokens_details", "reasoning_tokens", "output_tokens")):
            details = usage.get(group) or {}
            integer(details.get(name, 0), name, 0, usage[upper])
        if c["state"] == "complete":
            if c["usage"] != usage:
                raise ValueError("Conflicting usage receipt")
            return
        c.update(state="complete", usage=usage,
                 reservation_exceeded=(usage["input_tokens"] > c["input_tokens"] or
                                       usage["output_tokens"] > c["max_output_tokens"]))

    def estimate(self, call_id, input_tokens, output_tokens):
        if self.mode != "manual":
            raise ValueError("Estimates are only accepted in manual mode")
        integer(input_tokens, "input_tokens")
        integer(output_tokens, "output_tokens")
        if not isinstance(call_id, str) or not 1 <= len(call_id) <= 128:
            raise ValueError("Invalid call_id")
        if call_id not in self.calls:
            # These tokens have already been spent in the external chat. Record
            # even an overrun rather than silently discarding its estimate.
            self.calls[call_id] = dict(input_tokens=input_tokens, max_output_tokens=max(1, output_tokens),
                model="manual_estimate", cap=input_tokens+output_tokens, state="pending", output_chars=0)
        self.complete(call_id, dict(input_tokens=input_tokens, output_tokens=output_tokens,
                                    total_tokens=input_tokens+output_tokens))
