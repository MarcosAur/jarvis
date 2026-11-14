from typing import Any
import httpx
from pipeline.config import config
from pipeline.domain.entities import BoardInfo, RemoteCard, SettingFieldSpec
from pipeline.domain.exceptions import BoardError
from pipeline.domain.ports.project_provider import ProjectProvider

TRELLO_BASE_URL = "https://api.trello.com/1"


class TrelloProjectProvider(ProjectProvider):
    provider_key = "trello"
    display_name = "Trello"

    def settings_fields(self) -> list[SettingFieldSpec]:
        return [
            SettingFieldSpec(
                name="trello_api_key",
                label="Trello API Key",
                type="text",
                required=False,
                description="Chave de API do desenvolvedor no Trello.",
            ),
            SettingFieldSpec(
                name="trello_token",
                label="Trello Token",
                type="password",
                required=False,
                is_secret=True,
                description="Token de autorização gerado no Trello.",
            ),
        ]

    def _get_auth_params(self, settings: dict[str, Any]) -> dict[str, str]:
        key = settings.get("trello_api_key") or config.TRELLO_API_KEY
        token = settings.get("trello_token") or config.TRELLO_TOKEN
        if not key or not token:
            raise BoardError("Credenciais do Trello incompletas. Informe API Key e Token no CRUD de Configurações.")
        return {"key": key, "token": token}

    def test_connection(self, project_key: str, settings: dict[str, Any]) -> BoardInfo:
        params = self._get_auth_params(settings)
        board_id = project_key.strip()

        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(f"{TRELLO_BASE_URL}/boards/{board_id}", params=params)
                if resp.status_code != 200:
                    raise BoardError(f"Trello API retornou {resp.status_code}: {resp.text}")
                data = resp.json()
                title = data.get("name", f"Quadro Trello {board_id}")

                # Lists
                list_resp = client.get(f"{TRELLO_BASE_URL}/boards/{board_id}/lists", params=params)
                columns = [l.get("name") for l in list_resp.json()] if list_resp.status_code == 200 else []

                # Cards count
                cards_resp = client.get(f"{TRELLO_BASE_URL}/boards/{board_id}/cards", params=params)
                total = len(cards_resp.json()) if cards_resp.status_code == 200 else 0

                return BoardInfo(
                    project_key=project_key,
                    title=title,
                    total_cards=total,
                    columns=columns,
                    raw_meta=data,
                )
        except httpx.RequestError as e:
            raise BoardError(f"Falha de rede ao conectar ao Trello: {e}") from e

    def fetch_cards(self, project_key: str, settings: dict[str, Any]) -> list[RemoteCard]:
        params = self._get_auth_params(settings)
        board_id = project_key.strip()

        try:
            with httpx.Client(timeout=30.0) as client:
                # Get lists first to map idList -> list name
                list_resp = client.get(f"{TRELLO_BASE_URL}/boards/{board_id}/lists", params=params)
                if list_resp.status_code != 200:
                    raise BoardError(f"Erro ao buscar listas no Trello: {list_resp.text}")
                lists_map = {l["id"]: l["name"] for l in list_resp.json()}

                # Get cards
                cards_resp = client.get(f"{TRELLO_BASE_URL}/boards/{board_id}/cards", params=params)
                if cards_resp.status_code != 200:
                    raise BoardError(f"Erro ao buscar cards no Trello: {cards_resp.text}")

                cards: list[RemoteCard] = []
                for c in cards_resp.json():
                    col_name = lists_map.get(c.get("idList"), "Todo")
                    cards.append(
                        RemoteCard(
                            remote_id=c.get("id"),
                            title=c.get("name", "Sem título"),
                            body=c.get("desc", ""),
                            column_name=col_name,
                            url=c.get("shortUrl") or c.get("url"),
                        )
                    )
                return cards
        except httpx.RequestError as e:
            raise BoardError(f"Falha ao consultar Trello: {e}") from e

    def move_card(
        self,
        project_key: str,
        remote_card_id: str,
        target_column_name: str,
        settings: dict[str, Any],
    ) -> None:
        params = self._get_auth_params(settings)
        board_id = project_key.strip()

        try:
            with httpx.Client(timeout=15.0) as client:
                # Find target list ID
                list_resp = client.get(f"{TRELLO_BASE_URL}/boards/{board_id}/lists", params=params)
                if list_resp.status_code != 200:
                    return
                target_list_id = None
                for l in list_resp.json():
                    if l.get("name", "").lower() == target_column_name.lower():
                        target_list_id = l.get("id")
                        break

                if target_list_id:
                    client.put(
                        f"{TRELLO_BASE_URL}/cards/{remote_card_id}",
                        params={**params, "idList": target_list_id},
                    )
        except Exception:
            pass

    def add_comment(
        self,
        project_key: str,
        remote_card_id: str,
        markdown: str,
        settings: dict[str, Any],
    ) -> None:
        params = self._get_auth_params(settings)
        try:
            with httpx.Client(timeout=15.0) as client:
                client.post(
                    f"{TRELLO_BASE_URL}/cards/{remote_card_id}/actions/comments",
                    params={**params, "text": markdown},
                )
        except Exception:
            pass
