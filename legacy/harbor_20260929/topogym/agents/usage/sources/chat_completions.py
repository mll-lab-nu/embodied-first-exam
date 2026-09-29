from .common import ReceiptSource
from .base import ProviderProtocol


class ChatUsage(ReceiptSource):
    name = "openai.chat_completions.v1"

    def feed(self, payload, *, streaming=True):
        usage = payload.get("usage")
        if usage is None and streaming:
            return None
        usage = usage or {}
        # OpenRouter and OpenAI totals include reasoning/cache. Do not add details.
        return self.event(input_tokens=usage.get("prompt_tokens"), output_tokens=usage.get("completion_tokens"),
            final=True, details={k: usage[k] for k in ("prompt_tokens_details", "completion_tokens_details") if k in usage})


class ChatProtocol(ProviderProtocol):
    route = "/chat/completions"
    receipt_type = ChatUsage

    def cap_field(self, body):
        if "max_completion_tokens" in body:
            body.pop("max_tokens", None)
            return "max_completion_tokens"
        return self.output_field

    def prepare_stream(self, body):
        if body.get("stream"):
            body["stream_options"] = {**body.get("stream_options", {}), "include_usage": True}
