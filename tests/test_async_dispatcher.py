"""Tests for AsyncDispatcher."""

import pytest

from affairon import MutableAffair
from affairon.async_dispatcher import AsyncDispatcher
from conftest import Ping


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
