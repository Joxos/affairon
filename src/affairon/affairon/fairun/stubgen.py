from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, order=True)
class ParentSpec:
    name: str
    module: str


@dataclass(frozen=True, order=True)
class ChildSpec:
    route_name: str
    child_name: str
    child_module: str


@dataclass(frozen=True)
class _NodeClass:
    name: str
    module: str
    source_path: Path
    route_name: str | None
    inject_parent_expr: ast.expr | None
    is_root: bool


@dataclass(frozen=True)
class _ModuleInfo:
    module_name: str
    source_path: Path
    imports: dict[str, str]
    classes: dict[str, _NodeClass]


type ParentMap = dict[ParentSpec, list[ChildSpec]]
type SourceMap = dict[Path, ParentMap]

_SKIP_DIR_NAMES = {
    "__pycache__",
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".svn",
    ".venv",
    "build",
    "dist",
    "site-packages",
    "venv",
}


def _iter_python_sources(root_path: Path) -> list[Path]:
    sources: list[Path] = []
    for source_path in root_path.rglob("*.py"):
        relative_parts = source_path.relative_to(root_path).parts[:-1]
        if any(
            part in _SKIP_DIR_NAMES or part.startswith(".") for part in relative_parts
        ):
            continue
        sources.append(source_path)
    return sorted(sources)


def _qualify(module_name: str, symbol_name: str) -> str:
    return f"{module_name}.{symbol_name}" if module_name else symbol_name


def _module_name_for_path(root_path: Path, source_path: Path) -> str:
    relative = source_path.relative_to(root_path)
    parts = list(relative.parts)
    if source_path.name == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = source_path.stem
    return ".".join(parts)


def _package_name(module_name: str, source_path: Path) -> str:
    if source_path.name == "__init__.py":
        return module_name
    if "." not in module_name:
        return ""
    return module_name.rsplit(".", 1)[0]


def _resolve_import_module(
    current_module: str,
    source_path: Path,
    module: str | None,
    level: int,
) -> str:
    if level == 0:
        return module or ""

    package_parts = [
        part for part in _package_name(current_module, source_path).split(".") if part
    ]
    parent_levels = level - 1
    if parent_levels > len(package_parts):
        base_parts: list[str] = []
    else:
        base_parts = package_parts[: len(package_parts) - parent_levels]

    if module:
        base_parts.extend(module.split("."))
    return ".".join(base_parts)


def _decorator_leaf_name(expr: ast.expr) -> str | None:
    if isinstance(expr, ast.Name):
        return expr.id
    if isinstance(expr, ast.Attribute):
        return expr.attr
    return None


def _parse_module(root_path: Path, source_path: Path) -> _ModuleInfo:
    module_name = _module_name_for_path(root_path, source_path)
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))

    imports: dict[str, str] = {}
    classes: dict[str, _NodeClass] = {}

    for statement in tree.body:
        if isinstance(statement, ast.Import):
            for alias in statement.names:
                bound_name = alias.asname or alias.name.split(".", 1)[0]
                target = alias.name if alias.asname else bound_name
                imports[bound_name] = target
            continue

        if isinstance(statement, ast.ImportFrom):
            import_module = _resolve_import_module(
                module_name,
                source_path,
                statement.module,
                statement.level,
            )
            for alias in statement.names:
                if alias.name == "*":
                    continue
                bound_name = alias.asname or alias.name
                if import_module:
                    imports[bound_name] = f"{import_module}.{alias.name}"
                else:
                    imports[bound_name] = alias.name
            continue

        if not isinstance(statement, ast.ClassDef):
            continue

        route_name: str | None = None
        inject_parent_expr: ast.expr | None = None
        is_root = False
        for decorator in statement.decorator_list:
            if isinstance(decorator, ast.Call):
                leaf_name = _decorator_leaf_name(decorator.func)
                if (
                    leaf_name == "route"
                    and decorator.args
                    and isinstance(decorator.args[0], ast.Constant)
                    and isinstance(decorator.args[0].value, str)
                ):
                    route_name = decorator.args[0].value
                elif leaf_name == "inject_to" and decorator.args:
                    inject_parent_expr = decorator.args[0]
                continue

            if _decorator_leaf_name(decorator) == "root":
                is_root = True

        classes[statement.name] = _NodeClass(
            name=statement.name,
            module=module_name,
            source_path=source_path,
            route_name=route_name,
            inject_parent_expr=inject_parent_expr,
            is_root=is_root,
        )

    return _ModuleInfo(
        module_name=module_name,
        source_path=source_path,
        imports=imports,
        classes=classes,
    )


