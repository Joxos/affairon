from __future__ import annotations

import pytest

from affairon import RuntimeRegistry, inject_from


class PhaseRuntime:
    def __init__(self, phase: str) -> None:
        self.phase = phase


class TurnRuntime:
    def __init__(self, turn: int) -> None:
        self.turn = turn


def _registry() -> RuntimeRegistry:
    registry = RuntimeRegistry()
    registry.provide(PhaseRuntime("DRAW"))
    registry.provide(TurnRuntime(3))
    return registry


def test_provide_and_inject_returns_same_instance() -> None:
    registry = RuntimeRegistry()
    runtime = PhaseRuntime("ok")

    registry.provide(runtime)

    assert registry.inject(PhaseRuntime) is runtime


def test_injects_missing_annotated_parameters() -> None:
    registry = _registry()

    @inject_from(lambda affair: affair)
    def listener(
        affair: RuntimeRegistry, phase: PhaseRuntime, turn: TurnRuntime
    ) -> tuple[str, int]:
        return phase.phase, turn.turn

    assert listener(registry) == ("DRAW", 3)


def test_explicit_arguments_win_over_injected_values() -> None:
    registry = _registry()
    explicit = PhaseRuntime("BATTLE")

    @inject_from(lambda affair: affair)
    def listener(affair: RuntimeRegistry, phase: PhaseRuntime) -> str:
        return phase.phase

    assert listener(registry, explicit) == "BATTLE"


def test_missing_registration_raises_lookup_error() -> None:
    registry = RuntimeRegistry()

    @inject_from(lambda affair: affair)
    def listener(affair: RuntimeRegistry, phase: PhaseRuntime) -> str:
        return phase.phase

    with pytest.raises(LookupError, match="PhaseRuntime not provided"):
        listener(registry)


def test_unsupported_annotation_fails_fast() -> None:
    registry = _registry()

    @inject_from(lambda affair: affair)
    def listener(affair: RuntimeRegistry, phase: str) -> str:
        return phase

    with pytest.raises(TypeError, match="Unsupported injected annotation"):
        listener(registry)


@pytest.mark.asyncio
async def test_async_listener_injection() -> None:
    registry = _registry()

    @inject_from(lambda affair: affair)
    async def listener(affair: RuntimeRegistry, turn: TurnRuntime) -> int:
        return turn.turn

    assert await listener(registry) == 3
