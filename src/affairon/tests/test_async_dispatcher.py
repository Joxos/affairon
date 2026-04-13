"""Tests for AsyncDispatcher."""

import pytest
from conftest import ChildAffair, GrandchildAffair, MutablePing, ParentAffair, Ping

from affairon import CallbackErrorAffair, KeyConflictError, MutableAffair
from affairon.async_dispatcher import AsyncDispatcher


class TestAsyncDispatcher:
    @pytest.mark.asyncio
    async def test_emit_merges_results(self):
        """Multiple async listeners, results merged."""
        d = AsyncDispatcher()

        @d.on(Ping)
        async def h1(e: MutableAffair) -> dict:
            return {"a": 1}

        @d.on(Ping)
        async def h2(e: MutableAffair) -> dict:
            return {"b": 2}

        result = await d.emit(Ping(msg="x"))
        assert result == {"a": 1, "b": 2}

    @pytest.mark.asyncio
    async def test_emit_exception_group(self):
        """Failing listeners propagate ExceptionGroup."""
        d = AsyncDispatcher()

        @d.on(Ping)
        async def bad1(e: MutableAffair) -> dict:
            raise ValueError("e1")

        @d.on(Ping)
        async def bad2(e: MutableAffair) -> dict:
            raise ValueError("e2")

        with pytest.raises(ExceptionGroup) as exc_info:
            await d.emit(Ping(msg="x"))
        assert len(exc_info.value.exceptions) == 2


class TestAsyncEmitUp:
    @pytest.mark.asyncio
    async def test_emit_up_false_fires_only_child(self):
        """Default emit_up=False only fires callbacks on the concrete type."""
        d = AsyncDispatcher()
        parent_called = []
        child_called = []

        @d.on(ParentAffair)
        async def parent_handler(e: MutableAffair) -> None:
            parent_called.append(1)

        @d.on(ChildAffair)
        async def child_handler(e: MutableAffair) -> None:
            child_called.append(1)

        await d.emit(ChildAffair(msg="hi", extra="x"))

        assert child_called == [1]
        assert parent_called == []

    @pytest.mark.asyncio
    async def test_emit_up_true_fires_child_and_parent(self):
        """emit_up=True fires child callbacks then parent callbacks."""
        d = AsyncDispatcher()
        order = []

        @d.on(ParentAffair)
        async def parent_handler(e: MutableAffair) -> None:
            order.append("parent")

        @d.on(ChildAffair)
        async def child_handler(e: MutableAffair) -> None:
            order.append("child")

        await d.emit(ChildAffair(msg="hi", extra="x", emit_up=True))

        assert order == ["child", "parent"]

    @pytest.mark.asyncio
    async def test_emit_up_true_merges_results_across_hierarchy(self):
        """emit_up=True merges results from child and parent callbacks."""
        d = AsyncDispatcher()

        @d.on(ParentAffair)
        async def parent_handler(e: MutableAffair) -> dict:
            return {"from_parent": True}

        @d.on(ChildAffair)
        async def child_handler(e: MutableAffair) -> dict:
            return {"from_child": True}

        result = await d.emit(ChildAffair(msg="hi", extra="x", emit_up=True))

        assert result == {"from_child": True, "from_parent": True}

    @pytest.mark.asyncio
    async def test_emit_up_multilevel_hierarchy(self):
        """emit_up=True walks full MRO: grandchild -> child -> parent."""
        d = AsyncDispatcher()
        order = []

        @d.on(ParentAffair)
        async def parent_handler(e: MutableAffair) -> None:
            order.append("parent")

        @d.on(ChildAffair)
        async def child_handler(e: MutableAffair) -> None:
            order.append("child")

        @d.on(GrandchildAffair)
        async def grandchild_handler(e: MutableAffair) -> None:
            order.append("grandchild")

        await d.emit(GrandchildAffair(msg="hi", extra="x", detail="d", emit_up=True))

        assert order == ["grandchild", "child", "parent"]

    @pytest.mark.asyncio
    async def test_emit_up_key_conflict_across_hierarchy(self):
        """emit_up=True raises KeyConflictError on cross-hierarchy key clash."""
        d = AsyncDispatcher()

        @d.on(ParentAffair)
        async def parent_handler(e: MutableAffair) -> dict:
            return {"k": "parent"}

        @d.on(ChildAffair)
        async def child_handler(e: MutableAffair) -> dict:
            return {"k": "child"}

        with pytest.raises(KeyConflictError):
            await d.emit(ChildAffair(msg="hi", extra="x", emit_up=True))

    @pytest.mark.asyncio
    async def test_emit_up_no_parent_listeners(self):
        """emit_up=True with no parent callbacks is a harmless no-op."""
        d = AsyncDispatcher()

        @d.on(ChildAffair)
        async def child_handler(e: MutableAffair) -> dict:
            return {"from_child": True}

        result = await d.emit(ChildAffair(msg="hi", extra="x", emit_up=True))

        assert result == {"from_child": True}


