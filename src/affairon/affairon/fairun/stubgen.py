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


@dataclass(frozen=True)
class _AttributeSpec:
    name: str
    annotation_str: str | None


@dataclass(frozen=True)
class _MethodSpec:
    name: str
    params: list[tuple[str, str | None, bool]]
    return_annotation: str | None
    is_static: bool
    is_classmethod: bool
    is_associate: bool
    decorators: tuple[str, ...]


@dataclass(frozen=True)
class _FunctionSpec:
    name: str
    params: list[tuple[str, str | None, bool]]
    return_annotation: str | None


@dataclass(frozen=True)
class _ClassStubInfo:
    name: str
    bases: list[str]
    attrs: list[_AttributeSpec]
    methods: list[_MethodSpec]


@dataclass(frozen=True)
class _ModuleStubInfo:
    module_name: str
    source_path: Path
    classes: list[_ClassStubInfo]
    functions: list[_FunctionSpec]
    module_vars: list[_AttributeSpec]
    imports_needed: dict[str, set[str]]


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


def _annotation_str(expr: ast.expr | None) -> str | None:
    if expr is None:
        return None
    return ast.unparse(expr)


def _constant_annotation(expr: ast.expr) -> str | None:
    if not isinstance(expr, ast.Constant):
        return None
    value = expr.value
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, complex):
        return "complex"
    if isinstance(value, str):
        return "str"
    if isinstance(value, bytes):
        return "bytes"
    return None


def _contains_root_or_parent(expr: ast.expr) -> bool:
    if isinstance(expr, ast.Name) and expr.id in {"Root", "Parent"}:
        return True
    return any(
        _contains_root_or_parent(node)
        for node in ast.iter_child_nodes(expr)
        if isinstance(node, ast.expr)
    )


def _contains_injection_locator(expr: ast.expr) -> bool:
    if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Div):
        if _contains_root_or_parent(expr.left) or _contains_root_or_parent(expr.right):
            return True
    return any(
        _contains_injection_locator(node)
        for node in ast.iter_child_nodes(expr)
        if isinstance(node, ast.expr)
    )


def _is_injected_annotation(annotation: ast.expr | None) -> bool:
    if not isinstance(annotation, ast.Subscript):
        return False
    if not (
        isinstance(annotation.value, ast.Name) and annotation.value.id == "Annotated"
    ):
        return False
    slice_expr = annotation.slice
    if isinstance(slice_expr, ast.Tuple):
        parts = list(slice_expr.elts)
    else:
        parts = [slice_expr]
    if len(parts) < 2:
        return False
    for locator_expr in parts[1:]:
        if _contains_injection_locator(locator_expr):
            return True
    return False


def _extract_params(
    fn: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    drop_injected: bool,
) -> list[tuple[str, str | None, bool]]:
    params: list[tuple[str, str | None, bool]] = []

    all_positional = fn.args.posonlyargs + fn.args.args
    num_positional = len(all_positional)
    num_defaults = len(fn.args.defaults)
    default_offset = num_positional - num_defaults

    for i, arg in enumerate(all_positional):
        if drop_injected and _is_injected_annotation(arg.annotation):
            continue
        has_default = i >= default_offset
        params.append((arg.arg, _annotation_str(arg.annotation), has_default))

    if fn.args.vararg is not None:
        if not (drop_injected and _is_injected_annotation(fn.args.vararg.annotation)):
            params.append(
                (
                    f"*{fn.args.vararg.arg}",
                    _annotation_str(fn.args.vararg.annotation),
                    False,
                )
            )
    elif fn.args.kwonlyargs:
        params.append(("*", None, False))

    for j, arg in enumerate(fn.args.kwonlyargs):
        if drop_injected and _is_injected_annotation(arg.annotation):
            continue
        kw_default = fn.args.kw_defaults[j] if j < len(fn.args.kw_defaults) else None
        has_default = kw_default is not None
        params.append((arg.arg, _annotation_str(arg.annotation), has_default))

    if fn.args.kwarg is not None:
        if not (drop_injected and _is_injected_annotation(fn.args.kwarg.annotation)):
            params.append(
                (
                    f"**{fn.args.kwarg.arg}",
                    _annotation_str(fn.args.kwarg.annotation),
                    False,
                )
            )

    return params


