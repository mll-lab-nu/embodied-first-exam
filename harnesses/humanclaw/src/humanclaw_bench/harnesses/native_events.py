"""Native JSONL evidence and non-overlapping accounting responsibilities."""

from __future__ import annotations

import contextvars
from typing import Any

from humanclaw_bench.experiments.recorder import event, span
from .services import trace_payload


class NativeOperationInterrupted(BaseException):
    """No completion event was observed; keep it outside resolved failure rates."""


class NativeEvents:
    """Normalize observed tools/modules without claiming invisible internals.

    Each open operation owns a copied context. Interleaved tool events do not
    accidentally become children of whichever operation started most recently.
    Environment dispatch is a module; the bridge counts the actual action once.
    """

    def __init__(self, harness: str, call_names: dict[str, str] | None = None,
                 requested_calls: set[str] | None = None):
        """Capture the enclosing session context and native call-name mapping."""
        self.harness = harness
        self.context = contextvars.copy_context()
        self.open: dict[str, tuple[Any, Any]] = {}
        self.call_names = call_names if call_names is not None else {}
        self.requested_calls = requested_calls if requested_calls is not None else set()
        self.registered: set[tuple[str, str]] = set()

    def start(self, ident: str, name: str, kind: str, data: Any, parent: str | None = None):
        """Open an independently scoped operation, preserving an explicit parent."""
        if ident in self.open:
            return
        context = self.open[parent][0].copy() if parent in self.open else self.context.copy()
        operation = context.run(span, name, kind=kind, input=trace_payload(data),
                                attributes={"native_id": ident, "boundary": "native_event"})
        if (kind, name) not in self.registered:
            context.run(event, "capability.registered", kind=kind, name=name,
                        data={"observability": "native_event", "available": True})
            self.registered.add((kind, name))
        if kind == "tool" and not any(part in self.requested_calls for part in ident.split("|")):
            context.run(event, "tool.requested", kind=kind, name=name, data={"native_id": ident})
        context.run(operation.__enter__)
        self.open[ident] = context, operation

    def end(self, ident: str, data: Any, failed: bool = False):
        """Close a known operation once without fabricating absent start events."""
        value = self.open.pop(ident, None)
        if value is None:
            return
        context, operation = value
        operation.set_output(trace_payload(data))
        if failed:
            operation.fail({"type": "NativeOperationFailed", "native_id": ident})
        context.run(operation.__exit__, None, None, None)

    def consume(self, row: dict[str, Any]):
        """Persist a native event and normalize its observable operation boundaries."""
        event("native.event", kind="native", name=self.harness, data=trace_payload(row))
        if self.harness == "codex":
            method, params = row.get("method"), row.get("params") or {}
            if method in {"item/started", "item/completed"}:
                item = params.get("item") or {}
                item_type, ident = item.get("type", "unknown"), item.get("id", "unknown")
                if item_type in {"agentMessage", "reasoning", "userMessage"}:
                    return
                environment = item_type == "mcpToolCall" and item.get("server") == "humanclaw"
                kind = "module" if environment or item_type == "contextCompaction" else "tool"
                name = "codex.environment_dispatch" if environment else self.call_names.get(ident, f"codex.{item_type}")
                if method == "item/started":
                    self.start(ident, name, kind, item)
                else:
                    self.end(ident, item, item.get("status") == "failed" or bool(item.get("error"))
                             or bool((item.get("result") or {}).get("isError")))
        else:
            kind = row.get("type", "")
            if kind == "tool_execution_start":
                name = row["toolName"]
                environment = name.startswith("mcp__humanclaw__")
                self.start(row["toolCallId"], "pi.environment_dispatch" if environment else f"pi.{name}",
                           "module" if environment else "tool", row, row.get("parentToolCallId"))
            elif kind == "tool_execution_end":
                self.end(row["toolCallId"], row, bool(row.get("isError")))
            elif kind in {"auto_compaction_start", "auto_retry_start"}:
                self.start(kind[:-6], "pi." + kind[:-6], "module", row)
            elif kind in {"auto_compaction_end", "auto_retry_end"}:
                self.end(kind[:-4], row, bool(row.get("errorMessage")))

    def close(self):
        """Interrupt operations lacking native completion events."""
        for ident in list(self.open):
            context, operation = self.open.pop(ident)
            error = NativeOperationInterrupted("Native session ended before operation completion")
            context.run(operation.__exit__, type(error), error, None)
