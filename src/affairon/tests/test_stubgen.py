from pathlib import Path

from affairon.fairun import stubgen


def test_render_stub_content_for_dynamic_children() -> None:
    source_path = Path(__file__).resolve()
    parent_map: stubgen.ParentMap = {
        stubgen.ParentSpec(name="_StubRoom", module="tests.test_stubgen"): [
            stubgen.ChildSpec(
                route_name="members",
                child_name="_StubMemberList",
                child_module="tests.test_stubgen",
            ),
            stubgen.ChildSpec(
                route_name="log",
                child_name="_StubMessageLog",
                child_module="tests.test_stubgen",
            ),
        ],
        stubgen.ParentSpec(
            name="_StubMemberList",
            module="tests.test_stubgen",
        ): [
            stubgen.ChildSpec(
                route_name="stats",
                child_name="_StubMemberStats",
                child_module="tests.test_stubgen",
            )
        ],
    }

    rendered = stubgen.render_stub_content(source_path, parent_map)

    assert "from __future__ import annotations\n" in rendered
    assert "class _StubRoom:\n" in rendered
    assert "    log: _StubMessageLog\n" in rendered
    assert "    members: _StubMemberList\n" in rendered
    assert "class _StubMemberList:\n" in rendered
    assert "    stats: _StubMemberStats\n" in rendered
    assert "class _StubMessageLog:\n    ...\n" in rendered
    assert "class _StubMemberStats:\n    ...\n" in rendered
    assert "from " not in rendered.split("\n\n", 2)[1]


def test_generate_stub_files_from_ast_project(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.affairon]\n", encoding="utf-8")

    package_dir = tmp_path / "sampleapp"
    package_dir.mkdir()
    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    (package_dir / "root_nodes.py").write_text(
        "from affairon import Node, root, route\n\n\n"
        "@root\n"
        '@route("room")\n'
        "class Room(Node):\n"
        "    pass\n",
        encoding="utf-8",
    )
    (package_dir / "child_nodes.py").write_text(
        "from affairon import Node, inject_to, route\n"
        "from sampleapp.root_nodes import Room\n\n\n"
        "@inject_to(Room)\n"
        '@route("members")\n'
        "class MemberList(Node):\n"
        "    pass\n\n\n"
        "@inject_to(MemberList)\n"
        '@route("stats")\n'
        "class MemberStats(Node):\n"
        "    pass\n",
        encoding="utf-8",
    )

    generated = stubgen.generate_stub_files(tmp_path)

    root_stub = package_dir / "root_nodes.pyi"
    child_stub = package_dir / "child_nodes.pyi"
    assert set(generated) == {root_stub, child_stub}

    root_content = root_stub.read_text(encoding="utf-8")
    assert "from __future__ import annotations\n" in root_content
    assert "from sampleapp.child_nodes import MemberList\n" in root_content
    assert "class Room:\n" in root_content
    assert "    members: MemberList\n" in root_content

    child_content = child_stub.read_text(encoding="utf-8")
    assert "from __future__ import annotations\n" in child_content
    assert "class MemberList:\n" in child_content
    assert "    stats: MemberStats\n" in child_content
    assert "class MemberStats:\n    ...\n" in child_content
    assert "from " not in child_content.split("\n\n", 2)[1]


def test_non_node_class_with_attributes_and_methods(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "helpers.py").write_text(
        "class Clock:\n"
        "    def __init__(self) -> None:\n"
        "        self.tick = 0\n"
        "\n"
        "    def advance(self) -> int:\n"
        "        self.tick += 1\n"
        "        return self.tick\n",
        encoding="utf-8",
    )

    generated = stubgen.generate_stub_files(tmp_path)

    assert len(generated) == 1
    content = generated[0].read_text(encoding="utf-8")
    assert "class Clock:" in content
    assert "    tick: int" in content
    assert "    def advance(self) -> int: ..." in content
    assert "__init__" not in content


def test_annotated_init_attributes(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "store.py").write_text(
        "class Store:\n"
        "    def __init__(self) -> None:\n"
        "        self.names: list[str] = []\n"
        "        self.counts: dict[str, int] = {}\n",
        encoding="utf-8",
    )

    generated = stubgen.generate_stub_files(tmp_path)

    content = generated[0].read_text(encoding="utf-8")
    assert "    counts: dict[str, int]" in content
    assert "    names: list[str]" in content


def test_injected_parameter_stripping(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "nodes.py").write_text(
        "from __future__ import annotations\n"
        "from typing import Annotated\n"
        "from affairon import Node, Root, Parent, affair, associate, route\n"
        "\n"
        "class Timer:\n"
        "    pass\n"
        "\n"
        '@route("parent")\n'
        "class ParentNode(Node):\n"
        "    pass\n"
        "\n"
        '@route("child")\n'
        "class ChildNode(Node):\n"
        "    RecordAffair = affair()\n"
        "\n"
        "    @associate(RecordAffair)\n"
        "    def record(\n"
        "        self,\n"
        "        text: str,\n"
        "        timer: Annotated[Timer, Root / Timer],\n"
        "        parent: Annotated[ParentNode, Parent / ParentNode],\n"
        "    ) -> dict[str, int]:\n"
        "        return {'count': 1}\n",
        encoding="utf-8",
    )

    generated = stubgen.generate_stub_files(tmp_path)

    content = generated[0].read_text(encoding="utf-8")
    assert "def record(self, text: str) -> dict[str, int]: ..." in content
    assert "timer" not in content
    assert "Annotated" not in content
    assert "Root / " not in content
    assert "Parent / " not in content


