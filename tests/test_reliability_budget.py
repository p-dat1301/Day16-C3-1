from types import SimpleNamespace

from arena.model import FINALIZE_SENTINEL
from arena.tools import ToolResult
from harness.layers.budget_policy import BudgetPolicy
from harness.layers.retry import Retry


def _ctx(*, calls=0, limit=None, state=None):
    tools = SimpleNamespace(calls=calls)
    return SimpleNamespace(
        tools=tools,
        max_tool_calls=limit,
        state={} if state is None else state,
    )


def _scripted(ctx, results):
    seen = []

    def call(name, args):
        seen.append((name, args))
        result = results.pop(0)
        ctx.tools.calls += 1
        return result

    return call, seen


def test_retry_repeats_degraded_results_with_same_call_and_records_attempts():
    ctx = _ctx()
    call, seen = _scripted(
        ctx,
        [
            ToolResult(ok=True, content="[TRUNCATED: missing tail]"),
            ToolResult(ok=False, content="", error="timeout"),
            ToolResult(ok=True, content="complete"),
        ],
    )

    result = Retry().wrap_tool_call(ctx, call, "fetch_doc", {"doc_id": "doc-1"})

    assert result.content == "complete"
    assert seen == [("fetch_doc", {"doc_id": "doc-1"})] * 3
    assert ctx.state["retry_attempts"][-1]["attempts"] == 3


def test_retry_stops_at_max_attempts_and_respects_submit_reserve():
    ctx = _ctx(limit=3)
    call, seen = _scripted(
        ctx,
        [ToolResult(ok=False, content="", error="timeout") for _ in range(3)],
    )
    result = Retry(max_attempts=3).wrap_tool_call(ctx, call, "search", {"query": "q"})
    assert not result.ok
    assert len(seen) == 2
    assert ctx.state["retry_attempts"][-1]["attempts"] == 2

    ctx = _ctx(limit=2)
    call, seen = _scripted(
        ctx,
        [ToolResult(ok=False, content="", error="timeout") for _ in range(2)],
    )
    Retry().wrap_tool_call(ctx, call, "search", {"query": "q"})
    assert len(seen) == 1


def test_budget_adds_one_turn_finalize_nudge_without_mutating_messages():
    ctx = _ctx(calls=2, limit=3)
    messages = [{"role": "user", "content": "question"}]

    updated = BudgetPolicy().before_model(ctx, messages)

    assert updated is not messages
    assert messages == [{"role": "user", "content": "question"}]
    assert FINALIZE_SENTINEL in updated[-1]["content"]


def test_budget_blocks_tool_and_preserves_submit_slot():
    ctx = _ctx(calls=2, limit=3)
    called = False

    def call(name, args):
        nonlocal called
        called = True
        return ToolResult(ok=True, content="should not run")

    result = BudgetPolicy().wrap_tool_call(ctx, call, "search", {"query": "q"})

    assert isinstance(result, ToolResult)
    assert not result.ok
    assert "budget" in (result.error or "").lower()
    assert not called
    assert ctx.tools.calls == 2