def _extract_attribute_from_assign(
    statement: ast.stmt,
) -> tuple[str, str | None] | None:
    if isinstance(statement, ast.AnnAssign):
        target = statement.target
        if (
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == "self"
        ):
            return target.attr, _annotation_str(statement.annotation)
    if isinstance(statement, ast.Assign):
        if len(statement.targets) != 1:
            return None
        target = statement.targets[0]
        if (
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == "self"
        ):
            return target.attr, _constant_annotation(statement.value)
    return None


def _collect_init_attrs(
    init_method: ast.FunctionDef | ast.AsyncFunctionDef,
    class_attr_annotations: dict[str, str],
) -> dict[str, str | None]:
    attrs: dict[str, str | None] = {}
    for statement in ast.walk(init_method):
        if not isinstance(statement, ast.stmt):
            continue
        extracted = _extract_attribute_from_assign(statement)
        if extracted is None:
            continue
        attr_name, inferred = extracted
        annotation = class_attr_annotations.get(attr_name, inferred)
        if attr_name not in attrs or (
            attrs[attr_name] is None and annotation is not None
        ):
            attrs[attr_name] = annotation
    return attrs


def _extract_method_spec(method: ast.FunctionDef | ast.AsyncFunctionDef) -> _MethodSpec:
    decorator_names_set: set[str] = set()
    for decorator in method.decorator_list:
        name = (
            _decorator_leaf_name(decorator.func)
            if isinstance(decorator, ast.Call)
            else _decorator_leaf_name(decorator)
        )
        if name is not None:
            decorator_names_set.add(name)

    decorator_names = tuple(sorted(decorator_names_set))
    is_static = "staticmethod" in decorator_names
    is_classmethod = "classmethod" in decorator_names
    is_associate = "associate" in decorator_names
    params = _extract_params(method, drop_injected=is_associate)
    return _MethodSpec(
        name=method.name,
        params=params,
        return_annotation=_annotation_str(method.returns),
        is_static=is_static,
        is_classmethod=is_classmethod,
        is_associate=is_associate,
        decorators=decorator_names,
    )


def _extract_class_info(class_def: ast.ClassDef) -> _ClassStubInfo:
    bases = [ast.unparse(base) for base in class_def.bases]

    class_attr_annotations: dict[str, str] = {}
    attrs: dict[str, str | None] = {}
    methods: list[_MethodSpec] = []

    init_method: ast.FunctionDef | ast.AsyncFunctionDef | None = None

    for statement in class_def.body:
        if isinstance(statement, ast.AnnAssign) and isinstance(
            statement.target, ast.Name
        ):
            annotation = _annotation_str(statement.annotation)
            if annotation is not None:
                class_attr_annotations[statement.target.id] = annotation
                attrs[statement.target.id] = annotation
            continue

        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            methods.append(_extract_method_spec(statement))
            if statement.name == "__init__":
                init_method = statement

    if init_method is not None:
        init_attrs = _collect_init_attrs(init_method, class_attr_annotations)
        for attr_name, annotation in init_attrs.items():
            if attr_name in attrs and attrs[attr_name] is not None:
                continue
            attrs[attr_name] = annotation

    attr_specs = [
        _AttributeSpec(name=name, annotation_str=attrs[name]) for name in sorted(attrs)
    ]
    return _ClassStubInfo(
        name=class_def.name,
        bases=bases,
        attrs=attr_specs,
        methods=sorted(methods, key=lambda spec: spec.name),
    )


