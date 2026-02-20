"""Registry for listener management.

This module provides BaseRegistry for storing and querying listeners,
with topological sorting and execution plan layering using NetworkX.
"""

from collections import defaultdict

import networkx as nx

from affairon.affairs import MutableAffair
from affairon.exceptions import CyclicDependencyError


class BaseRegistry[CB]:
    """Registry table for affair listeners.

    Manages listener registration, removal, and execution order resolution
    with priority layering and topological sorting using NetworkX.

    Each affair type has its own dependency graph for callback relationships.
    Only callbacks explicitly registered for a given affair type are included;
    parent affair type callbacks are NOT inherited (no MRO expansion).
    """

    def __init__(self, guardian: CB) -> None:
        """Initialize empty registry.

        Post:
            _graphs is empty dict mapping affair types to DiGraphs.
        """
        self._guardian = guardian
        self._graphs: defaultdict[type[MutableAffair], nx.DiGraph[CB]] = defaultdict(
            nx.DiGraph
        )

    def add(
        self,
        affair_types: list[type[MutableAffair]],
        callback: CB,
        after: list[CB] | None = None,
    ) -> None:
        """Register a listener for specified affair types.

        Args:
            affair_types: MutableAffair types to register for.
            callback: Listener callback function.
            after: List of callbacks that should run before this one.

        Post:
            callback added to each affair type's graph.
            dependency edges added to each graph.

        Raises:
            ValueError: If entry.after references unregistered callbacks.
            CyclicDependencyError: If entry.after forms a cycle.
        """
        # Add the entry for each affair type
        for affair_type in affair_types:
            # defaultdict ensures graph exists for affair_type
            graph = self._graphs[affair_type]

            # Ensure the guardian node exists
            # Note that add_node is idempotent
            graph.add_node(self._guardian)

            # Check that all 'after' dependencies exist
            for dep in after or []:
                if dep not in graph:
                    raise ValueError(
                        f"after={dep.__qualname__} not registered for affair type "
                        f"{affair_type.__qualname__}"
                    )

            graph.add_node(callback)

            # Add dependency edges (dep -> callback means dep executes before callback)
            for dep in after or [self._guardian]:
                graph.add_edge(dep, callback)

            # Check for cycles
            if cycles := list(nx.simple_cycles(graph)):
                # Rollback: remove entry
                # Note that removing the node will also remove all its edges
                graph.remove_node(callback)

                raise CyclicDependencyError(
                    f"cyclic dependency detected: adding {callback.__qualname__} "
                    f"would create a cycle in {affair_type.__qualname__}"
                    f" - cycles: {cycles}"
                )

    def remove(
        self,
        affair_types: list[type[MutableAffair]] | None,
        callback: CB | None,
    ) -> None:
        """Remove listeners from registry.

        Supports three modes:
        - (affair_types, callback): Remove callback from specified affair types.
        - (affair_types, None): Remove all listeners from specified affair types.
        - (None, callback): Remove callback from all affair types.

        Args:
            affair_types: MutableAffair types to remove from, or None for all.
            callback: Callback to remove, or None for all.

        Post:
            Matching entries removed from affair graphs.
            Corresponding nodes/edges removed if no longer referenced.

        Raises:
            ValueError: If both args are None.
        """
        # Validate parameters
        if affair_types is None and callback is None:
            raise ValueError("affair_types and callback cannot both be None")

        # If specific affair requested
        if affair_types is not None:
            for affair_type in affair_types:
                # Get the graph for this affair (skip if not exists)
                if affair_type not in self._graphs:
                    continue

                graph = self._graphs[affair_type]

                # If func requested, only remove the func node
                if callback is not None:
                    if callback in graph:
                        graph.remove_node(callback)
                        # Clean up empty graph
                        if len(graph) == 0:
                            del self._graphs[affair_type]
                else:
                    # If no func requested, delete the affair key
                    del self._graphs[affair_type]

        # If specific func requested and affair not requested
        elif callback is not None:
            # Search for all graphs of all affairs for func node and remove it
            affairs_to_clean = []
            for affair_type, graph in self._graphs.items():
                if callback in graph:
                    graph.remove_node(callback)
                    # Mark for cleanup if empty
                    if len(graph) == 0:
                        affairs_to_clean.append(affair_type)

            # Clean up empty graphs
            for affair_type in affairs_to_clean:
                del self._graphs[affair_type]

    def exec_order(self, affair_type: type[MutableAffair]) -> list[list[CB]]:
        """Return execution order for an affair type using breadth-first enumeration.

        Performs a breadth-first traversal of the dependency graph for the affair type
        and returns a 2D list of callbacks in layers of execution order.

        Args:
            affair_type: MutableAffair type to resolve.

        Returns:
            2D list of callbacks in layers of execution order (dependencies before dependents).
        """
        # Get the graph for the affair type
        if affair_type not in self._graphs:
            return []

        graph = self._graphs[affair_type]
        return list(nx.bfs_layers(graph, sources=[self._guardian]))[
            1:
        ]  # Exclude guardian layer
