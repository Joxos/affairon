from pathlib import Path

from affairon.fairun import cli


class _DummyComposer:
    def __init__(self, dispatcher, events: list[str]):
        self._dispatcher = dispatcher
        self._events = events

    def compose_from_pyproject(self, pyproject_path: Path) -> None:
        self._events.append(f"compose:{pyproject_path.name}:{id(self._dispatcher)}")


def test_main_sync_uses_same_dispatcher_for_compose_and_emit(
    monkeypatch,
    tmp_path: Path,
):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("[tool.affairon]\n", encoding="utf-8")

    events: list[str] = []

    class _FakeSyncDispatcher:
        def emit(self, affair) -> None:
            events.append(
                f"emit:{id(self)}:{affair.project_path}:{id(affair.dispatcher)}"
            )

    fake_sync_dispatcher = _FakeSyncDispatcher()

    def composer_factory(dispatcher):
        events.append(f"composer:{id(dispatcher)}")
        return _DummyComposer(dispatcher, events)

    monkeypatch.setattr(cli, "default_dispatcher", fake_sync_dispatcher)
    monkeypatch.setattr(cli, "default_async_dispatcher", object())
    monkeypatch.setattr(cli, "PluginComposer", composer_factory)

    cli.main([str(tmp_path)])

    dispatcher_id = id(fake_sync_dispatcher)
    assert events[0] == f"composer:{dispatcher_id}"
    assert events[1] == f"compose:pyproject.toml:{dispatcher_id}"
    assert events[2] == f"emit:{dispatcher_id}:{tmp_path.resolve()}:{dispatcher_id}"


def test_main_async_uses_same_dispatcher_for_compose_and_emit(
    monkeypatch,
    tmp_path: Path,
):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("[tool.affairon]\n", encoding="utf-8")

    events: list[str] = []

    class _FakeAsyncDispatcher:
        async def emit(self, affair) -> None:
            events.append(
                f"emit:{id(self)}:{affair.project_path}:{id(affair.dispatcher)}"
            )

    fake_async_dispatcher = _FakeAsyncDispatcher()

    def composer_factory(dispatcher):
        events.append(f"composer:{id(dispatcher)}")
        return _DummyComposer(dispatcher, events)

    monkeypatch.setattr(cli, "default_dispatcher", object())
    monkeypatch.setattr(cli, "default_async_dispatcher", fake_async_dispatcher)
    monkeypatch.setattr(cli, "PluginComposer", composer_factory)

    cli.main(["--async", str(tmp_path)])

    dispatcher_id = id(fake_async_dispatcher)
    assert events[0] == f"composer:{dispatcher_id}"
    assert events[1] == f"compose:pyproject.toml:{dispatcher_id}"
    assert events[2] == f"emit:{dispatcher_id}:{tmp_path.resolve()}:{dispatcher_id}"
