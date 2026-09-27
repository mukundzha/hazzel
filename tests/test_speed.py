"""Speed and robustness fixes: no double-charged requests, no phantom
timeouts, fewer model round trips, bounded in-turn context."""

import time

import pytest

from hazzel.agent import core
from hazzel.agent import dispatch
from hazzel.agent import fastpath
from hazzel.agent import history
from hazzel.agent.history import _enforce_turn_budget
from hazzel.agent.toolspec import PARALLEL_SAFE, PARALLEL_SAFE_JOB_WAIT, PARALLEL_TOOL_TIMEOUT
from hazzel.providers import base as pbase

MSGS = [{"role": "system", "content": "x"}]


class _Boom:
    """Provider whose stream and chat both fail with a given message."""

    def __init__(self, message):
        self.message = message
        self.calls = 0

    def stream(self, *a, **k):
        self.calls += 1
        raise RuntimeError(self.message)

    def chat(self, *a, **k):
        self.calls += 1
        raise RuntimeError(self.message)


def _stream_calls(message):
    provider = _Boom(message)
    with pytest.raises(Exception):
        core._safe_stream_chat(provider, MSGS, [])
    return provider.calls


# --- one model request per failure, not two -------------------------------


@pytest.mark.parametrize("message", [
    "Error code: 401 - invalid_api_key",
    "Error code: 403 - forbidden",
    "AuthenticationError: no api key",
    "Error code: 404 - model_not_found",
    "Error code: 401 - permission denied for this model",
])
def test_auth_errors_cost_one_request(message):
    # Dropping stream=True can never fix these; retrying just doubles latency.
    assert _stream_calls(message) == 1


@pytest.mark.parametrize("message", [
    "stream_options is not supported by this endpoint",
    "Error: SSE stream not supported",
])
def test_stream_specific_errors_still_fall_back(message):
    # ...but these ARE fixed by dropping streaming, so the fallback must stay.
    assert _stream_calls(message) == 2


def test_generic_error_still_falls_back():
    assert _stream_calls("something odd happened") == 2


# --- parallel batches honor their timeout ---------------------------------


def test_is_parallel_safe_reads_arguments():
    assert dispatch._is_parallel_safe("read_file", {"path": "x"}) is True
    assert dispatch._is_parallel_safe("write_file", {}) is False


def test_long_job_wait_leaves_the_parallel_batch():
    # A 120s wait inside a 60s batch guarantees a bogus timeout for every sibling.
    assert dispatch._is_parallel_safe("jobs", {"action": "wait", "timeout": 120}) is False
    assert dispatch._is_parallel_safe("jobs", {"action": "wait", "timeout": 5}) is True
    assert dispatch._is_parallel_safe("jobs", {"action": "list"}) is True


def test_parallel_safe_job_wait_fits_the_budget():
    assert PARALLEL_SAFE_JOB_WAIT < PARALLEL_TOOL_TIMEOUT
    assert "jobs" in PARALLEL_SAFE


# --- transient failures retry instead of failing the turn -----------------


def test_transient_errors_are_recognized():
    for message in ["503 service unavailable", "502 bad gateway",
                    "Connection reset by peer", "Read timed out",
                    "remote end closed connection"]:
        assert pbase.is_transient_error(RuntimeError(message)), message


def test_non_transient_errors_are_not_retried():
    for message in ["401 invalid_api_key", "ValueError: bad tool json", "404 not found"]:
        assert not pbase.is_transient_error(RuntimeError(message)), message


def test_transient_failure_recovers_without_asking_the_model(monkeypatch):
    monkeypatch.setattr(pbase.time, "sleep", lambda *_: None)
    attempts = {"n": 0}

    def flaky():
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise RuntimeError("503 service unavailable")
        return "ok"

    assert pbase.call_with_backoff("test", flaky) == "ok"
    assert attempts["n"] == 2


def test_transient_retry_is_bounded(monkeypatch):
    monkeypatch.setattr(pbase.time, "sleep", lambda *_: None)
    attempts = {"n": 0}

    def always_down():
        attempts["n"] += 1
        raise RuntimeError("503 service unavailable")

    with pytest.raises(RuntimeError):
        pbase.call_with_backoff("test", always_down)
    assert attempts["n"] == pbase.TRANSIENT_ATTEMPTS


def test_permanent_error_is_not_retried(monkeypatch):
    monkeypatch.setattr(pbase.time, "sleep", lambda *_: None)
    attempts = {"n": 0}

    def bad_key():
        attempts["n"] += 1
        raise RuntimeError("401 invalid_api_key")

    with pytest.raises(RuntimeError):
        pbase.call_with_backoff("test", bad_key)
    assert attempts["n"] == 1


def test_retry_after_header_is_honored(monkeypatch):
    slept = []
    monkeypatch.setattr(pbase.time, "sleep", lambda s: slept.append(s))

    class Response:
        headers = {"retry-after": "7"}

    class Limited(Exception):
        response = Response()

    attempts = {"n": 0}

    def throttled():
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise Limited("429 rate limit")
        return "ok"

    assert pbase.call_with_backoff("test", throttled) == "ok"
    assert slept == [7.0]


# --- in-turn context stays bounded ----------------------------------------


def test_turn_budget_distills_tool_call_arguments(monkeypatch):
    # An 8k write_file body is an echo of work already done: pure latency on
    # every later iteration of the same turn.
    monkeypatch.setattr(history, "TURN_TOKEN_BUDGET", 200)
    big = "x" * 8000
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "1", "type": "function",
             "function": {"name": "write_file", "arguments": '{"content":"' + big + '"}'}}]},
        {"role": "tool", "content": "wrote ok", "tool_call_id": "1"},
    ]
    _enforce_turn_budget(messages)
    args = messages[1]["tool_calls"][0]["function"]["arguments"]
    assert "…distilled…" in args
    assert len(args) < 1000


