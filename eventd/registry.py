"""Registry table for listener management.

This module provides RegistryTable for storing and querying listeners,
with topological sorting and execution plan caching using NetworkX.
"""

from collections import defaultdict

import networkx as nx

from eventd.event import Event
from eventd.exceptions import CyclicDependencyError


class BaseRegistry[CB]:
    """Registry table for event listeners.

    Manages listener registration, removal, and execution order resolution
    with MRO expansion, priority layering, and topological sorting using NetworkX.

    Each event type has its own dependency graph for callback relationships.
    _graphs maps event types to their dependency graphs.
    """

    def __init__(self, guardian: CB) -> None:
        """Initialize empty registry.

        Post:
            _graphs is empty dict mapping event types to DiGraphs.
        """
        self._guardian = guardian
        self._graphs: defaultdict[type[Event], nx.DiGraph[CB]] = defaultdict(nx.DiGraph)

    def add(
        self,
        event_types: list[type[Event]],
        callback: CB,
        after: list[CB] | None = None,
    ) -> None:
        """Register a listener for specified event types.

        Args:
            event_types: Event types to register for.
            callback: Listener callback function.
            after: List of callbacks that should run before this one.

        Post:
            callback added to each event type's graph.
            dependency edges added to each graph.

        Raises:
            ValueError: If entry.after references unregistered callbacks.
            CyclicDependencyError: If entry.after forms a cycle.
        """
        # Add the entry for each event type
        for event_type in event_types:
            # defaultdict ensures graph exists for event_type
            graph = self._graphs[event_type]

            # Ensure the guardian node exists
            # Note that add_node is idempotent
            graph.add_node(self._guardian)

            # Check that all 'after' dependencies exist
            for dep in after or []:
                if dep not in graph:
                    raise ValueError(
                        f"after={dep.__qualname__} not registered for event type "
                        f"{event_type.__qualname__}"
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
                    f"would create a cycle in {event_type.__qualname__}"
                    f" - cycles: {cycles}"
                )

    def remove(
        self,
        event_types: list[type[Event]] | None,
        callback: CB | None,
    ) -> None:
        """Remove listeners from registry.

        Supports three modes:
        - (event_types, callback): Remove callback from specified event types.
        - (event_types, None): Remove all listeners from specified event types.
        - (None, callback): Remove callback from all event types.

        Args:
            event_types: Event types to remove from, or None for all.
            callback: Callback to remove, or None for all.

        Post:
            Matching entries removed from event graphs.
            Corresponding nodes/edges removed if no longer referenced.

        Raises:
            ValueError: If both args are None.
        """
        # Validate parameters
        if event_types is None and callback is None:
            raise ValueError("event_types and callback cannot both be None")

        # If specific event requested
        if event_types is not None:
            for event_type in event_types:
                # Get the graph for this event (skip if not exists)
                if event_type not in self._graphs:
                    continue

                graph = self._graphs[event_type]

                # If func requested, only remove the func node
                if callback is not None:
                    if callback in graph:
                        graph.remove_node(callback)
                        # Clean up empty graph
                        if len(graph) == 0:
                            del self._graphs[event_type]
                else:
                    # If no func requested, delete the event key
                    del self._graphs[event_type]

        # If specific func requested and event not requested
        elif callback is not None:
            # Search for all graphs of all events for func node and remove it
            events_to_clean = []
            for event_type, graph in self._graphs.items():
                if callback in graph:
                    graph.remove_node(callback)
                    # Mark for cleanup if empty
                    if len(graph) == 0:
                        events_to_clean.append(event_type)

            # Clean up empty graphs
            for event_type in events_to_clean:
                del self._graphs[event_type]

    def exec_order(self, event_type: type[Event]) -> list[list[CB]]:
        """Return execution order for an event type using breadth-first enumeration.

        Performs a breadth-first traversal of the dependency graph for the event type
        and returns a 2D list of callbacks in layers of execution order.

        Args:
            event_type: Event type to resolve.

        Returns:
            2D list of callbacks in layers of execution order (dependencies before dependents).
        """
        # Get the graph for the event type
        if event_type not in self._graphs:
            return []

        graph = self._graphs[event_type]
        return list(nx.bfs_layers(graph, sources=[self._guardian]))[
            1:
        ]  # Exclude guardian layer
