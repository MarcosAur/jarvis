import re
from typing import Any
import httpx
from pipeline.config import config
from pipeline.domain.entities import BoardInfo, RemoteCard, SettingFieldSpec
from pipeline.domain.exceptions import BoardError

GITHUB_GRAPHQL_ENDPOINT = "https://api.github.com/graphql"


class GitHubProjectProvider:
    provider_key = "github"
    display_name = "GitHub Projects (User v2)"

    def settings_fields(self) -> list[SettingFieldSpec]:
        return [
            SettingFieldSpec(
                name="github_token",
                label="GitHub Personal Access Token (classic ou fine-grained com read/write em projects)",
                type="password",
                required=False,
                is_secret=True,
                description="Token para autenticação na API do GitHub. Pode ser herdado de GITHUB_TOKEN no .env.",
            ),
            SettingFieldSpec(
                name="github_owner",
                label="GitHub Owner Padrão (Usuário ou Org)",
                type="text",
                required=False,
                description="Login do usuário dono do projeto. Pode ser herdado de GITHUB_OWNER no .env.",
            ),
        ]

    def _parse_project_key(self, project_key: str, default_owner: str | None = None) -> tuple[str, int]:
        """
        Parses project_key into (owner, number).
        Supports:
        - "3" -> (default_owner, 3)
        - "maurelio/3" -> ("maurelio", 3)
        - "https://github.com/users/maurelio/projects/3" -> ("maurelio", 3)
        - "https://github.com/orgs/minhaorg/projects/5" -> ("minhaorg", 5)
        """
        key = project_key.strip()

        # URL pattern
        url_match = re.search(r"github\.com/(?:users|orgs)/([^/]+)/projects/(\d+)", key)
        if url_match:
            return url_match.group(1), int(url_match.group(2))

        # owner/number pattern
        if "/" in key:
            parts = key.split("/", 1)
            return parts[0].strip(), int(parts[1].strip())

        # number only
        if key.isdigit():
            if not default_owner:
                raise BoardError("Owner do GitHub não informado. Forneça o projeto como 'owner/número' ou configure o owner nas Configurações.")
            return default_owner, int(key)

        raise BoardError(f"Formato inválido de chave de projeto GitHub: '{project_key}'. Use número, 'login/número' ou a URL do projeto.")

    def _get_token(self, settings: dict[str, Any]) -> str:
        token = settings.get("github_token") or config.GITHUB_TOKEN
        if not token:
            raise BoardError("GitHub Token não configurado. Adicione o token no CRUD de Configurações ou no arquivo .env.")
        return token

    def _get_owner(self, settings: dict[str, Any]) -> str | None:
        return settings.get("github_owner") or config.GITHUB_OWNER

    def _execute_graphql(self, token: str, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": "Pipeline-Desenvolvimento-Automatico",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(GITHUB_GRAPHQL_ENDPOINT, json={"query": query, "variables": variables}, headers=headers)
                if resp.status_code != 200:
                    raise BoardError(f"GitHub API retornou HTTP {resp.status_code}: {resp.text}")
                data = resp.json()
                if "errors" in data and data["errors"]:
                    err_msg = "; ".join([e.get("message", "Erro GraphQL") for e in data["errors"]])
                    raise BoardError(f"GitHub GraphQL error: {err_msg}")
                return data.get("data", {})
        except httpx.RequestError as e:
            raise BoardError(f"Falha de rede ao conectar à API do GitHub: {e}") from e

    def test_connection(self, project_key: str, settings: dict[str, Any]) -> BoardInfo:
        token = self._get_token(settings)
        owner, number = self._parse_project_key(project_key, self._get_owner(settings))

        query = """
        query($login: String!, $number: Int!) {
          user(login: $login) {
            projectV2(number: $number) {
              id
              title
              fields(first: 20) {
                nodes {
                  ... on ProjectV2SingleSelectField {
                    name
                    options {
                      name
                    }
                  }
                }
              }
              items {
                totalCount
              }
            }
          }
        }
        """
        data = self._execute_graphql(token, query, {"login": owner, "number": number})
        user_data = data.get("user")
        if not user_data or not user_data.get("projectV2"):
            # Try organization query if user returned empty
            query_org = query.replace("user(login: $login)", "organization(login: $login)")
            data_org = self._execute_graphql(token, query_org, {"login": owner, "number": number})
            org_data = data_org.get("organization")
            if not org_data or not org_data.get("projectV2"):
                raise BoardError(f"Projeto #{number} de '{owner}' não foi encontrado no GitHub.")
            proj = org_data["projectV2"]
        else:
            proj = user_data["projectV2"]

        columns = []
        for field in proj.get("fields", {}).get("nodes", []):
            if field.get("name") == "Status":
                columns = [opt["name"] for opt in field.get("options", [])]
                break

        total_cards = proj.get("items", {}).get("totalCount", 0)
        return BoardInfo(
            project_key=project_key,
            title=proj.get("title", f"GitHub Project #{number}"),
            total_cards=total_cards,
            columns=columns,
            raw_meta={"project_id": proj.get("id"), "owner": owner, "number": number},
        )

    def fetch_cards(self, project_key: str, settings: dict[str, Any]) -> list[RemoteCard]:
        token = self._get_token(settings)
        owner, number = self._parse_project_key(project_key, self._get_owner(settings))

        query = """
        query($login: String!, $number: Int!) {
          user(login: $login) {
            projectV2(number: $number) {
              items(first: 100) {
                nodes {
                  id
                  fieldValues(first: 10) {
                    nodes {
                      ... on ProjectV2ItemFieldSingleSelectValue {
                        name
                        field {
                          ... on ProjectV2SingleSelectField {
                            name
                          }
                        }
                      }
                    }
                  }
                  content {
                    ... on Issue {
                      number
                      title
                      body
                      url
                      repository {
                        nameWithOwner
                      }
                      labels(first: 10) {
                        nodes { name }
                      }
                      assignees(first: 5) {
                        nodes { login }
                      }
                      updatedAt
                    }
                    ... on DraftIssue {
                      title
                      body
                      updatedAt
                    }
                    ... on PullRequest {
                      number
                      title
                      body
                      url
                      repository {
                        nameWithOwner
                      }
                      updatedAt
                    }
                  }
                }
              }
            }
          }
        }
        """
        data = self._execute_graphql(token, query, {"login": owner, "number": number})
        user_data = data.get("user")
        if not user_data or not user_data.get("projectV2"):
            # Try organization query
            query_org = query.replace("user(login: $login)", "organization(login: $login)")
            data_org = self._execute_graphql(token, query_org, {"login": owner, "number": number})
            proj = data_org.get("organization", {}).get("projectV2")
        else:
            proj = user_data.get("projectV2")

        if not proj:
            raise BoardError(f"Projeto #{number} de '{owner}' não foi encontrado.")

        cards: list[RemoteCard] = []
        for item in proj.get("items", {}).get("nodes", []):
            item_id = item.get("id")
            content = item.get("content") or {}
            title = content.get("title") or "Sem título"
            body = content.get("body") or ""
            url = content.get("url")
            issue_num = content.get("number")
            repo = content.get("repository", {}).get("nameWithOwner") if content.get("repository") else None

            # Find status column value
            column_name = "Todo"  # fallback
            for fv in item.get("fieldValues", {}).get("nodes", []):
                if fv.get("field", {}).get("name") == "Status" and fv.get("name"):
                    column_name = fv.get("name")
                    break

            labels = [lbl.get("name") for lbl in content.get("labels", {}).get("nodes", [])]
            assignees = [a.get("login") for a in content.get("assignees", {}).get("nodes", [])]

            cards.append(
                RemoteCard(
                    remote_id=item_id,
                    title=title,
                    body=body,
                    column_name=column_name,
                    url=url,
                    issue_number=issue_num,
                    repository=repo,
                    labels=labels,
                    assignees=assignees,
                )
            )

        return cards

    def move_card(
        self,
        project_key: str,
        remote_card_id: str,
        target_column_name: str,
        settings: dict[str, Any],
    ) -> None:
        """Updates the Status field of a project card item via GraphQL."""
        token = self._get_token(settings)
        owner, number = self._parse_project_key(project_key, self._get_owner(settings))

        # Query project id, status field id and target option id
        query_fields = """
        query($login: String!, $number: Int!) {
          user(login: $login) {
            projectV2(number: $number) {
              id
              fields(first: 20) {
                nodes {
                  ... on ProjectV2SingleSelectField {
                    id
                    name
                    options {
                      id
                      name
                    }
                  }
                }
              }
            }
          }
        }
        """
        data = self._execute_graphql(token, query_fields, {"login": owner, "number": number})
        user_data = data.get("user")
        proj = user_data.get("projectV2") if user_data else None
        if not proj:
            return

        proj_id = proj.get("id")
        field_id = None
        option_id = None

        for field in proj.get("fields", {}).get("nodes", []):
            if field.get("name") == "Status":
                field_id = field.get("id")
                for opt in field.get("options", []):
                    if opt.get("name", "").strip().lower() == target_column_name.strip().lower():
                        option_id = opt.get("id")
                        break
                break

        if not field_id or not option_id:
            raise BoardError(f"Coluna de destino '{target_column_name}' não encontrada no GitHub Project #{number}.")

        mutation = """
        mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $optionId: String!) {
          updateProjectV2ItemFieldValue(input: {
            projectId: $projectId
            itemId: $itemId
            fieldId: $fieldId
            value: { singleSelectOptionId: $optionId }
          }) {
            projectV2Item { id }
          }
        }
        """
        self._execute_graphql(
            token,
            mutation,
            {
                "projectId": proj_id,
                "itemId": remote_card_id,
                "fieldId": field_id,
                "optionId": option_id,
            },
        )

    def add_comment(
        self,
        project_key: str,
        remote_card_id: str,
        markdown: str,
        settings: dict[str, Any],
    ) -> None:
        # For full issues, comments are added to issue node ID
        token = self._get_token(settings)
        mutation = """
        mutation($subjectId: ID!, $body: String!) {
          addComment(input: { subjectId: $subjectId, body: $body }) {
            commentEdge { node { id } }
          }
        }
        """
        try:
            self._execute_graphql(token, mutation, {"subjectId": remote_card_id, "body": markdown})
        except Exception:
            # Non-blocking for comments
            pass