def _resolve_symbol(expr: ast.expr, module_info: _ModuleInfo) -> str | None:
    if isinstance(expr, ast.Name):
        if expr.id in module_info.classes:
            return _qualify(module_info.module_name, expr.id)
        return module_info.imports.get(expr.id)

    if isinstance(expr, ast.Attribute):
        base = _resolve_symbol(expr.value, module_info)
        if base is None:
            return None
        return f"{base}.{expr.attr}"

    return None


def _collect_parent_children(root_path: Path) -> SourceMap:
    module_infos = [
        _parse_module(root_path, path) for path in _iter_python_sources(root_path)
    ]

    classes_by_symbol: dict[str, _NodeClass] = {}
    for module_info in module_infos:
        for node_class in module_info.classes.values():
            classes_by_symbol[_qualify(node_class.module, node_class.name)] = node_class

    by_source: SourceMap = {}
    for module_info in module_infos:
        for node_class in module_info.classes.values():
            if node_class.inject_parent_expr is None or node_class.route_name is None:
                continue

            parent_symbol = _resolve_symbol(node_class.inject_parent_expr, module_info)
            if parent_symbol is None:
                continue

            parent_class = classes_by_symbol.get(parent_symbol)
            if parent_class is None:
                continue

            source_parents = by_source.setdefault(parent_class.source_path, {})
            parent_spec = ParentSpec(name=parent_class.name, module=parent_class.module)
            child_spec = ChildSpec(
                route_name=node_class.route_name,
                child_name=node_class.name,
                child_module=node_class.module,
            )
            child_specs = source_parents.setdefault(parent_spec, [])
            if child_spec not in child_specs:
                child_specs.append(child_spec)

    return by_source


def _local_leaf_names(parent_map: ParentMap, current_module: str | None) -> list[str]:
    declared_parent_names = {parent.name for parent in parent_map}
    leaf_names = {
        child.child_name
        for child_specs in parent_map.values()
        for child in child_specs
        if child.child_module == current_module
        and child.child_name not in declared_parent_names
    }
    return sorted(leaf_names)


def render_stub_content(source_path: Path, parent_map: ParentMap) -> str:
    del source_path

    current_module = next(iter({parent.module for parent in parent_map}), None)
    imports: dict[str, set[str]] = {}
    for child_specs in parent_map.values():
        for child in child_specs:
            if child.child_module == current_module:
                continue
            imports.setdefault(child.child_module, set()).add(child.child_name)

    lines: list[str] = ["from __future__ import annotations", ""]
    for module_name in sorted(imports):
        names = ", ".join(sorted(imports[module_name]))
        lines.append(f"from {module_name} import {names}")

    if imports:
        lines.append("")

    for parent in sorted(parent_map):
        lines.append(f"class {parent.name}:")
        for child in sorted(parent_map[parent]):
            lines.append(f"    {child.route_name}: {child.child_name}")
        lines.append("")

    for leaf_name in _local_leaf_names(parent_map, current_module):
        lines.append(f"class {leaf_name}:")
        lines.append("    ...")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def generate_stub_files(project_path: Path) -> list[Path]:
    parent_children_by_source = _collect_parent_children(project_path.resolve())

    generated_files: list[Path] = []
    for source_path in sorted(parent_children_by_source):
        stub_path = source_path.with_suffix(".pyi")
        content = render_stub_content(
            source_path, parent_children_by_source[source_path]
        )
        _ = stub_path.write_text(content, encoding="utf-8")
        generated_files.append(stub_path)

    return generated_files