class TestAsyncWhenFilter:
    @pytest.mark.asyncio
    async def test_when_true_fires_callback(self):
        """Async callback with when predicate returning True fires normally."""
        d = AsyncDispatcher()

        @d.on(Ping, when=lambda a: a.msg == "yes")
        async def handler(affair: Ping) -> dict:
            return {"fired": affair.msg}

        result = await d.emit(Ping(msg="yes"))
        assert result == {"fired": "yes"}

    @pytest.mark.asyncio
    async def test_when_false_skips_callback(self):
        """Async callback with when predicate returning False is skipped."""
        d = AsyncDispatcher()

        @d.on(Ping, when=lambda a: a.msg == "yes")
        async def handler(affair: Ping) -> dict:
            return {"fired": affair.msg}

        result = await d.emit(Ping(msg="no"))
        assert result == {}

    @pytest.mark.asyncio
    async def test_when_mixed_filtered_and_unfiltered(self):
        """Only async callbacks whose when predicate passes contribute."""
        d = AsyncDispatcher()

        @d.on(Ping, when=lambda a: a.msg == "target")
        async def selective(affair: Ping) -> dict:
            return {"selective": "yes"}

        @d.on(Ping)
        async def always(affair: Ping) -> dict:
            return {"always": "yes"}

        result = await d.emit(Ping(msg="target"))
        assert result == {"selective": "yes", "always": "yes"}

        result = await d.emit(Ping(msg="other"))
        assert result == {"always": "yes"}

    @pytest.mark.asyncio
    async def test_when_filtered_callback_not_awaited(self):
        """Filtered-out async callbacks are never scheduled as tasks."""
        d = AsyncDispatcher()
        called = []

        @d.on(Ping, when=lambda a: a.msg == "go")
        async def tracked(affair: Ping) -> None:
            called.append(1)

        await d.emit(Ping(msg="stop"))
        assert called == []

        await d.emit(Ping(msg="go"))
        assert called == [1]

    @pytest.mark.asyncio
    async def test_when_with_emit_up(self):
        """Async when predicate checked per-affair-type during emit_up."""
        d = AsyncDispatcher()

        @d.on(ParentAffair, when=lambda a: a.msg == "yes")
        async def parent_handler(e: MutableAffair) -> dict:
            return {"parent": True}

        @d.on(ChildAffair)
        async def child_handler(e: MutableAffair) -> dict:
            return {"child": True}

        result = await d.emit(ChildAffair(msg="yes", extra="x", emit_up=True))
        assert result == {"child": True, "parent": True}

        result = await d.emit(ChildAffair(msg="no", extra="x", emit_up=True))
        assert result == {"child": True}


