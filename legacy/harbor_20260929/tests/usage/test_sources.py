from topogym.agents.usage.sources import SOURCES


def test_messages_cumulative_and_caching():
    source = SOURCES["messages"]("r")
    first = source.feed({"type": "message_start", "message": {"usage": {
        "input_tokens": 10, "cache_read_input_tokens": 20, "cache_creation_input_tokens": 30, "output_tokens": 1}}})
    assert first.input_tokens == 60
    second = source.feed({"type": "message_delta", "usage": {"output_tokens": 9}})
    assert (second.input_tokens, second.output_tokens) == (60, 9)
    final = source.feed({"type": "message_stop"})
    assert final.final and final.output_tokens == 9
    assert source.feed({"type": "message_stop"}) == final


def test_responses_reasoning_and_cache_details_not_added_to_totals():
    source = SOURCES["responses"]("r")
    assert source.feed({"type": "response.output_text.delta", "delta": "many words"}) is None
    event = source.feed({"type": "response.completed", "response": {"usage": {
        "input_tokens": 10, "output_tokens": 20, "input_tokens_details": {"cached_tokens": 8},
        "output_tokens_details": {"reasoning_tokens": 12}}}})
    assert (event.input_tokens, event.output_tokens) == (10, 20)


def test_chat_end_usage_and_unknown_fields():
    source = SOURCES["chat_completions"]("r")
    assert source.feed({"choices": [{"delta": {"content": "hello"}}]}) is None
    event = source.feed({"usage": {"prompt_tokens": 7, "completion_tokens": 8,
        "completion_tokens_details": {"reasoning_tokens": 6}}})
    assert event.final and event.input_tokens == 7 and event.output_tokens == 8
    assert SOURCES["responses"]("missing").feed({"type": "response.completed", "response": {}}).input_tokens is None