def test_top_level_function_extraction(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "lib.py").write_text(
        "def greet(name: str) -> str:\n"
        "    return f'hello {name}'\n"
        "\n"
        "def build() -> tuple[int, str]:\n"
        "    return 1, 'x'\n",
        encoding="utf-8",
    )

    generated = stubgen.generate_stub_files(tmp_path)

    content = generated[0].read_text(encoding="utf-8")
    assert "def build() -> tuple[int, str]: ..." in content
    assert "def greet(name: str) -> str: ..." in content


def test_class_body_annotations(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "models.py").write_text(
        "class Config:\n    timeout: int\n    name: str\n",
        encoding="utf-8",
    )

    generated = stubgen.generate_stub_files(tmp_path)

    content = generated[0].read_text(encoding="utf-8")
    assert "class Config:" in content
    assert "    name: str" in content
    assert "    timeout: int" in content


def test_import_rendering_for_external_types(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "app.py").write_text(
        "from affairon import Node, Dispatcher\n"
        "\n"
        "def setup() -> tuple[Node, Dispatcher]:\n"
        "    return Node(), Dispatcher()\n",
        encoding="utf-8",
    )

    generated = stubgen.generate_stub_files(tmp_path)

    content = generated[0].read_text(encoding="utf-8")
    assert "from affairon import Dispatcher, Node" in content
    assert "def setup() -> tuple[Node, Dispatcher]: ..." in content


def test_empty_init_py_is_skipped(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "core.py").write_text(
        "class Foo:\n    x: int\n",
        encoding="utf-8",
    )

    generated = stubgen.generate_stub_files(tmp_path)

    generated_names = {p.name for p in generated}
    assert "__init__.pyi" not in generated_names
    assert "core.pyi" in generated_names


def test_nodesample_golden(tmp_path: Path) -> None:
    import shutil

    src = Path(__file__).resolve().parent.parent / "examples" / "nodes" / "nodesample"
    shutil.copytree(
        src,
        tmp_path / "nodesample",
        ignore=shutil.ignore_patterns(".venv", "__pycache__", "*.pyi", "uv.lock"),
    )

    generated = stubgen.generate_stub_files(tmp_path / "nodesample")

    stubs = {p.name: p.read_text(encoding="utf-8") for p in generated}
    assert "app.pyi" in stubs
    assert "nodes.pyi" in stubs
    assert "host.pyi" in stubs

    nodes_stub = stubs["nodes.pyi"]
    assert "from __future__ import annotations" in nodes_stub
    assert "from affairon import" in nodes_stub

    assert "class Clock:" in nodes_stub
    assert "    tick: int" in nodes_stub
    assert "    def advance(self) -> int: ..." in nodes_stub

    assert "class Room(Node):" in nodes_stub
    assert "    log: MessageLog" in nodes_stub
    assert "    members: MemberList" in nodes_stub

    assert "class MemberList(Node):" in nodes_stub
    assert "    names: list[str]" in nodes_stub
    assert "    stats: MemberStats" in nodes_stub
    assert "    def join(self, name: str) -> dict[str, bool]: ..." in nodes_stub
    assert "    def kick(self, name: str) -> dict[str, bool]: ..." in nodes_stub

    assert "class MemberStats(Node):" in nodes_stub
    assert "    counts: dict[str, int]" in nodes_stub
    assert "    def bump(self, name: str) -> dict[str, int]: ..." in nodes_stub

    assert "class MessageLog(Node):" in nodes_stub
    assert "    entries: list[dict[str, str | int]]" in nodes_stub
    assert (
        "    def record(self, sender: str, text: str) -> dict[str, int]: ..."
        in nodes_stub
    )

    assert "Annotated" not in nodes_stub
    assert "Root / Clock" not in nodes_stub
    assert "Parent / MemberList" not in nodes_stub
    assert "__init__" not in nodes_stub

    app_stub = stubs["app.pyi"]
    assert "def build_room() -> tuple[Room, Dispatcher]: ..." in app_stub
    assert "def demo() -> dict[str, object]: ..." in app_stub

    host_stub = stubs["host.pyi"]
    assert "def run(_affair: AffairMain) -> dict[str, object]: ..." in host_stub
    assert "from affairon import AffairMain" in host_stub


def test_node_child_attrs_merge_with_class_attrs(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "nodes.py").write_text(
        "from affairon import Node, inject_to, root, route\n"
        "\n"
        "@root\n"
        '@route("app")\n'
        "class App(Node):\n"
        "    version: str\n"
        "\n"
        "@inject_to(App)\n"
        '@route("db")\n'
        "class DB(Node):\n"
        "    def __init__(self) -> None:\n"
        "        super().__init__()\n"
        "        self.connected: bool = False\n",
        encoding="utf-8",
    )

    generated = stubgen.generate_stub_files(tmp_path)

    content = generated[0].read_text(encoding="utf-8")
    assert "class App(Node):" in content
    assert "    db: DB" in content
    assert "    version: str" in content
    assert "class DB(Node):" in content
    assert "    connected: bool" in content


def test_trivial_init_filtered_but_nontrivial_preserved(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "models.py").write_text(
        "class Simple:\n"
        "    def __init__(self) -> None:\n"
        "        self.x = 0\n"
        "\n"
        "class Complex:\n"
        "    def __init__(self, name: str, count: int = 0) -> None:\n"
        "        self.name = name\n"
        "        self.count = count\n",
        encoding="utf-8",
    )

    generated = stubgen.generate_stub_files(tmp_path)

    content = generated[0].read_text(encoding="utf-8")
    assert "class Simple:" in content
    assert "def __init__(self) -> None: ..." not in content

    assert "class Complex:" in content
    assert "def __init__(self, name: str, count: int = ...) -> None: ..." in content
