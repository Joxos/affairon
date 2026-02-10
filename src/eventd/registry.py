"""Registry table for listener management.

This module provides RegistryTable for storing and querying listeners,
with topological sorting and execution plan caching.
"""

import weakref
from dataclasses import dataclass, field
from graphlib import CycleError, TopologicalSorter

from eventd._types import ListenerCallback
from eventd.event import Event
from eventd.exceptions import CyclicDependencyError


@dataclass
class ListenerEntry:
    """Listener entry with metadata.

    Attributes:
        callback: Listener callback function.
        priority: Priority value (higher = executed first).
        after: List of callbacks that must execute before this one.
        name: Debug label for logging (defaults to callback.__qualname__).
    """

    callback: ListenerCallback
    priority: int
    after: list[ListenerCallback] = field(default_factory=list)
    name: str = field(default="")

    def __post_init__(self) -> None:
        """Set default name if not provided."""
        if not self.name:
            object.__setattr__(self, "name", self.callback.__qualname__)


class RegistryTable:
    """Registry table for event listeners.

    Manages listener registration, removal, and execution order resolution
    with MRO expansion, priority layering, and topological sorting.

    Internal caching (via _revision and _plan_cache) ensures resolve_order()
    is O(1) when no registration changes occur.
    """

    def __init__(self) -> None:
        """Initialize empty registry.

        Post:
            _store is empty, _revision == 0, _plan_cache is empty.
        """
        self._store: dict[type[Event], list[ListenerEntry]] = {}
        self._callback_events: dict[ListenerCallback, set[type[Event]]] = {}
        self._revision: int = 0
        self._plan_cache: weakref.WeakKeyDictionary[
            type[Event], tuple[int, list[list[ListenerEntry]]]
        ] = weakref.WeakKeyDictionary()

    def add(
        self,
        event_types: list[type[Event]],
        entry: ListenerEntry,
    ) -> None:
        """Register a listener for specified event types.

        Args:
            event_types: Event types to register for.
            entry: Listener entry with callback and metadata.

        Post:
            entry added to each event type's listener list.
            _revision incremented.

        Raises:
            ValueError: If entry.after references unregistered callbacks.
            CyclicDependencyError: If entry.after forms a cycle.
        """
        # 1. Check after references are registered
        for dep in entry.after:
            if dep not in self._callback_events:
                raise ValueError(
                    f"after references unregistered callback: {dep.__qualname__}"
                )

        # 2. Check for cyclic dependencies
        self._check_cycle(entry)

        # 3. Add to store
        for event_type in event_types:
            if event_type not in self._store:
                self._store[event_type] = []
            self._store[event_type].append(entry)

        # 4. Update reverse index
        if entry.callback not in self._callback_events:
            self._callback_events[entry.callback] = set()
        self._callback_events[entry.callback].update(event_types)

        # 5. Increment revision (invalidate cache)
        self._revision += 1

    def remove(
        self,
        event_types: list[type[Event]] | None,
        callback: ListenerCallback | None,
    ) -> None:
        """Remove listeners from registry.

        Supports four modes:
        - (event_types, callback): Remove callback from specified event types.
        - (event_types, None): Remove all listeners from specified event types.
        - (None, callback): Remove callback from all event types.
        - (None, None): ValueError.

        Args:
            event_types: Event types to remove from, or None for all.
            callback: Callback to remove, or None for all.

        Post:
            Matching entries removed.
            _revision incremented.

        Raises:
            ValueError: If both args are None, or callback not registered,
                        or removal breaks other listeners' after dependencies.
        """
        # 1. Validate parameters
        if event_types is None and callback is None:
            raise ValueError("event_types and callback cannot both be None")

        # 2. Determine targets to remove
        targets: list[tuple[type[Event], ListenerCallback]] = []
        if event_types is not None and callback is not None:
            # Mode 1: Remove specific callback from specific event types
            # Validate callback is registered
            if callback not in self._callback_events:
                raise ValueError(f"callback not registered: {callback.__qualname__}")
            targets = [(et, callback) for et in event_types]
        elif event_types is not None:
            # Mode 2: Remove all callbacks from specific event types
            targets = [
                (et, e.callback) for et in event_types for e in self._store.get(et, [])
            ]
        else:
            # Mode 3: Remove specific callback from all event types
            if callback is None or callback not in self._callback_events:
                qualname = callback.__qualname__ if callback else "None"
                raise ValueError(f"callback not registered: {qualname}")
            targets = [(et, callback) for et in self._callback_events[callback]]

        # 3. Check for broken dependencies
        callbacks_to_remove = {cb for _, cb in targets}
        for entries in self._store.values():
            for entry in entries:
                if entry.callback not in callbacks_to_remove:
                    # This entry is not being removed
                    deps_broken = set(entry.after) & callbacks_to_remove
                    if deps_broken:
                        names = [d.__qualname__ for d in deps_broken]
                        raise ValueError(
                            f"cannot remove: {names} depended on by {entry.name}"
                        )

        # 4. Execute removal
        for et, cb in targets:
            if et in self._store:
                self._store[et] = [e for e in self._store[et] if e.callback != cb]
                if not self._store[et]:
                    del self._store[et]

        # 5. Update reverse index
        callbacks_updated = set()
        for _et, cb in targets:
            if cb not in callbacks_updated:
                callbacks_updated.add(cb)
                if cb in self._callback_events:
                    event_types_for_cb = [t[0] for t in targets if t[1] == cb]
                    for event_type in event_types_for_cb:
                        self._callback_events[cb].discard(event_type)
                    if not self._callback_events[cb]:
                        del self._callback_events[cb]

        # 6. Increment revision (invalidate cache)
        self._revision += 1

    def resolve_order(self, event_type: type[Event]) -> list[list[ListenerEntry]]:
        """Resolve execution order for an event type.

        Returns a 2D list: outer = priority layers (high to low),
        inner = topologically sorted by after dependencies.

        Uses cache when possible (_plan_cache with _revision check).

        Args:
            event_type: Event type to resolve.

        Returns:
            2D list of listener entries.

        Post:
            Returns cached plan if _revision unchanged, otherwise rebuilds.
            All listeners matched via MRO are included (not deduplicated).

        Raises:
            CyclicDependencyError: If after dependencies form a cycle.
        """
        # 0. Check cache
        if event_type in self._plan_cache:
            cached_revision, cached_plan = self._plan_cache[event_type]
            if cached_revision == self._revision:
                return cached_plan

        # 1. MRO expansion - collect listeners from all base classes
        all_entries: list[ListenerEntry] = []
        for base in event_type.__mro__:
            # Skip object and non-Event types
            if base is object:
                continue
            # Check if it's an Event subclass
            try:
                if not issubclass(base, Event):
                    continue
            except TypeError:
                # Not a class, skip
                continue
            if base in self._store:
                all_entries.extend(self._store[base])

        # Empty registry case
        if not all_entries:
            plan: list[list[ListenerEntry]] = []
            self._plan_cache[event_type] = (self._revision, plan)
            return plan

        # 3. Group by priority (high to low)
        priority_groups: dict[int, list[ListenerEntry]] = {}
        for entry in all_entries:
            if entry.priority not in priority_groups:
                priority_groups[entry.priority] = []
            priority_groups[entry.priority].append(entry)

        # Sort priorities high to low
        sorted_priorities = sorted(priority_groups.keys(), reverse=True)

        # 4. Topological sort within each group
        plan = []
        for priority in sorted_priorities:
            group = priority_groups[priority]
            sorted_group = self._topological_sort(group)
            plan.append(sorted_group)

        # 5. Write to cache
        self._plan_cache[event_type] = (self._revision, plan)

        # 6. Return plan
        return plan

    def _check_cycle(self, new_entry: ListenerEntry) -> None:
        """Check if new_entry creates a cycle via after dependencies.

        Args:
            new_entry: Entry to check for cycles.

        Raises:
            CyclicDependencyError: If adding new_entry would create a cycle.
        """
        visited: set[ListenerCallback] = set()

        def dfs(callback: ListenerCallback) -> bool:
            """DFS to detect if path from callback leads back to new_entry."""
            if callback == new_entry.callback:
                return True  # Found cycle
            if callback in visited:
                return False
            visited.add(callback)

            # Find all entries with this callback and check their after deps
            for entries in self._store.values():
                for entry in entries:
                    if entry.callback == callback:
                        for dep in entry.after:
                            if dfs(dep):
                                return True
                        break  # Same callback has same after list
            return False

        # Check each dependency
        for dep in new_entry.after:
            if dfs(dep):
                msg = (
                    f"cyclic dependency detected: "
                    f"{new_entry.name} -> ... -> {new_entry.name}"
                )
                raise CyclicDependencyError(msg)

    def _topological_sort(self, entries: list[ListenerEntry]) -> list[ListenerEntry]:
        """Topologically sort entries by after dependencies using graphlib.

        Args:
            entries: Entries to sort (same priority group).

        Returns:
            Topologically sorted list of entries.

        Raises:
            CyclicDependencyError: If after dependencies form a cycle.
        """
        # Build callback -> list of entry indices mapping (handles duplicates)
        callback_to_indices: dict[ListenerCallback, list[int]] = {}
        for idx, entry in enumerate(entries):
            if entry.callback not in callback_to_indices:
                callback_to_indices[entry.callback] = []
            callback_to_indices[entry.callback].append(idx)

        # Build TopologicalSorter using entry indices as nodes
        ts: TopologicalSorter[int] = TopologicalSorter()
        for idx, entry in enumerate(entries):
            # Collect after deps that are in current group
            deps_in_group = []
            for dep in entry.after:
                if dep in callback_to_indices:
                    # All entries with this callback are dependencies
                    deps_in_group.extend(callback_to_indices[dep])
            ts.add(idx, *deps_in_group)

        # Execute sort
        try:
            sorted_indices = tuple(ts.static_order())
        except CycleError as e:
            raise CyclicDependencyError(f"cyclic dependency detected: {e.args}") from e

        return [entries[idx] for idx in sorted_indices]