def _extract_function_spec(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> _FunctionSpec:
    return _FunctionSpec(
        name=fn.name,
        params=_extract_params(fn, drop_injected=False),
        return_annotation=_annotation_str(fn.returns),
    )


def _build_import_aliases(
    module_name: str,
    source_path: Path,
    tree: ast.Module,
) -> dict[str, str]:
    imports: dict[str, str] = {}
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
    return imports


def _extract_symbol_names(type_expr: str) -> set[str]:
    try:
        expr = ast.parse(type_expr, mode="eval").body
    except SyntaxError:
        return set()

    names: set[str] = set()
    for node in ast.walk(expr):
        if isinstance(node, ast.Name):
            names.add(node.id)
    return names


def _collect_imports_needed(
    module_name: str,
    source_path: Path,
    classes: list[_ClassStubInfo],
    functions: list[_FunctionSpec],
    module_vars: list[_AttributeSpec],
    import_aliases: dict[str, str],
) -> dict[str, set[str]]:
    local_names = (
        {class_info.name for class_info in classes}
        | {function.name for function in functions}
        | {module_var.name for module_var in module_vars}
    )

    referenced_names: set[str] = set()
    for class_info in classes:
        for base in class_info.bases:
            referenced_names.update(_extract_symbol_names(base))
        for attr in class_info.attrs:
            if attr.annotation_str is not None:
                referenced_names.update(_extract_symbol_names(attr.annotation_str))
        for method in class_info.methods:
            for _, annotation, _ in method.params:
                if annotation is not None:
                    referenced_names.update(_extract_symbol_names(annotation))
            if method.return_annotation is not None:
                referenced_names.update(_extract_symbol_names(method.return_annotation))

    for function in functions:
        for _, annotation, _ in function.params:
            if annotation is not None:
                referenced_names.update(_extract_symbol_names(annotation))
        if function.return_annotation is not None:
            referenced_names.update(_extract_symbol_names(function.return_annotation))

    for module_var in module_vars:
        if module_var.annotation_str is not None:
            referenced_names.update(_extract_symbol_names(module_var.annotation_str))

    imports_needed: dict[str, set[str]] = {}
    for name in sorted(referenced_names):
        if name in local_names:
            continue
        full_symbol = import_aliases.get(name)
        if not full_symbol or "." not in full_symbol:
            continue
        import_module, symbol_name = full_symbol.rsplit(".", 1)
        if import_module == "typing" and symbol_name == "Annotated":
            continue
        if import_module == module_name:
            continue
        if import_module.startswith("affairon"):
            imports_needed.setdefault("affairon", set()).add(symbol_name)
            continue
        if _package_name(module_name, source_path) == _package_name(
            import_module, Path("x.py")
        ):
            imports_needed.setdefault(import_module, set()).add(symbol_name)
            continue
        imports_needed.setdefault(import_module, set()).add(symbol_name)

    return imports_needed


def _is_empty_init(source_path: Path) -> bool:
    if source_path.name != "__init__.py":
        return False
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    for statement in tree.body:
        if isinstance(statement, ast.Expr) and isinstance(
            statement.value, ast.Constant
        ):
            if isinstance(statement.value.value, str):
                continue
        if isinstance(statement, ast.Pass):
            continue
        return False
    return True


def _parse_module_full(root_path: Path, source_path: Path) -> _ModuleStubInfo:
    module_name = _module_name_for_path(root_path, source_path)
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    import_aliases = _build_import_aliases(module_name, source_path, tree)

    classes: list[_ClassStubInfo] = []
    functions: list[_FunctionSpec] = []
    module_vars: list[_AttributeSpec] = []

    for statement in tree.body:
        if isinstance(statement, ast.ClassDef):
            classes.append(_extract_class_info(statement))
            continue

        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(_extract_function_spec(statement))
            continue

        if isinstance(statement, ast.AnnAssign) and isinstance(
            statement.target, ast.Name
        ):
            module_vars.append(
                _AttributeSpec(
                    name=statement.target.id,
                    annotation_str=_annotation_str(statement.annotation),
                )
            )

    classes = sorted(classes, key=lambda cls: cls.name)
    functions = sorted(functions, key=lambda fn: fn.name)
    module_vars = sorted(module_vars, key=lambda var: var.name)
    imports_needed = _collect_imports_needed(
        module_name,
        source_path,
        classes,
        functions,
        module_vars,
        import_aliases,
    )
    return _ModuleStubInfo(
        module_name=module_name,
        source_path=source_path,
        classes=classes,
        functions=functions,
        module_vars=module_vars,
        imports_needed=imports_needed,
    )


def _render_params(params: list[tuple[str, str | None, bool]]) -> str:
    rendered: list[str] = []
    for name, annotation, has_default in params:
        if name == "*":
            rendered.append("*")
            continue
        suffix = " = ..." if has_default else ""
        if annotation is None:
            rendered.append(f"{name}{suffix}")
        else:
            rendered.append(f"{name}: {annotation}{suffix}")
    return ", ".join(rendered)


def _render_method(method: _MethodSpec) -> str:
    rendered_params = _render_params(method.params)
    if method.return_annotation is None:
        return f"def {method.name}({rendered_params}): ..."
    return f"def {method.name}({rendered_params}) -> {method.return_annotation}: ..."


def _render_function(function: _FunctionSpec) -> str:
    rendered_params = _render_params(function.params)
    if function.return_annotation is None:
        return f"def {function.name}({rendered_params}): ..."
    return (
        f"def {function.name}({rendered_params}) -> {function.return_annotation}: ..."
    )


def _is_trivial_init(method: _MethodSpec) -> bool:
    if method.name != "__init__":
        return False
    non_self_params = [
        (name, ann, has_def) for name, ann, has_def in method.params if name != "self"
    ]
    if non_self_params:
        return False
    return method.return_annotation in (None, "None")


def _render_full_stub(
    source_path: Path,
    module_stub_info: _ModuleStubInfo,
    parent_map_for_source: ParentMap,
) -> str:
    del source_path

    merged_attrs: dict[str, dict[str, str | None]] = {}
    for class_info in module_stub_info.classes:
        merged_attrs[class_info.name] = {
            attr.name: attr.annotation_str for attr in class_info.attrs
        }

    child_imports: dict[str, set[str]] = {}
    for parent_spec, child_specs in parent_map_for_source.items():
        parent_attrs = merged_attrs.setdefault(parent_spec.name, {})
        for child in child_specs:
            parent_attrs[child.route_name] = child.child_name
            if child.child_module != module_stub_info.module_name:
                child_imports.setdefault(child.child_module, set()).add(
                    child.child_name
                )

    imports = {
        module_name: set(names)
        for module_name, names in module_stub_info.imports_needed.items()
    }
    for module_name, names in child_imports.items():
        imports.setdefault(module_name, set()).update(names)

    lines: list[str] = ["from __future__ import annotations"]

    import_lines: list[str] = []
    for module_name in sorted(imports):
        names = ", ".join(sorted(imports[module_name]))
        import_lines.append(f"from {module_name} import {names}")

    if import_lines:
        lines.append("")
        lines.extend(import_lines)

    body_lines: list[str] = []
    for module_var in module_stub_info.module_vars:
        if module_var.annotation_str is None:
            continue
        body_lines.append(f"{module_var.name}: {module_var.annotation_str}")

    for class_info in module_stub_info.classes:
        base_segment = f"({', '.join(class_info.bases)})" if class_info.bases else ""
        body_lines.append("")
        body_lines.append(f"class {class_info.name}{base_segment}:")

        class_body: list[str] = []
        attrs = merged_attrs.get(class_info.name, {})
        for attr_name in sorted(attrs):
            annotation = attrs[attr_name]
            if annotation is None:
                continue
            class_body.append(f"    {attr_name}: {annotation}")

        for method in class_info.methods:
            if method.name == "__init__" and _is_trivial_init(method):
                continue
            class_body.append(f"    {_render_method(method)}")

        if not class_body:
            class_body.append("    ...")

        body_lines.extend(class_body)

    for function in module_stub_info.functions:
        body_lines.append("")
        body_lines.append(_render_function(function))

    if body_lines:
        lines.append("")
        lines.extend(body_lines)

    return "\n".join(lines).rstrip() + "\n"


def _is_legacy_dynamic_only_module(
    module_stub: _ModuleStubInfo,
    parent_map_for_source: ParentMap,
) -> bool:
    if not parent_map_for_source:
        return False
    if module_stub.functions or module_stub.module_vars:
        return False
    return all(
        not class_info.attrs and not class_info.methods
        for class_info in module_stub.classes
    )


def generate_stub_files(project_path: Path) -> list[Path]:
    root_path = project_path.resolve()
    parent_children_by_source = _collect_parent_children(root_path)
    sources = _iter_python_sources(root_path)

    generated_files: list[Path] = []
    for source_path in sources:
        if _is_empty_init(source_path):
            continue

        module_stub = _parse_module_full(root_path, source_path)
        parent_map = parent_children_by_source.get(source_path, {})

        if (
            not module_stub.classes
            and not module_stub.functions
            and not module_stub.module_vars
            and not parent_map
        ):
            continue

        stub_path = source_path.with_suffix(".pyi")
        if _is_legacy_dynamic_only_module(module_stub, parent_map):
            content = render_stub_content(source_path, parent_map)
        else:
            content = _render_full_stub(source_path, module_stub, parent_map)
        _ = stub_path.write_text(content, encoding="utf-8")
        generated_files.append(stub_path)

    return generated_files
