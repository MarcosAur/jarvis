import pytest
from pipeline.adapters.project_providers.github_projects import GitHubProjectProvider
from pipeline.domain.exceptions import BoardError
from pipeline.domain.ports.project_provider import ProjectProvider


def test_github_provider_conforms_to_protocol():
    gh = GitHubProjectProvider()
    assert isinstance(gh, ProjectProvider)
    assert gh.provider_key == "github"


def test_parse_project_key_formats():
    gh = GitHubProjectProvider()

    # 1. Number only with default owner
    owner, num = gh._parse_project_key("3", default_owner="maurelio")
    assert owner == "maurelio"
    assert num == 3

    # 2. owner/number
    owner, num = gh._parse_project_key("outro_user/42")
    assert owner == "outro_user"
    assert num == 42

    # 3. User project URL
    owner, num = gh._parse_project_key("https://github.com/users/maurelio/projects/1")
    assert owner == "maurelio"
    assert num == 1

    # 4. Org project URL
    owner, num = gh._parse_project_key("https://github.com/orgs/google/projects/99")
    assert owner == "google"
    assert num == 99


def test_parse_project_key_errors():
    gh = GitHubProjectProvider()

    # Number only without default owner
    with pytest.raises(BoardError, match="Owner do GitHub não informado"):
        gh._parse_project_key("3", default_owner=None)

    # Invalid string
    with pytest.raises(BoardError, match="Formato inválido"):
        gh._parse_project_key("abc-xyz")
