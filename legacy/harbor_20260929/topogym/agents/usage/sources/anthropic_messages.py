from .common import ReceiptSource
from .base import ProviderProtocol
from ..types import token_count


class MessagesUsage(ReceiptSource):
    name = "anthropic.messages.v1"

    def __init__(self, request_id):
        super().__init__(request_id)
        self.parts = {}

    def feed(self, payload, *, streaming=True):
        kind = payload.get("type", "")
        usage = payload.get("message", payload).get("usage")
        final = not streaming or kind == "message_stop"
        if usage is None and not final:
            return None
        self.parts.update(usage or {})
        # Missing cache counters on ordinary uncached Messages responses mean no
        # cache usage. Missing main input/output counters remain unknown.
        inputs = None
        if "input_tokens" in self.parts:
            inputs = sum(token_count(self.parts.get(k, 0), k) for k in
                         ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
        return self.event(input_tokens=inputs, output_tokens=self.parts.get("output_tokens"), final=final,
            details={k: v for k, v in self.parts.items() if k not in {"input_tokens", "output_tokens"}})


class MessagesProtocol(ProviderProtocol):
    route = "/messages"
    receipt_type = MessagesUsage
    allowed_tools = frozenset({"custom"})
    default_tool = "custom"

    def build_headers(self, credential, allowed_headers):
        headers = {"Content-Type": "application/json", "Accept-Encoding": "identity",
                   "x-api-key": credential, "anthropic-version": "2023-06-01"}
        if allowed_headers.get("anthropic-beta"):
            headers["anthropic-beta"] = allowed_headers["anthropic-beta"]
        return headers
