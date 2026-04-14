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
