"""Synchronous dispatcher for affair handling."""

from typing import Any

from loguru import logger

from affairon._types import (
    SyncCallback,
)
from affairon.affairs import CallbackErrorAffair, MutableAffair
from affairon.base_dispatcher import BaseDispatcher
from affairon.utils import callable_name, merge_dict

log = logger.bind(source=__name__)


class Dispatcher(BaseDispatcher[SyncCallback]):
    """Synchronous affair dispatcher.

    Executes listeners synchronously in priority order.
    Recursive emit() calls execute directly (no queue).
    """

    @staticmethod
    def _sample_guardian(affair: MutableAffair) -> None:
        """Silent guardian callback to anchor execution order."""

    def __init__(self):
        super().__init__(self._sample_guardian)

    def emit(self, affair: MutableAffair) -> dict[str, Any]:
        """Synchronously dispatch affair.

        When ``affair.emit_up`` is True, callbacks registered on parent
        affair types are also invoked, walking the MRO from child to
        parent.

        If a callback raises an exception, the dispatcher emits a
        :class:`CallbackErrorAffair`.  Error handlers may return control
        keys (``retry``, ``deadletter``, ``silent``) to influence recovery.
        Priority: retry first → deadletter → silent → re-raise.

        Warning:
            Listeners can recursively call emit(). Framework does not detect cycles.
            Users must avoid infinite recursion chains (e.g., A→B→A), otherwise
            Python's RecursionError will be raised.

        Args:
            affair: MutableAffair to dispatch.

        Returns:
            Merged dict of all listener results.

        Post:
            All matching listeners executed in priority order.

        Raises:
            TypeError: If listener returns non-dict value.
            KeyConflictError: If merging dicts causes key conflict.
            RecursionError: If listeners form infinite recursion chain.
        """
        merged_result: dict[str, Any] = {}
        affair_types = self._resolve_affair_types(affair)
        log.debug(
            "Emit {} (types={})",
            type(affair).__qualname__,
            [t.__qualname__ for t in affair_types],
        )
        for affair_type in affair_types:
            layers = self._registry.exec_order(affair_type)
            for layer in layers:
                for cb in layer:
                    if not self._registry.should_fire(cb, affair_type, affair):
                        continue
                    try:
                        result = cb(affair)
                    except Exception as exc:
                        result = self._handle_callback_error(cb, affair, exc)
                    if result is not None:
                        if not isinstance(result, dict):
                            raise TypeError(
                                f"Callback {callable_name(cb)} returned "
                                f"{type(result).__name__}, expected dict or None"
                            )
                        merge_dict(merged_result, result)
        return merged_result

    def _handle_callback_error(
        self,
        callback: SyncCallback,
        affair: MutableAffair,
        exception: Exception,
    ) -> dict[str, Any] | None:
        """Handle a callback exception via CallbackErrorAffair.

        Emits a :class:`CallbackErrorAffair` and reads the merged error
        policy.  Retry is attempted first; on exhaustion, ``deadletter``
        and ``silent`` are checked.

        Args:
            callback: The callback that raised.
            affair: The affair being dispatched.
            exception: The exception that was raised.

        Returns:
            Callback result on successful retry, or None when silenced
            or dead-lettered.

        Raises:
            Exception: Re-raises *exception* when no handler suppresses it.
        """
        error_affair = CallbackErrorAffair(
            listener_name=callable_name(callback),
            original_affair_type=type(affair).__qualname__,
            error_message=str(exception),
            error_type=type(exception).__name__,
        )
        policy = self.emit(error_affair)
        retry, deadletter, silent = self._read_error_policy(policy)
        log.debug(
            "Error policy for {}: retry={}, deadletter={}, silent={}",
            callable_name(callback),
            retry,
            deadletter,
            silent,
        )
        while retry > 0:
            retry -= 1
            try:
                return callback(affair)
            except Exception:
                pass
        if deadletter:
            return None
        if silent:
            return None
        raise exception
