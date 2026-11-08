from typing import Generic, TypeVar

T = TypeVar("T")


class Registry(Generic[T]):
    """Generic in-memory registry for pluggable components."""

    def __init__(self, name: str = "Registry"):
        self.name = name
        self._items: dict[str, T] = {}

    def register(self, item: T, key: str | None = None) -> None:
        actual_key = key or getattr(item, "provider_key", None)
        if not actual_key:
            raise ValueError(f"Cannot register item {item}: missing key or provider_key.")
        self._items[str(actual_key)] = item

    def get(self, key: str) -> T:
        if key not in self._items:
            raise KeyError(f"Item with key '{key}' not found in {self.name}.")
        return self._items[key]

    def get_or_none(self, key: str) -> T | None:
        return self._items.get(key)

    def has(self, key: str) -> bool:
        return key in self._items

    def list_keys(self) -> list[str]:
        return list(self._items.keys())

    def list_all(self) -> list[T]:
        return list(self._items.values())

    def clear(self) -> None:
        self._items.clear()
