from typing import Any

import pytest

from pipeline.bootstrap import cli_registry, project_registry
from pipeline.domain.entities import BoardInfo, RemoteCard, SettingFieldSpec
from pipeline.domain.exceptions import ContractViolationError
from pipeline.domain.ports.cli_provider import CliModelProvider
from pipeline.domain.ports.project_provider import ProjectProvider
from pipeline.domain.registry import Registry


class ValidBoard(ProjectProvider):
    """A conforming fourth provider: explicit inheritance + exact signatures."""

    provider_key = "valid_board"
    display_name = "Valid Board"

    def settings_fields(self) -> list[SettingFieldSpec]:
        return []

    def test_connection(self, project_key: str, settings: dict[str, Any]) -> BoardInfo:
        return BoardInfo(project_key=project_key, title="x", total_cards=0, columns=[])

    def fetch_cards(self, project_key: str, settings: dict[str, Any]) -> list[RemoteCard]:
        return []

    def move_card(
        self, project_key: str, remote_card_id: str, target_column_name: str, settings: dict[str, Any]
    ) -> None: ...

    def add_comment(self, project_key: str, remote_card_id: str, markdown: str, settings: dict[str, Any]) -> None: ...


def new_board_registry() -> Registry[ProjectProvider]:
    return Registry[ProjectProvider]("Test", contract=ProjectProvider)


# --- real providers ---------------------------------------------------------


def test_all_registered_providers_inherit_their_port():
    for p in cli_registry.list_all():
        assert isinstance(p, CliModelProvider)
        assert CliModelProvider in type(p).__mro__
    for p in project_registry.list_all():
        assert isinstance(p, ProjectProvider)
        assert ProjectProvider in type(p).__mro__


def test_registries_enforce_the_contract():
    assert cli_registry.contract is CliModelProvider
    assert project_registry.contract is ProjectProvider


# --- a conforming 4th provider ----------------------------------------------


def test_conforming_provider_is_accepted():
    reg = new_board_registry()
    reg.register(ValidBoard())
    assert reg.has("valid_board")


# --- missing methods --------------------------------------------------------


def test_explicit_subclass_with_missing_method_cannot_be_instantiated():
    class Incomplete(ProjectProvider):
        provider_key = "incomplete"
        display_name = "Incomplete"

        def fetch_cards(self, project_key: str, settings: dict[str, Any]) -> list[RemoteCard]:
            return []

    with pytest.raises(TypeError, match="abstract"):
        Incomplete()


def test_duck_typed_provider_with_missing_method_is_rejected_on_register():
    class NoWriter:
        provider_key = "no_writer"
        display_name = "No Writer"

        def settings_fields(self) -> list[SettingFieldSpec]:
            return []

        def test_connection(self, project_key: str, settings: dict[str, Any]) -> BoardInfo:
            return BoardInfo(project_key=project_key, title="x", total_cards=0, columns=[])

        def fetch_cards(self, project_key: str, settings: dict[str, Any]) -> list[RemoteCard]:
            return []

    reg = new_board_registry()
    with pytest.raises(ContractViolationError) as exc:
        reg.register(NoWriter())
    assert "move_card" in str(exc.value)
    assert "add_comment" in str(exc.value)
    assert not reg.has("no_writer")


# --- different signatures ---------------------------------------------------


def _board_with(**overrides: Any) -> object:
    """Builds a ValidBoard-like duck-typed provider, replacing the given methods."""
    namespace = {n: getattr(ValidBoard, n) for n in (
        "settings_fields", "test_connection", "fetch_cards", "move_card", "add_comment")}
    namespace.update(provider_key="dup", display_name="Dup")
    namespace.update(overrides)
    return type("DuckBoard", (), namespace)()


def test_different_parameter_name_is_rejected():
    def fetch_cards(self, key: str, settings: dict[str, Any]) -> list[RemoteCard]:
        return []

    with pytest.raises(ContractViolationError, match="fetch_cards"):
        new_board_registry().register(_board_with(fetch_cards=fetch_cards))


def test_missing_parameter_is_rejected():
    def move_card(self, project_key: str, remote_card_id: str, target_column_name: str) -> None: ...

    with pytest.raises(ContractViolationError, match="move_card"):
        new_board_registry().register(_board_with(move_card=move_card))


def test_different_parameter_type_is_rejected():
    def add_comment(self, project_key: str, remote_card_id: str, markdown: int, settings: dict[str, Any]) -> None: ...

    with pytest.raises(ContractViolationError, match="add_comment"):
        new_board_registry().register(_board_with(add_comment=add_comment))


def test_different_return_type_is_rejected():
    def fetch_cards(self, project_key: str, settings: dict[str, Any]) -> dict:
        return {}

    with pytest.raises(ContractViolationError, match="fetch_cards"):
        new_board_registry().register(_board_with(fetch_cards=fetch_cards))


def test_missing_annotations_are_rejected():
    def fetch_cards(self, project_key, settings):
        return []

    with pytest.raises(ContractViolationError, match="fetch_cards"):
        new_board_registry().register(_board_with(fetch_cards=fetch_cards))


# --- attributes -------------------------------------------------------------


def test_empty_display_name_is_rejected():
    class Nameless(ValidBoard):
        provider_key = "nameless"
        display_name = ""

    with pytest.raises(ContractViolationError, match="display_name"):
        new_board_registry().register(Nameless())


def test_missing_provider_key_is_rejected():
    class Keyless(ValidBoard):
        provider_key = ""

    with pytest.raises(ContractViolationError, match="provider_key"):
        new_board_registry().register(Keyless(), key="keyless")


# --- CLI port ---------------------------------------------------------------


def test_cli_provider_with_wrong_signature_is_rejected():
    class BadCli:
        provider_key = "bad_cli"
        display_name = "Bad"
        binary_name = "bad"

        def is_installed(self) -> bool:
            return True

        def list_models(self):
            return []

        def execute_prompt(self, req):
            return None

    reg = Registry[CliModelProvider]("TestCli", contract=CliModelProvider)
    with pytest.raises(ContractViolationError) as exc:
        reg.register(BadCli())
    assert "list_models" in str(exc.value)
    assert "execute_prompt" in str(exc.value)


# --- registry without a contract keeps working -----------------------------


def test_registry_without_contract_accepts_anything():
    reg: Registry[Any] = Registry("Free")
    reg.register(object(), key="anything")
    assert reg.has("anything")
