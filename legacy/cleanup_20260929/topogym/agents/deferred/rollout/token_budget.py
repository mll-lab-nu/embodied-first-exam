"""Per-repeat receipts and reservations for individual model requests."""
import copy
import threading
import time

from topogym.agent_bridge.session import write_json


class TokenBudgetExhausted(RuntimeError):
    pass


def natural(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


class TokenBudget:
    def __init__(self, private, public, limit=3_000_000):
        self.limit = natural(limit, "token_limit", 1)
        self.private, self.public = private, public
        self.calls, self.blocked, self.reason = [], None, None
        self.lock = threading.RLock()
        self._persist()

    def snapshot(self):
        with self.lock:
            used = sum(c.get("usage", {}).get("total_tokens", 0) for c in self.calls)
            reserved = sum(c["reservation"] for c in self.calls if c["state"] != "complete")
            return dict(limit=self.limit, used=used, reserved=reserved,
                        remaining=max(0, self.limit-used-reserved),
                        usage_complete=all(c["state"] == "complete" for c in self.calls),
                        requests=len(self.calls), blocked=self.blocked, reason=self.reason,
                        over_budget=used > self.limit,
                        enforcement="input_count_and_max_output_tokens")

    def _persist(self):
        status = self.snapshot()
        write_json(self.private / "token_budget.json", dict(status, calls=copy.deepcopy(self.calls)))
        write_json(self.public / "token_budget.json", status)

    def stop(self, code, reason):
        with self.lock:
            if not self.blocked:
                self.blocked, self.reason = code, str(reason)
            self._persist()

    def require_ready(self):
        with self.lock:
            if self.blocked == "token_budget_exhausted":
                raise TokenBudgetExhausted(self.reason)
            if self.blocked:
                raise RuntimeError(self.reason)
            if any(c["state"] != "complete" for c in self.calls):
                raise RuntimeError("A model request still has an unsettled token reservation")

    def reserve(self, input_tokens, output_cap):
        with self.lock:
            self.require_ready()
            natural(input_tokens, "input_tokens")
            natural(output_cap, "max_output_tokens", 1)
            available = self.snapshot()["remaining"] - input_tokens
            if available < 1:
                message = f"Remaining token budget cannot fit the next input ({input_tokens} tokens) and output"
                self.stop("token_budget_exhausted", message)
                raise TokenBudgetExhausted(message)
            cap = min(output_cap, available)
            item = dict(request=len(self.calls)+1, input_tokens=input_tokens, max_output_tokens=cap,
                        reservation=input_tokens+cap, state="pending", started_at=time.time())
            self.calls.append(item)
            self._persist()  # Durable reservation BEFORE the billable request.
            print(f"[tokens] request {item['request']}: input={input_tokens}, output_cap={cap}, "
                  f"used={self.snapshot()['used']}/{self.limit}", flush=True)
            return item["request"], cap

    def complete(self, request, usage):
        with self.lock:
            item = self.calls[request-1]
            if not isinstance(usage, dict):
                raise ValueError("Model response did not contain a usage receipt")
            for field in ("input_tokens", "output_tokens", "total_tokens"):
                natural(usage.get(field), field)
            if usage["total_tokens"] != usage["input_tokens"] + usage["output_tokens"]:
                raise ValueError("Usage total must equal input_tokens + output_tokens")
            # Cached input and reasoning output are already included in these totals.
            if item["state"] == "complete":
                if usage != item["usage"]:
                    raise ValueError("Conflicting usage receipt")
                return
            item.update(state="complete", usage=copy.deepcopy(usage), completed_at=time.time())
            exceeded = (usage["input_tokens"] > item["input_tokens"] or
                        usage["output_tokens"] > item["max_output_tokens"])
            if exceeded:
                self.stop("reservation_exceeded", "Provider usage exceeded the preflight reservation")
            self._persist()
            status = self.snapshot()
            print(f"[tokens] used={status['used']}/{self.limit}, remaining={status['remaining']}", flush=True)
            if exceeded:
                raise RuntimeError(self.reason)

    def usage_since(self, index):
        with self.lock:
            calls = self.calls[index:]
            if not calls or any(c["state"] != "complete" for c in calls):
                return None
            return {field: sum(c["usage"][field] for c in calls)
                    for field in ("input_tokens", "output_tokens", "total_tokens")}

    def notice(self):
        status = self.snapshot()
        return (f"Token budget for this attempt: {status['used']:,} / {self.limit:,} tokens used. "
                f"Remaining unreserved tokens: {status['remaining']:,}. "
                "The budget includes all model input and output across tool calls and action segments.")
