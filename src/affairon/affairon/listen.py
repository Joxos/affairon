from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from affairon.affairs import MutableAffair


@dataclass(frozen=True)
class ListenSpec:
    affair_types: list[type[MutableAffair]]
    after: list[Any] | None  # pyright: ignore[reportExplicitAny]
    when: Callable[[Any], bool] | None  # pyright: ignore[reportExplicitAny]


LISTEN_SPEC_ATTR = "_affair_listen_spec"


def listen[A: MutableAffair, F: Callable[..., Any]](
    *affair_types: type[A],
    after: list[Any] | None = None,  # pyright: ignore[reportExplicitAny]
    when: Callable[[A], bool] | None = None,
) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        setattr(
            func,
            LISTEN_SPEC_ATTR,
            ListenSpec(
                affair_types=list(affair_types),
                after=after,
                when=cast(Callable[[Any], bool] | None, when),  # pyright: ignore[reportExplicitAny]
            ),
        )
        return func

    return decorator


def get_listen_spec(obj: Any) -> ListenSpec | None:  # pyright: ignore[reportAny, reportExplicitAny]
    spec = getattr(obj, LISTEN_SPEC_ATTR, None)  # pyright: ignore[reportAny]
    if isinstance(spec, ListenSpec):
        return spec
    return None


__all__ = ["LISTEN_SPEC_ATTR", "ListenSpec", "get_listen_spec", "listen"]
