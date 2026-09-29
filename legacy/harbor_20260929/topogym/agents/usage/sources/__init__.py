"""Versioned provider receipts. Text chunks are never treated as exact tokens."""
from .openai_responses import ResponsesUsage, ResponsesProtocol
from .anthropic_messages import MessagesUsage, MessagesProtocol
from .chat_completions import ChatUsage, ChatProtocol

SOURCES = {"responses": ResponsesUsage, "messages": MessagesUsage, "chat_completions": ChatUsage}
PROTOCOLS = {"responses": ResponsesProtocol(), "messages": MessagesProtocol(), "chat_completions": ChatProtocol()}
