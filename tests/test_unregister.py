"""Tests for listener unregistration."""

import pytest

from affairon import Dispatcher, MutableAffair
from conftest import Ping, Pong


class TestUnregister:
    def test_mode1_specific_callback_specific_affair(self):
        """unregister(Affair, callback=cb) removes only that pair."""
        d = Dispatcher()

        def h(e: MutableAffair) -> None: ...

        d.register(Ping, h)
        d.unregister(Ping, callback=h)
        assert d.emit(Ping(msg="x")) == {}

    def test_mode2_all_listeners_from_affair(self):
        """unregister(Affair) clears all listeners for that affair."""
        d = Dispatcher()
        d.register(Ping, lambda e: {"a": 1})
        d.register(Ping, lambda e: {"b": 2})
        d.unregister(Ping)
        assert d.emit(Ping(msg="x")) == {}

    def test_mode3_callback_from_all_affairs(self):
        """unregister(callback=cb) removes it everywhere."""
        d = Dispatcher()

        def h(e: MutableAffair) -> None: ...

        d.register([Ping, Pong], h)
        d.unregister(callback=h)
        assert d.emit(Ping(msg="x")) == {}
        assert d.emit(Pong(msg="x")) == {}

    def test_no_args_raises(self):
        """unregister() with no arguments raises ValueError."""
        d = Dispatcher()
        with pytest.raises(ValueError, match="must provide"):
            d.unregister()