class TestAsyncCallbackErrorHandling:
    @pytest.mark.asyncio
    async def test_no_handler_reraises(self):
        """No error handler registered → exception re-raised as-is."""
        d = AsyncDispatcher()

        @d.on(MutablePing)
        async def bad(affair: MutablePing) -> None:
            raise ValueError("boom")

        with pytest.raises(ExceptionGroup) as exc_info:
            await d.emit(MutablePing(msg="x"))
        assert any(
            isinstance(e, ValueError) and str(e) == "boom"
            for e in exc_info.value.exceptions
        )

    @pytest.mark.asyncio
    async def test_silent_swallows_error(self):
        """Error handler returning silent=True swallows the exception."""
        d = AsyncDispatcher()

        @d.on(MutablePing)
        async def bad(affair: MutablePing) -> None:
            raise ValueError("boom")

        @d.on(CallbackErrorAffair)
        async def handler(affair: CallbackErrorAffair) -> dict[str, bool]:
            return {"silent": True}

        result = await d.emit(MutablePing(msg="x"))
        assert result == {}

    @pytest.mark.asyncio
    async def test_retry_succeeds(self):
        """Retry succeeds on second attempt, returns callback result."""
        d = AsyncDispatcher()
        call_count = 0

        @d.on(MutablePing)
        async def flaky(affair: MutablePing) -> dict[str, int]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("transient")
            return {"attempt": call_count}

        @d.on(CallbackErrorAffair)
        async def handler(affair: CallbackErrorAffair) -> dict[str, int]:
            return {"retry": 2}

        result = await d.emit(MutablePing(msg="x"))
        assert result == {"attempt": 2}
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_retry_exhausted_reraises(self):
        """All retries fail → exception re-raised (surfaces as ExceptionGroup)."""
        d = AsyncDispatcher()

        @d.on(MutablePing)
        async def bad(affair: MutablePing) -> None:
            raise RuntimeError("fail")

        @d.on(CallbackErrorAffair)
        async def handler(affair: CallbackErrorAffair) -> dict[str, int]:
            return {"retry": 2}

        with pytest.raises(ExceptionGroup):
            await d.emit(MutablePing(msg="x"))

    @pytest.mark.asyncio
    async def test_retry_exhausted_then_silent(self):
        """All retries fail + silent=True → swallow error."""
        d = AsyncDispatcher()

        @d.on(MutablePing)
        async def bad(affair: MutablePing) -> None:
            raise RuntimeError("fail")

        @d.on(CallbackErrorAffair)
        async def handler(affair: CallbackErrorAffair) -> dict[str, int | bool]:
            return {"retry": 2, "silent": True}

        result = await d.emit(MutablePing(msg="x"))
        assert result == {}

    @pytest.mark.asyncio
    async def test_deadletter_without_retry(self):
        """deadletter=True with no retry → returns None immediately."""
        d = AsyncDispatcher()

        @d.on(MutablePing)
        async def bad(affair: MutablePing) -> None:
            raise RuntimeError("fail")

        @d.on(CallbackErrorAffair)
        async def handler(affair: CallbackErrorAffair) -> dict[str, bool]:
            return {"deadletter": True}

        result = await d.emit(MutablePing(msg="x"))
        assert result == {}

    @pytest.mark.asyncio
    async def test_error_affair_fields_correct(self):
        """CallbackErrorAffair carries correct metadata about the failure."""
        d = AsyncDispatcher()
        captured: list[CallbackErrorAffair] = []

        @d.on(MutablePing)
        async def failing(affair: MutablePing) -> None:
            raise TypeError("bad type")

        @d.on(CallbackErrorAffair)
        async def handler(affair: CallbackErrorAffair) -> dict[str, bool]:
            captured.append(affair)
            return {"silent": True}

        await d.emit(MutablePing(msg="x"))

        assert len(captured) == 1
        ea = captured[0]
        assert "failing" in ea.listener_name
        assert ea.original_affair_type == "MutablePing"
        assert ea.error_message == "bad type"
        assert ea.error_type == "TypeError"

    @pytest.mark.asyncio
    async def test_error_handling_preserves_other_callback_results(self):
        """Successful callbacks' results preserved when one fails silently."""
        d = AsyncDispatcher()

        @d.on(MutablePing)
        async def good(affair: MutablePing) -> dict[str, str]:
            return {"good": "yes"}

        @d.on(MutablePing, after=[good])
        async def bad(affair: MutablePing) -> dict[str, str]:
            raise ValueError("boom")

        @d.on(CallbackErrorAffair)
        async def handler(affair: CallbackErrorAffair) -> dict[str, bool]:
            return {"silent": True}

        result = await d.emit(MutablePing(msg="x"))
        assert result == {"good": "yes"}

    @pytest.mark.asyncio
    async def test_parallel_errors_both_handled(self):
        """Two parallel callbacks both fail → both handled independently."""
        d = AsyncDispatcher()

        @d.on(MutablePing)
        async def bad1(affair: MutablePing) -> None:
            raise ValueError("e1")

        @d.on(MutablePing)
        async def bad2(affair: MutablePing) -> None:
            raise ValueError("e2")

        @d.on(CallbackErrorAffair)
        async def handler(affair: CallbackErrorAffair) -> dict[str, bool]:
            return {"silent": True}

        # Both errors silenced, no ExceptionGroup
        result = await d.emit(MutablePing(msg="x"))
        assert result == {}

    @pytest.mark.asyncio
    async def test_invalid_retry_value_raises_type_error(self):
        """Non-int-convertible retry value raises TypeError."""
        d = AsyncDispatcher()

        @d.on(MutablePing)
        async def bad(affair: MutablePing) -> None:
            raise ValueError("x")

        @d.on(CallbackErrorAffair)
        async def handler(affair: CallbackErrorAffair) -> dict[str, str]:
            return {"retry": "not_a_number"}

        with pytest.raises(ExceptionGroup):
            await d.emit(MutablePing(msg="x"))