def test_turn_budget_leaves_short_arguments_alone(monkeypatch):
    monkeypatch.setattr(history, "TURN_TOKEN_BUDGET", 200)
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "1", "type": "function",
             "function": {"name": "read_file", "arguments": '{"path":"a.py"}'}}]},
    ]
    _enforce_turn_budget(messages)
    assert messages[1]["tool_calls"][0]["function"]["arguments"] == '{"path":"a.py"}'


def test_turn_budget_still_distills_tool_results(monkeypatch):
    monkeypatch.setattr(history, "TURN_TOKEN_BUDGET", 200)
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "tool", "content": "y" * 5000, "tool_call_id": "1"},
    ]
    _enforce_turn_budget(messages)
    assert "…distilled…" in messages[1]["content"]


# --- zero-LLM fast paths for lookup-shaped requests ------------------------


@pytest.mark.parametrize("text,tool", [
    ("find all *.py files", "glob"),
    ("find **/*.toml", "glob"),
    ("show me *.json files", "glob"),
    ("list all *.cfg files", "glob"),
    ("find test_*.py files in tests", "glob"),
    ('grep "def run" in src', "search_files"),
    ("grep for MAX_ITERATIONS in src", "search_files"),
])
def test_lookup_requests_skip_the_model(text, tool):
    result = fastpath.try_fast_path(MSGS, text)
    assert result is not None, f"{text!r} should not need a model call"
    assert result[1][0]["tool"] == tool


@pytest.mark.parametrize("text", [
    "why is the parser slow",
    "fix the failing test in test_tools.py",
    "find the bug and fix it",
    "add a glob tool",
    "search for the bug that causes the parser to fail and fix it",
    "what does agent/core.py do",
    "refactor the history module",
    "find all the places where we call the provider and explain why",
])
def test_reasoning_requests_still_reach_the_model(text):
    assert fastpath.try_fast_path(MSGS, text) is None


def _scripted_provider(replies):
    """Fake provider that walks a fixed list of ChatResponses."""
    from hazzel.providers.base import ChatResponse, ToolCall

    class FakeProvider:
        provider_name = "Fake"
        seen = []

        def stream(self, messages, tools, on_token=None, think=False, on_reason=None):
            self.seen.append(messages)
            if not replies:
                return ChatResponse(content="done")
            item = replies.pop(0)
            if isinstance(item, str):
                return ChatResponse(content=item)
            content, calls = item
            return ChatResponse(
                content=content,
                tool_calls=[ToolCall(id=f"c{i}", name=n, arguments=a)
                            for i, (n, a) in enumerate(calls)],
            )

    return FakeProvider


def test_parallel_batch_returns_promptly_when_a_tool_hangs(monkeypatch):
    """A stuck tool must not hold the turn past the timeout.

    This is the regression that made the timeout a lie: the old code reported
    "Tool timed out after 60 seconds" and then blocked in the executor's
    __exit__ for as long as the tool actually took.
    """
    from hazzel import agent

    monkeypatch.setattr(core, "PARALLEL_TOOL_TIMEOUT", 0.3)
    monkeypatch.setattr(
        core, "get_provider",
        lambda: _scripted_provider([
            (None, [("read_file", '{"path":"a"}'), ("read_file", '{"path":"b"}')]),
            "finished",
        ])(),
    )

    def hang(tool_name, arguments):
        if arguments.get("path") == "b":
            time.sleep(30)
        return ("a contents", 0.001)

    monkeypatch.setattr(core, "_run_one_tool", hang)

    started = time.perf_counter()
    result = agent.run([{"role": "system", "content": "sys"}], "read both files")
    elapsed = time.perf_counter() - started

    assert elapsed < 5.0, f"turn blocked for {elapsed:.1f}s on a hung tool"
    reply, trace, _summary = result
    assert len(trace) == 2, trace
    assert any("timed out" in t["result"] for t in trace), trace
    assert any(t["result"] == "a contents" for t in trace), trace
    assert reply == "finished"


def test_parallel_batch_runs_reads_concurrently(monkeypatch):
    from hazzel import agent

    monkeypatch.setattr(
        core, "get_provider",
        lambda: _scripted_provider([
            (None, [("read_file", '{"path":"a"}'), ("read_file", '{"path":"b"}'),
                    ("read_file", '{"path":"c"}')]),
            "finished",
        ])(),
    )
    running = {"now": 0, "peak": 0}

    def slow(tool_name, arguments):
        running["now"] += 1
        running["peak"] = max(running["peak"], running["now"])
        time.sleep(0.2)
        running["now"] -= 1
        return ("contents", 0.2)

    monkeypatch.setattr(core, "_run_one_tool", slow)
    started = time.perf_counter()
    agent.run([{"role": "system", "content": "sys"}], "read three files")
    elapsed = time.perf_counter() - started

    assert running["peak"] > 1, "reads ran one at a time"
    assert elapsed < 0.5, f"three 0.2s reads took {elapsed:.2f}s — not parallel"


def test_is_print_readonly_does_not_break_parallel_safety():
    # Regression guard: the argument-aware check must survive print mode.
    dispatch.set_print_approvals(False)
    try:
        assert dispatch._is_parallel_safe("read_file", {"path": "."}) is True
    finally:
        dispatch.set_print_approvals(None)
