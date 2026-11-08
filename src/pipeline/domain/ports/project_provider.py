from typing import Any, ClassVar, Protocol, runtime_checkable
from pipeline.domain.entities import BoardInfo, RemoteCard, SettingFieldSpec


@runtime_checkable
class ProjectBoardReader(Protocol):
    """Port for reading cards and checking connection with external project boards."""

    provider_key: ClassVar[str]
    display_name: ClassVar[str]

    def settings_fields(self) -> list[SettingFieldSpec]:
        """Returns the configuration fields required by this board provider."""
        ...

    def test_connection(self, project_key: str, settings: dict[str, Any]) -> BoardInfo:
        """Validates connection and returns board summary."""
        ...

    def fetch_cards(self, project_key: str, settings: dict[str, Any]) -> list[RemoteCard]:
        """Fetches all cards from the external project board."""
        ...


@runtime_checkable
class ProjectBoardWriter(Protocol):
    """Port for modifying cards in external project boards."""

    def move_card(
        self,
        project_key: str,
        remote_card_id: str,
        target_column_name: str,
        settings: dict[str, Any],
    ) -> None:
        """Moves a card to another column in the external board."""
        ...

    def add_comment(
        self,
        project_key: str,
        remote_card_id: str,
        markdown: str,
        settings: dict[str, Any],
    ) -> None:
        """Adds a comment to the remote card."""
        ...


@runtime_checkable
class ProjectProvider(ProjectBoardReader, ProjectBoardWriter, Protocol):
    """Full project board interface combining read and write operations."""
    pass