class TestAsyncMergeStrategyRaise:
    @pytest.mark.asyncio
    async def test_raise_is_default(self):
        """Default strategy raises KeyConflictError on duplicate keys."""
        d = AsyncDispatcher()

        @d.on(Ping)
        async def h1(e: MutableAffair) -> dict:
            return {"k": 1}

        @d.on(Ping)
        async def h2(e: MutableAffair) -> dict:
            return {"k": 2}

        with pytest.raises(KeyConflictError):
            await d.emit(Ping(msg="x"))

    @pytest.mark.asyncio
    async def test_raise_no_conflict_merges(self):
        """No conflict under raise strategy merges normally."""
        d = AsyncDispatcher()

        @d.on(Ping)
        async def h1(e: MutableAffair) -> dict:
            return {"a": 1}

        @d.on(Ping)
        async def h2(e: MutableAffair) -> dict:
            return {"b": 2}

        result = await d.emit(Ping(msg="x", merge_strategy="raise"))
        assert result == {"a": 1, "b": 2}


class TestAsyncMergeStrategyKeep:
    @pytest.mark.asyncio
    async def test_keep_first_value_wins(self):
        """Keep strategy retains the first value for a duplicate key."""
        d = AsyncDispatcher()
        order = []

        @d.on(Ping)
        async def first(e: Ping) -> dict:
            order.append("first")
            return {"k": 1}

        @d.on(Ping, after=[first])
        async def second(e: Ping) -> dict:
            order.append("second")
            return {"k": 2}

        result = await d.emit(Ping(msg="x", merge_strategy="keep"))
        assert result == {"k": 1}
        assert order == ["first", "second"]

    @pytest.mark.asyncio
    async def test_keep_no_conflict(self):
        """Keep strategy merges disjoint keys normally."""
        d = AsyncDispatcher()

        @d.on(Ping)
        async def h1(e: MutableAffair) -> dict:
            return {"a": 1}

        @d.on(Ping)
        async def h2(e: MutableAffair) -> dict:
            return {"b": 2}

        result = await d.emit(Ping(msg="x", merge_strategy="keep"))
        assert result == {"a": 1, "b": 2}


class TestAsyncMergeStrategyOverride:
    @pytest.mark.asyncio
    async def test_override_last_value_wins(self):
        """Override strategy replaces with the last value for a duplicate key."""
        d = AsyncDispatcher()
        order = []

        @d.on(Ping)
        async def first(e: Ping) -> dict:
            order.append("first")
            return {"k": 1}

        @d.on(Ping, after=[first])
        async def second(e: Ping) -> dict:
            order.append("second")
            return {"k": 2}

        result = await d.emit(Ping(msg="x", merge_strategy="override"))
        assert result == {"k": 2}
        assert order == ["first", "second"]

    @pytest.mark.asyncio
    async def test_override_no_conflict(self):
        """Override strategy merges disjoint keys normally."""
        d = AsyncDispatcher()

        @d.on(Ping)
        async def h1(e: MutableAffair) -> dict:
            return {"a": 1}

        @d.on(Ping)
        async def h2(e: MutableAffair) -> dict:
            return {"b": 2}

        result = await d.emit(Ping(msg="x", merge_strategy="override"))
        assert result == {"a": 1, "b": 2}


class TestAsyncMergeStrategyListMerge:
    @pytest.mark.asyncio
    async def test_list_merge_collects_values(self):
        """list_merge wraps all values into lists and appends on conflict."""
        d = AsyncDispatcher()

        @d.on(Ping)
        async def h1(e: MutableAffair) -> dict:
            return {"k": 1}

        @d.on(Ping)
        async def h2(e: MutableAffair) -> dict:
            return {"k": 2}

        result = await d.emit(Ping(msg="x", merge_strategy="list_merge"))
        assert result == {"k": [1, 2]}

    @pytest.mark.asyncio
    async def test_list_merge_single_value(self):
        """list_merge wraps single-callback value in a list."""
        d = AsyncDispatcher()

        @d.on(Ping)
        async def handler(e: MutableAffair) -> dict:
            return {"k": "only"}

        result = await d.emit(Ping(msg="x", merge_strategy="list_merge"))
        assert result == {"k": ["only"]}

    @pytest.mark.asyncio
    async def test_list_merge_disjoint_keys(self):
        """list_merge wraps each disjoint key as a single-element list."""
        d = AsyncDispatcher()

        @d.on(Ping)
        async def h1(e: MutableAffair) -> dict:
            return {"a": 1}

        @d.on(Ping)
        async def h2(e: MutableAffair) -> dict:
            return {"b": 2}

        result = await d.emit(Ping(msg="x", merge_strategy="list_merge"))
        assert result == {"a": [1], "b": [2]}

    @pytest.mark.asyncio
    async def test_list_merge_three_callbacks(self):
        """list_merge collects values from three callbacks into one list."""
        d = AsyncDispatcher()

        @d.on(Ping)
        async def h1(e: MutableAffair) -> dict:
            return {"k": 1}

        @d.on(Ping)
        async def h2(e: MutableAffair) -> dict:
            return {"k": 2}

        @d.on(Ping)
        async def h3(e: MutableAffair) -> dict:
            return {"k": 3}

        result = await d.emit(Ping(msg="x", merge_strategy="list_merge"))
        assert result == {"k": [1, 2, 3]}


