from .base import BaseAuthStrategy

auth_registry: dict[str, type[BaseAuthStrategy]] = {}


def register_auth(name: str):
    """Decorator to register an auth strategy by name."""
    def wrapper(cls: type[BaseAuthStrategy]):
        auth_registry[name] = cls
        return cls
    return wrapper


def get_auth_strategy(name: str) -> BaseAuthStrategy:
    cls = auth_registry.get(name)
    if cls is None:
        raise ValueError(
            f"Unknown auth strategy: {name!r}. Registered: {list(auth_registry)}"
        )
    return cls()
