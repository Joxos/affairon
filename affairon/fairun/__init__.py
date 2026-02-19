"""fairun — CLI runner for affairon applications.

Reads ``[tool.affairon]`` from a project's ``pyproject.toml``,
composes external and local plugins, then emits :class:`AffairMain`
on the default dispatcher to start the application.

Usage::

    fairun /path/to/project
"""
