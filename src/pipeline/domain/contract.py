import inspect
from typing import Any, get_type_hints

from pipeline.domain.exceptions import ContractViolationError

_IGNORED_MODULES = {"typing", "typing_extensions", "builtins", "abc"}


def _contract_classes(contract: type) -> list[type]:
    return [c for c in contract.__mro__ if c.__module__ not in _IGNORED_MODULES]


def contract_methods(contract: type) -> dict[str, Any]:
    """Public methods declared by the port (including the ports it extends)."""
    methods: dict[str, Any] = {}
    for cls in reversed(_contract_classes(contract)):
        for name, value in vars(cls).items():
            if not name.startswith("_") and inspect.isfunction(value):
                methods[name] = value
    return methods


def contract_attributes(contract: type) -> list[str]:
    """Attributes (e.g. ``provider_key``) declared by the port."""
    attrs: list[str] = []
    for cls in reversed(_contract_classes(contract)):
        for name in vars(cls).get("__annotations__", {}):
            if not name.startswith("_") and name not in attrs:
                attrs.append(name)
    return attrs


def _signature_shape(func: Any) -> tuple[list[tuple[str, Any, bool, Any]], Any]:
    sig = inspect.signature(func)
    try:
        hints = get_type_hints(func)
    except Exception:  # pragma: no cover - unresolved annotations
        hints = dict(getattr(func, "__annotations__", {}))
    params = [
        (p.name, p.kind, p.default is not inspect.Parameter.empty, hints.get(p.name, inspect.Parameter.empty))
        for p in sig.parameters.values()
    ]
    return params, hints.get("return", inspect.Parameter.empty)


def _describe(func: Any) -> str:
    try:
        return f"{getattr(func, '__name__', 'method')}{inspect.signature(func)}"
    except (TypeError, ValueError):  # pragma: no cover
        return str(func)


def find_contract_violations(item: Any, contract: type) -> list[str]:
    """Lists every way in which ``item`` fails to fulfill ``contract`` (empty if it conforms)."""
    problems: list[str] = []

    for name in contract_attributes(contract):
        if not hasattr(item, name):
            problems.append(f"atributo '{name}' ausente")
            continue
        value = getattr(item, name)
        if isinstance(value, str) and not value.strip():
            problems.append(f"atributo '{name}' está vazio")

    for name, expected in contract_methods(contract).items():
        actual = getattr(item, name, None)
        if actual is None or not callable(actual):
            problems.append(f"método '{name}' ausente")
            continue

        # Contract side is an unbound function (has `self`), instance side is bound.
        expected_bound = expected.__get__(item, type(item))
        exp_params, exp_ret = _signature_shape(expected_bound)
        act_params, act_ret = _signature_shape(actual)
        if exp_params != act_params or exp_ret != act_ret:
            problems.append(
                f"assinatura de '{name}' diferente do contrato: "
                f"esperado {_describe(expected_bound)}, encontrado {_describe(actual)}"
            )
    return problems


def ensure_contract(item: Any, contract: type) -> None:
    """Raises ``ContractViolationError`` if ``item`` does not fulfill ``contract``."""
    problems = find_contract_violations(item, contract)
    if problems:
        owner = type(item).__name__
        details = "; ".join(problems)
        raise ContractViolationError(
            f"'{owner}' não cumpre o contrato '{contract.__name__}': {details}."
        )
