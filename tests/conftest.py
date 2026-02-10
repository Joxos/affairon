"""Shared test fixtures for all eventd tests."""

import pytest


@pytest.fixture
def sample_event_data() -> dict:
    """Sample event data for testing."""
    return {"user_id": 123, "action": "login"}


@pytest.fixture
def sample_callback():
    """Sample synchronous callback function."""

    def handler(event) -> dict:
        return {"handled": True}

    return handler


@pytest.fixture
async def sample_async_callback():
    """Sample asynchronous callback function."""

    async def handler(event) -> dict:
        return {"handled": True}

    return handler