class TestAsyncMergeStrategyDictMerge:
    @pytest.mark.asyncio
    async def test_dict_merge_collects_by_callback_name(self):
        """dict_merge stores values keyed by callback qualname."""
        d = AsyncDispatcher()

        @d.on(Ping)
        async def alpha(e: Ping) -> dict:
            return {"k": 1}

        @d.on(Ping)
        async def beta(e: Ping) -> dict:
            return {"k": 2}

        result = await d.emit(Ping(msg="x", merge_strategy="dict_merge"))
        assert "alpha" in str(result["k"])
        assert "beta" in str(result["k"])
        assert len(result["k"]) == 2

    @pytest.mark.asyncio
    async def test_dict_merge_single_value(self):
        """dict_merge wraps single-callback value in a dict."""
        d = AsyncDispatcher()

        @d.on(Ping)
        async def handler(e: Ping) -> dict:
            return {"k": 42}

        result = await d.emit(Ping(msg="x", merge_strategy="dict_merge"))
        assert isinstance(result["k"], dict)
        assert 42 in result["k"].values()

    @pytest.mark.asyncio
    async def test_dict_merge_disjoint_keys(self):
        """dict_merge wraps each disjoint key as a single-entry dict."""
        d = AsyncDispatcher()

        @d.on(Ping)
        async def handler(e: Ping) -> dict:
            return {"a": 1, "b": 2}

        result = await d.emit(Ping(msg="x", merge_strategy="dict_merge"))
        assert isinstance(result["a"], dict)
        assert isinstance(result["b"], dict)


class TestAsyncMergeStrategyWithErrorHandling:
    @pytest.mark.asyncio
    async def test_error_handler_uses_raise_strategy(self):
        """Error affair dispatch always uses raise strategy internally."""
        d = AsyncDispatcher()

        @d.on(MutablePing)
        async def bad(affair: MutablePing) -> None:
            raise ValueError("boom")

        @d.on(CallbackErrorAffair)
        async def handler(affair: CallbackErrorAffair) -> dict[str, bool]:
            return {"silent": True}

        # Should not wrap silent as [True] — error dispatch uses "raise"
        result = await d.emit(MutablePing(msg="x", merge_strategy="list_merge"))
        assert result == {}

    @pytest.mark.asyncio
    async def test_retry_with_non_raise_strategy(self):
        """Retry works correctly when dispatcher uses non-raise strategy."""
        d = AsyncDispatcher()
        call_count = 0

        @d.on(MutablePing)
        async def flaky(affair: MutablePing) -> dict[str, int]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("transient")
            return {"attempt": call_count}

        @d.on(CallbackErrorAffair)
        async def handler(affair: CallbackErrorAffair) -> dict[str, int]:
            return {"retry": 2}

        result = await d.emit(MutablePing(msg="x", merge_strategy="override"))
        assert result == {"attempt": 2}

    @pytest.mark.asyncio
    async def test_list_merge_with_emit_up(self):
        """list_merge collects values across emit_up hierarchy."""
        d = AsyncDispatcher()

        @d.on(ParentAffair)
        async def parent_handler(e: MutableAffair) -> dict:
            return {"k": "parent"}

        @d.on(ChildAffair)
        async def child_handler(e: MutableAffair) -> dict:
            return {"k": "child"}

        result = await d.emit(
            ChildAffair(msg="hi", extra="x", emit_up=True, merge_strategy="list_merge")
        )
        assert result == {"k": ["child", "parent"]}
