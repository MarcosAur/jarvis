import base64
from typing import Any
import httpx
from pipeline.config import config
from pipeline.domain.entities import BoardInfo, RemoteCard, SettingFieldSpec
from pipeline.domain.exceptions import BoardError


class JiraProjectProvider:
    provider_key = "jira"
    display_name = "Atlassian Jira"

    def settings_fields(self) -> list[SettingFieldSpec]:
        return [
            SettingFieldSpec(
                name="jira_base_url",
                label="Jira Base URL (ex: https://sua-empresa.atlassian.net)",
                type="text",
                required=False,
                description="URL base da sua instância Jira.",
            ),
            SettingFieldSpec(
                name="jira_email",
                label="Jira Email",
                type="text",
                required=False,
                description="E-mail da sua conta Atlassian.",
            ),
            SettingFieldSpec(
                name="jira_api_token",
                label="Jira API Token",
                type="password",
                required=False,
                is_secret=True,
                description="Token de API gerado na sua conta Atlassian.",
            ),
        ]

    def _get_auth_headers(self, settings: dict[str, Any]) -> tuple[str, dict[str, str]]:
        base_url = (settings.get("jira_base_url") or config.JIRA_BASE_URL or "").rstrip("/")
        email = settings.get("jira_email") or config.JIRA_EMAIL or ""
        token = settings.get("jira_api_token") or config.JIRA_API_TOKEN or ""

        if not base_url or not email or not token:
            raise BoardError("Credenciais do Jira incompletas. Informe URL, E-mail e API Token no CRUD de Configurações.")

        auth_str = f"{email}:{token}"
        encoded = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")
        headers = {
            "Authorization": f"Basic {encoded}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        return base_url, headers

    def test_connection(self, project_key: str, settings: dict[str, Any]) -> BoardInfo:
        base_url, headers = self._get_auth_headers(settings)
        # Search issues or get project
        url = f"{base_url}/rest/api/3/project/{project_key}"
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(url, headers=headers)
                if resp.status_code != 200:
                    raise BoardError(f"Jira API retornou {resp.status_code}: {resp.text}")
                data = resp.json()
                title = data.get("name", f"Jira Project {project_key}")

                # Fetch statuses
                status_url = f"{base_url}/rest/api/3/project/{project_key}/statuses"
                status_resp = client.get(status_url, headers=headers)
                columns: list[str] = []
                if status_resp.status_code == 200:
                    for issue_type in status_resp.json():
                        for st in issue_type.get("statuses", []):
                            st_name = st.get("name")
                            if st_name and st_name not in columns:
                                columns.append(st_name)

                return BoardInfo(
                    project_key=project_key,
                    title=title,
                    total_cards=len(columns),
                    columns=columns,
                    raw_meta=data,
                )
        except httpx.RequestError as e:
            raise BoardError(f"Falha ao conectar ao Jira: {e}") from e

    def fetch_cards(self, project_key: str, settings: dict[str, Any]) -> list[RemoteCard]:
        base_url, headers = self._get_auth_headers(settings)
        jql = f"project = '{project_key}' ORDER BY updated DESC"
        url = f"{base_url}/rest/api/3/search"

        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(url, headers=headers, params={"jql": jql, "maxResults": 100})
                if resp.status_code != 200:
                    raise BoardError(f"Erro ao buscar issues no Jira ({resp.status_code}): {resp.text}")
                data = resp.json()
                cards: list[RemoteCard] = []

                for issue in data.get("issues", []):
                    key = issue.get("key")
                    fields = issue.get("fields", {})
                    summary = fields.get("summary", "Sem título")
                    desc = fields.get("description")
                    body = desc if isinstance(desc, str) else ""
                    status = fields.get("status", {}).get("name", "Todo")
                    url_card = f"{base_url}/browse/{key}"

                    cards.append(
                        RemoteCard(
                            remote_id=key,
                            title=summary,
                            body=body,
                            column_name=status,
                            url=url_card,
                        )
                    )
                return cards
        except httpx.RequestError as e:
            raise BoardError(f"Falha de rede ao consultar Jira: {e}") from e

    def move_card(
        self,
        project_key: str,
        remote_card_id: str,
        target_column_name: str,
        settings: dict[str, Any],
    ) -> None:
        base_url, headers = self._get_auth_headers(settings)
        # Find transition matching target_column_name
        url_trans = f"{base_url}/rest/api/3/issue/{remote_card_id}/transitions"
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(url_trans, headers=headers)
                if resp.status_code != 200:
                    raise BoardError(f"Erro ao obter transições no Jira: {resp.text}")
                transitions = resp.json().get("transitions", [])
                target_id = None
                for t in transitions:
                    if t.get("to", {}).get("name", "").lower() == target_column_name.lower():
                        target_id = t.get("id")
                        break

                if target_id:
                    post_resp = client.post(url_trans, headers=headers, json={"transition": {"id": target_id}})
                    if post_resp.status_code not in (200, 204):
                        raise BoardError(f"Erro ao transicionar card no Jira: {post_resp.text}")
        except httpx.RequestError as e:
            raise BoardError(f"Falha ao mover card no Jira: {e}") from e

    def add_comment(
        self,
        project_key: str,
        remote_card_id: str,
        markdown: str,
        settings: dict[str, Any],
    ) -> None:
        base_url, headers = self._get_auth_headers(settings)
        url = f"{base_url}/rest/api/3/issue/{remote_card_id}/comment"
        try:
            with httpx.Client(timeout=15.0) as client:
                client.post(url, headers=headers, json={"body": markdown})
        except Exception:
            pass
